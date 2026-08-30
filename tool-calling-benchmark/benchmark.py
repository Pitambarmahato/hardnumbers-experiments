"""Benchmark tool-calling reliability for local AI agent workflows.

Tests how reliably Qwen3 14B and Llama 3.2 3B produce valid, schema-correct
JSON tool calls via Ollama. The experiment is the basis of an article on
whether small local models can be used as the LLM backend for popular
agent frameworks (LangChain, Pydantic AI, Smolagents, etc.).

Output: experiments/runs/tool_calling_<timestamp>.json with per-task
results + aggregate metrics.

Usage:
    python3 scripts/benchmark_tool_calling.py
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Local Ollama API
OLLAMA_URL = "http://localhost:11434/api/chat"

MODELS = [
    ("Qwen3 14B (Q4_K_M)", "qwen3:14b", 14.8),
    ("Llama 3.2 3B (Q4_0)", "llama3.2:latest", 3.2),
]

# Six plausible agent tools, defined in OpenAI function-calling JSON schema
# style (which Ollama also accepts). These mirror the kind of toolset a
# small productivity agent would have.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_articles",
            "description": "Search the publication's article archive by topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Add a task to the user's to-do list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_user",
            "description": "Look up a user by email address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_meeting",
            "description": "Book a meeting on the user's calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "starts_at": {"type": "string", "description": "ISO datetime"},
                    "duration_minutes": {"type": "integer", "minimum": 5, "maximum": 480},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "starts_at", "duration_minutes"],
            },
        },
    },
]

# Ten prompts with the expected correct tool. Used to score tool-selection
# accuracy. The other checks (JSON parse, schema valid) are objective.
TASKS = [
    ("get_weather",     "What's the weather like in Tokyo right now?"),
    ("get_weather",     "Will I need an umbrella in London tomorrow? Use Celsius."),
    ("search_articles", "Find me articles about RAG evaluation. Limit to 5."),
    ("create_task",     "Add a high-priority task: 'Submit Q3 report' by 2026-10-15."),
    ("create_task",     "Remind me to call the dentist."),
    ("send_email",      "Email priya@hardnumbers.dev about the new article launch. Subject: New article live. Body: Our RAG benchmark article just went up. Worth a read."),
    ("lookup_user",     "Find the user with email alex@example.com."),
    ("book_meeting",    "Book a 30-minute design review tomorrow at 2pm with sam@ and jordan@."),
    ("book_meeting",    "Schedule a 1-hour standup every Monday at 9am. Title: Weekly standup."),
    ("search_articles", "Show me recent articles on small model inference. Cap at 10."),
]


def _strip_think(text: str) -> str:
    """Remove Qwen3-style <think>...</think> blocks before JSON parse."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _try_parse_json(text: str) -> tuple[dict | None, str | None]:
    """Best-effort extract of a tool call JSON object from model output.

    Returns (parsed_dict, error_reason). Accepts:
      - raw JSON object
      - ```json fenced block
      - text containing a JSON object
    """
    cleaned = _strip_think(text)

    # 1) raw
    try:
        return json.loads(cleaned), None
    except Exception:
        pass
    # 2) fenced ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1)), None
        except Exception as e:
            return None, f"fenced json parse: {e}"
    # 3) first {...} in the text
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0)), None
        except Exception as e:
            return None, f"first-brace parse: {e}"
    return None, "no JSON object found"


