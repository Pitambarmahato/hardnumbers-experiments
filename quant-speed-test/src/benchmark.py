"""Local LLM speed test on M2: 2 models, 1 short prompt, 3 trials.

Uses Ollama's native API (not OpenAI-compat) so we can pass
`think: false` for gpt-oss and control KV cache params.

For the article: a short, code-completion style task that forces both
models to actually generate. Max 150 output tokens, 1 prompt, 3 trials.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = REPO_ROOT / "results"
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")

# Models we have cached. Different native quant formats (gpt-oss is MXFP4,
# Qwen3 is Q4_K_M). The natural comparison: how fast is each at its
# recommended quant on M2 unified memory.
MODELS = [
    ("gpt-oss:20b", {"name": "gpt-oss-20b (MXFP4)", "size_gb": 13.8, "quant": "MXFP4"}),
    ("qwen3:14b",   {"name": "Qwen3-14B (Q4_K_M)", "size_gb": 9.3,  "quant": "Q4_K_M"}),
]

# Short code-completion prompt. Same one for both models. ~120-150 tokens
# of expected output. Tests speed on a real coding workload.
PROMPT = (
    "Write a Python function `merge_dicts(*dicts)` that takes any number of "
    "dicts and returns a single dict with all keys merged. If the same key "
    "appears in multiple dicts, the later value wins. Include a type hint "
    "for the return. Output only the code, no explanation."
)

TRIALS = 3
MAX_TOKENS = 200


def call_ollama_native(model: str, prompt: str, options: dict) -> dict:
    """Call Ollama's /api/chat endpoint with full options control.
    Returns dict with timing + content."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": options,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    wall_start = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    wall_s = time.monotonic() - wall_start
    return {
        "wall_s": wall_s,
        "content": data.get("message", {}).get("content", ""),
        "eval_count": data.get("eval_count", 0),
        "eval_duration_ns": data.get("eval_duration", 1),
        "prompt_eval_count": data.get("prompt_eval_count", 0),
        "prompt_eval_duration_ns": data.get("prompt_eval_duration", 1),
        "total_duration_ns": data.get("total_duration", 1),
        "load_duration_ns": data.get("load_duration", 0),
    }


def run_trial(model: str, label: str, quant: str, trial: int) -> dict:
    options = {
        "num_predict": MAX_TOKENS,
        "temperature": 0.0,
        # Disable thinking for gpt-oss to get apples-to-apples speed
        "think": False,
    }
    try:
        r = call_ollama_native(model, PROMPT, options)
        eval_s = r["eval_duration_ns"] / 1e9
        prompt_s = r["prompt_eval_duration_ns"] / 1e9
        load_s = r["load_duration_ns"] / 1e9
        total_s = r["total_duration_ns"] / 1e9
        tok_per_s = r["eval_count"] / eval_s if eval_s > 0 else 0
        return {
            "model": model,
            "label": label,
            "quant": quant,
            "trial": trial,
            "success": True,
            "wall_time_s": round(r["wall_s"], 3),
            "total_duration_s": round(total_s, 3),
            "load_duration_s": round(load_s, 3),
            "prompt_eval_s": round(prompt_s, 3),
            "eval_s": round(eval_s, 3),
            "tokens_out": r["eval_count"],
            "tokens_in": r["prompt_eval_count"],
            "tokens_per_s": round(tok_per_s, 2),
            "response_chars": len(r["content"]),
            "error": None,
        }
    except Exception as e:
        return {
            "model": model,
            "label": label,
            "quant": quant,
            "trial": trial,
            "success": False,
            "wall_time_s": 0,
            "total_duration_s": 0,
            "load_duration_s": 0,
            "prompt_eval_s": 0,
            "eval_s": 0,
            "tokens_out": 0,
            "tokens_in": 0,
            "tokens_per_s": 0,
            "response_chars": 0,
            "error": str(e)[:200],
        }


def main():
    print("== Local LLM speed on M2 ==")
    print(f"Models: {[(m, d['name']) for m, d in MODELS]}")
    print(f"Trials per model: {TRIALS}")
    print(f"Max output tokens: {MAX_TOKENS}")
    print(f"Total runs: {len(MODELS) * TRIALS}")
    print()

    all_records = []
    for model, info in MODELS:
        label, quant = info["name"], info["quant"]
        print(f"--- {label} ---")
        # Warmup: load model first (don't time this)
        try:
            call_ollama_native(model, "ok", {"num_predict": 5, "think": False})
            print(f"  (warmup done)")
        except Exception as e:
            print(f"  SKIP (model not available): {e}")
            continue

        for trial in range(TRIALS):
            rec = run_trial(model, label, quant, trial)
            tag = "OK" if rec["success"] else "FAIL"
            print(
                f"  [{tag}] trial {trial + 1}: wall={rec['wall_time_s']:.2f}s "
                f"load={rec['load_duration_s']:.2f}s "
                f"tok/s={rec['tokens_per_s']:.1f} out={rec['tokens_out']}",
                flush=True,
            )
            all_records.append(rec)

    DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = DEFAULT_RESULTS_DIR / f"local_llm_speed_{ts}.json"
    payload = {
        "models": [{"name": m, **d} for m, d in MODELS],
        "prompt_chars": len(PROMPT),
        "max_tokens": MAX_TOKENS,
        "trials": TRIALS,
        "records": all_records,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults: {out_path}")
    print(f"Success: {sum(1 for r in all_records if r['success'])}/{len(all_records)}")


if __name__ == "__main__":
    main()