def _validate_call(call: dict) -> tuple[bool, str | None, str | None, str | None]:
    """Return (is_valid, tool_name, arg_error, missing_field).

    Validates that `call` is a {name, arguments} dict where name is in TOOLS
    and arguments satisfies that tool's required-field / type constraints.
    """
    if not isinstance(call, dict):
        return False, None, "call is not a dict", None
    name = call.get("name")
    args = call.get("arguments")
    if not isinstance(name, str):
        return False, None, "name missing or not a string", None
    schema = next(
        (t["function"]["parameters"] for t in TOOLS if t["function"]["name"] == name),
        None,
    )
    if schema is None:
        return False, name, "unknown tool name", None
    if not isinstance(args, dict):
        return False, name, "arguments missing or not a dict", None
    for required in schema.get("required", []):
        if required not in args:
            return False, name, f"missing required field: {required}", required
    props = schema.get("properties", {})
    for k, v in args.items():
        if k not in props:
            return False, name, f"unexpected argument: {k}", None
        spec = props[k]
        t = spec.get("type")
        if t == "string" and not isinstance(v, str):
            return False, name, f"argument {k!r} should be string", None
        if t == "integer" and not isinstance(v, int):
            return False, name, f"argument {k!r} should be integer", None
        if t == "array" and not isinstance(v, list):
            return False, name, f"argument {k!r} should be array", None
        if "enum" in spec and v not in spec["enum"]:
            return False, name, f"argument {k!r} not in enum {spec['enum']}", None
    return True, name, None, None


def query(model: str, prompt: str, timeout: int = 180) -> dict:
    """Ask the model to choose a tool. Returns timing + response data."""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an AI agent with access to tools. When the user's "
                    "request can be handled by a tool, respond with a JSON object "
                    "of the form {\"name\": \"<tool_name>\", \"arguments\": {...}} "
                    "and nothing else. If no tool fits, respond with the single word "
                    "NONE."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "tools": TOOLS,
        "stream": False,
        "options": {
            "num_predict": 512,
            "temperature": 0,
        },
    }
    t0 = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(OLLAMA_URL, json=payload)
    wall_ms = (time.perf_counter() - t0) * 1000
    if resp.status_code != 200:
        return {"ok": False, "wall_ms": wall_ms, "error": f"http {resp.status_code}: {resp.text[:200]}"}
    body = resp.json()
    msg = body.get("message") or {}
    # Ollama's chat response with tools: the model may put a tool call in
    # `tool_calls`, OR it may put raw JSON in `content`. Handle both.
    content = msg.get("content", "")
    tool_calls = msg.get("tool_calls") or []
    eval_count = body.get("eval_count", 0)  # tokens generated
    prompt_eval_count = body.get("prompt_eval_count", 0)
    return {
        "ok": True,
        "wall_ms": wall_ms,
        "content": content,
        "tool_calls": tool_calls,
        "tokens_out": eval_count,
        "tokens_in": prompt_eval_count,
    }


def main() -> None:
    captured_at = datetime.now(timezone.utc).isoformat()
    machine = _detect_machine()
    print(f"tool-calling benchmark starting @ {captured_at}")
    print(f"machine: {machine}")
    print(f"models:  {[m[1] for m in MODELS]}")

    model_results = []
    for label, tag, params_b in MODELS:
        print(f"\n=== {label} ({tag}) ===")
        tasks = []
        for idx, (expected, prompt) in enumerate(TASKS, start=1):
            print(f"  task {idx:2d} [{expected:15s}] ... ", end="", flush=True)
            r = query(tag, prompt)
            if not r.get("ok"):
                print(f"http error ({r.get('error', '?')[:60]})")
                tasks.append({
                    "idx": idx,
                    "expected_tool": expected,
                    "prompt": prompt,
                    "ok": False,
                    "error": r.get("error"),
                    "wall_ms": r.get("wall_ms", 0),
                })
                continue

            # Extract the model call. Prefer tool_calls (structured). Fall back
            # to parsing content as JSON.
            call: dict | None = None
            parse_error: str | None = None
            if r.get("tool_calls"):
                # Ollama returns tool_calls as a list of {function: {name, arguments}}
                tc = r["tool_calls"][0]
                fn = tc.get("function", tc)
                call = {"name": fn.get("name"), "arguments": fn.get("arguments")}
            else:
                call, parse_error = _try_parse_json(r.get("content", ""))

            is_valid, name_used, arg_error, missing = _validate_call(call) if call else (False, None, "no call parsed", None)
            tokens_out = r.get("tokens_out", 0)
            wall_ms = r.get("wall_ms", 0)
            tok_per_s = (tokens_out / (wall_ms / 1000.0)) if wall_ms > 0 and tokens_out > 0 else 0.0

            tasks.append({
                "idx": idx,
                "expected_tool": expected,
                "prompt": prompt,
                "ok": True,
                "parse_error": parse_error,
                "is_valid": is_valid,
                "tool_used": name_used,
                "arg_error": arg_error,
                "missing_field": missing,
                "wall_ms": wall_ms,
                "tokens_out": tokens_out,
                "tokens_in": r.get("tokens_in", 0),
                "tokens_per_sec": round(tok_per_s, 2),
                "raw_content_preview": (r.get("content") or "")[:200],
                "raw_call": call,
            })

            status = "ok" if is_valid else "bad"
            correct = "✓" if (is_valid and name_used == expected) else (" " if is_valid else "✗")
            print(f"{correct} {status:3s}  {wall_ms:6.0f}ms  {tok_per_s:5.1f} tok/s  -> {name_used or '(none)'}")

        # Per-model aggregates
        valid = [t for t in tasks if t.get("ok") and t.get("is_valid")]
        parseable = [t for t in tasks if t.get("ok") and t.get("tool_used")]
        correct_tool = [t for t in valid if t.get("tool_used") == t.get("expected_tool")]
        wall_times = [t["wall_ms"] for t in tasks if t.get("ok")]
        tok_speeds = [t["tokens_per_sec"] for t in tasks if t.get("ok")]

        model_results.append({
            "name": label,
            "tag": tag,
            "params_b": params_b,
            "tasks": tasks,
            "summary": {
                "total": len(tasks),
                "http_ok": sum(1 for t in tasks if t.get("ok")),
                "json_parse_ok": len(parseable),
                "schema_valid": len(valid),
                "tool_correct": len(correct_tool),
                "parse_rate": _pct(len(parseable), len(tasks)),
                "valid_rate": _pct(len(valid), len(tasks)),
                "tool_correct_rate": _pct(len(correct_tool), len(tasks)),
                "wall_ms_median": int(statistics.median(wall_times)) if wall_times else 0,
                "wall_ms_p90": int(_percentile(wall_times, 90)) if wall_times else 0,
                "tok_per_sec_median": round(statistics.median(tok_speeds), 2) if tok_speeds else 0,
                "tok_per_sec_p10": round(_percentile(tok_speeds, 10), 2) if tok_speeds else 0,
                "total_tokens_out": sum(t.get("tokens_out", 0) for t in tasks),
            },
        })
        s = model_results[-1]["summary"]
        print(f"\n  → parse: {s['parse_rate']}%  valid: {s['valid_rate']}%  tool_correct: {s['tool_correct_rate']}%  "
              f"median wall: {s['wall_ms_median']}ms  median tok/s: {s['tok_per_sec_median']}")

    out_dir = Path("experiments/runs")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"tool_calling_{ts}.json"
    out_path.write_text(json.dumps({
        "captured_at": captured_at,
        "machine": machine,
        "ollama": OLLAMA_URL,
        "models": [m[1] for m in MODELS],
        "tasks": [{"expected_tool": e, "prompt": p} for e, p in TASKS],
        "tools_offered": [t["function"]["name"] for t in TOOLS],
        "model_results": model_results,
    }, indent=2))
    print(f"\nresults written to {out_path}")


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def _percentile(values, p):
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f, c = int(k), int(k) + 1
    if c >= len(s):
        return s[-1]
    return s[f] + (s[c] - s[f]) * (k - f)


def _detect_machine() -> dict:
    info = {"cpu": "unknown", "ram": "unknown", "os": "unknown", "chip": "unknown"}
    try:
        info["cpu"] = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip()
    except Exception:
        pass
    try:
        info["ram"] = subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"], text=True
        ).strip() + " bytes"
    except Exception:
        pass
    try:
        info["os"] = subprocess.check_output(["sw_vers", "-productName"], text=True).strip() + " " + \
                  subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip()
    except Exception:
        pass
    try:
        info["chip"] = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    except Exception:
        pass
    return info


if __name__ == "__main__":
    main()
