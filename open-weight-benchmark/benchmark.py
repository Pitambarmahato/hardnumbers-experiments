#!/usr/bin/env python3
"""
Open-weight LLM head-to-head benchmark.

Compares gpt-oss-20B, Qwen3-30B-A3B, and Mistral-Small-24B on a fixed suite
of accuracy + speed tasks. All prompts and scoring are deterministic.

Usage:
    python3 benchmark.py run                    # full sweep
    python3 benchmark.py run --model gpt-oss:20b
    python3 benchmark.py run --task mmlu
    python3 benchmark.py smoke --model gpt-oss:20b
"""

from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

OLLAMA_URL = "http://localhost:11434"
DATA_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Ollama client ----------

def ollama_generate(
    model: str,
    prompt: str,
    *,
    num_predict: int = 256,
    temperature: float = 0.0,
    num_ctx: int = 4096,
    keep_alive: str = "5m",
    system: str | None = None,
) -> dict:
    """Call /api/generate, return full response dict."""
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
            "num_ctx": num_ctx,
            "top_p": 1.0,
            "seed": 42,
        },
    }
    if system is not None:
        body["system"] = system
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def stop_model(model: str) -> None:
    """Unload a model to measure cold start next time."""
    try:
        body = json.dumps({"model": model, "keep_alive": 0}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        pass


# ---------- Task definitions ----------

@dataclass
class TaskResult:
    task: str
    model: str
    correct: int = 0
    total: int = 0
    total_time_s: float = 0.0
    total_tokens: int = 0
    prompt_tokens: int = 0
    gen_tokens: int = 0
    items: list[dict] = field(default_factory=list)
    cold_load_s: float | None = None
    extras: dict = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return (self.correct / self.total) if self.total else 0.0

    @property
    def tok_per_s(self) -> float:
        return self.gen_tokens / self.total_time_s if self.total_time_s > 0 else 0.0


def fmt_prompt_mmlu(item: dict) -> str:
    ch = item["choices"]
    letters = ["A", "B", "C", "D"][: len(ch)]
    body = "\n".join(f"({L}) {c}" for L, c in zip(letters, ch))
    return (
        f"Answer the following multiple-choice question. Respond with only a single letter "
        f"(A, B, C, or D) and nothing else.\n\n"
        f"Question: {item['question']}\n{body}\n\nAnswer:"
    )


def parse_mmlu(output: str) -> str | None:
    out = output.strip()
    m = re.search(r"\b([ABCD])\b", out[:20])
    return m.group(1) if m else None


def run_mmlu(model: str) -> TaskResult:
    res = TaskResult(task="mmlu", model=model)
    with open(DATA_DIR / "mmlu_50.jsonl") as f:
        items = [json.loads(l) for l in f if l.strip()]
    res.total = len(items)
    start = time.perf_counter()
    for it in items:
        prompt = fmt_prompt_mmlu(it)
        try:
            r = ollama_generate(model, prompt, num_predict=8, temperature=0.0)
            out = r.get("response", "")
            ans = parse_mmlu(out)
            ok = ans == it["answer"]
            if ok:
                res.correct += 1
            res.total_tokens += r.get("eval_count", 0)
            res.prompt_tokens += r.get("prompt_eval_count", 0)
            res.gen_tokens += r.get("eval_count", 0)
            res.items.append({
                "id": it["id"],
                "subject": it["subject"],
                "expected": it["answer"],
                "got": ans,
                "raw": out[:200],
                "ok": ok,
            })
        except Exception as e:
            res.items.append({"id": it["id"], "ok": False, "error": str(e)})
    res.total_time_s = time.perf_counter() - start
    return res


def fmt_prompt_gsm8k(item: dict) -> str:
    return (
        "Solve the following math word problem. Show your work, then end your response "
        "with a line that starts with '####' followed by the final numerical answer.\n\n"
        f"Question: {item['question']}\n\nAnswer:"
    )


def parse_gsm8k(output: str) -> str | None:
    # Find the last #### or a number near the end
    m = re.findall(r"####\s*([\-\d.,]+)", output)
    if m:
        return m[-1].replace(",", "").strip().rstrip(".")
    # fallback: last number in the response
    nums = re.findall(r"[\-\d]+\.?\d*", output)
    return nums[-1] if nums else None


def score_gsm8k(got: str | None, expected: str) -> bool:
    if got is None:
        return False
    try:
        return abs(float(got) - float(expected)) < 1e-3
    except ValueError:
        return got.strip() == expected.strip()


def run_gsm8k(model: str) -> TaskResult:
    res = TaskResult(task="gsm8k", model=model)
    with open(DATA_DIR / "gsm8k_30.jsonl") as f:
        items = [json.loads(l) for l in f if l.strip()]
    res.total = len(items)
    start = time.perf_counter()
    for it in items:
        prompt = fmt_prompt_gsm8k(it)
        try:
            r = ollama_generate(model, prompt, num_predict=512, temperature=0.0)
            out = r.get("response", "")
            ans = parse_gsm8k(out)
            ok = score_gsm8k(ans, it["answer"])
            if ok:
                res.correct += 1
            res.total_tokens += r.get("eval_count", 0)
            res.prompt_tokens += r.get("prompt_eval_count", 0)
            res.gen_tokens += r.get("eval_count", 0)
            res.items.append({
                "id": it["id"],
                "question": it["question"],
                "expected": it["answer"],
                "got": ans,
                "raw_tail": out[-300:],
                "ok": ok,
            })
        except Exception as e:
            res.items.append({"id": it["id"], "ok": False, "error": str(e)})
    res.total_time_s = time.perf_counter() - start
    return res


def fmt_prompt_humaneval(item: dict) -> str:
    return (
        "Complete the following Python function. Write only the function body. "
        "Do not include the function signature, the docstring, or any imports.\n\n"
        f"```python\n{item['prompt'].rstrip()}\n    "
    )


def extract_python_code(output: str) -> str:
    """Try to extract a Python function body from model output."""
    # If wrapped in ```python ... ```
    m = re.search(r"```(?:python)?\s*\n(.*?)```", output, re.DOTALL)
    if m:
        return m.group(1).strip()
    return output.strip()


def assemble_humaneval_solution(prompt: str, body: str) -> str:
    """Take the original prompt (signature + docstring) and append the body."""
    # The prompt ends with the docstring's closing triple-quote and a newline, then
    # expects the body. We re-emit the whole thing.
    p = prompt.rstrip()
    if p.endswith('"""'):
        p = p + "\n    "
    return p + body + "\n"


def run_humaneval(model: str) -> TaskResult:
    res = TaskResult(task="humaneval", model=model)
    with open(DATA_DIR / "humaneval_20.jsonl") as f:
        items = [json.loads(l) for l in f if l.strip()]
    res.total = len(items)
    start = time.perf_counter()
    for it in items:
        prompt = fmt_prompt_humaneval(it)
        try:
            r = ollama_generate(model, prompt, num_predict=512, temperature=0.0)
            out = r.get("response", "")
            body = extract_python_code(out)
            solution = assemble_humaneval_solution(it["prompt"], body)
            ok = _run_humaneval_test(it["task_id"], it["entry_point"], it["test"], solution)
            if ok:
                res.correct += 1
            res.total_tokens += r.get("eval_count", 0)
            res.prompt_tokens += r.get("prompt_eval_count", 0)
            res.gen_tokens += r.get("eval_count", 0)
            res.items.append({
                "task_id": it["task_id"],
                "ok": ok,
                "raw_tail": out[-200:],
            })
        except Exception as e:
            res.items.append({"task_id": it["task_id"], "ok": False, "error": str(e)})
    res.total_time_s = time.perf_counter() - start
    return res


def _run_humaneval_test(task_id: str, entry_point: str, test: str, solution: str) -> bool:
    """Run the HumanEval test in a subprocess. Returns True if it passes."""
    code = (
        "import sys, json\n"
        f"_SOLUTION = {json.dumps(solution)}\n"
        "_exec_result = {'pass': False, 'err': None}\n"
        "try:\n"
        "    exec(_SOLUTION, globals())\n"
        "    exec(compile(" + repr(test) + ", '<test>', 'exec'), globals())\n"
        "    _exec_result['pass'] = True\n"
        "except SystemExit:\n"
        "    _exec_result['pass'] = True\n"
        "except BaseException as e:\n"
        "    _exec_result['err'] = f'{type(e).__name__}: {e}'\n"
        "print(json.dumps(_exec_result))\n"
    )
    try:
        proc = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=20,
        )
        out = proc.stdout.strip().splitlines()[-1] if proc.stdout else ""
        result = json.loads(out)
        return result.get("pass", False)
    except Exception as e:
        return False


# ---- IFEval validators ----

def _v_num_list_items(output: str, n: int) -> bool:
    """Match numbered list '1. ... 2. ... 3. ...' of exactly n items."""
    matches = re.findall(r"^\s*(\d+)\.\s", output, re.MULTILINE)
    return len(set(matches)) == n


def _v_ends_with(output: str, phrase: str) -> bool:
    return output.rstrip().endswith(phrase)


def _v_no_commas(output: str) -> bool:
    return "," not in output


def _v_min_word(output: str, word: str, n: int) -> bool:
    return len(re.findall(rf"\b{re.escape(word)}\b", output, re.IGNORECASE)) >= n


def _v_only_number(output: str) -> bool:
    return bool(re.match(r"^\s*[\-\d]+\.?\d*\s*\.?\s*$", output))


def _v_no_letter(output: str, letter: str) -> bool:
    return letter not in output and letter.upper() not in output


def _v_words(output: str, n: int) -> bool:
    return len(output.split()) == n


def _v_words_in(output: str, lo: int, hi: int) -> bool:
    return lo <= len(output.split()) <= hi


def _v_words_max(output: str, n: int) -> bool:
    return len(output.split()) <= n


def _v_paragraphs(output: str, n: int) -> bool:
    paras = [p for p in re.split(r"\n\s*\n", output.strip()) if p.strip()]
    return len(paras) == n


def _v_csv_items(output: str, n: int) -> bool:
    return len([x for x in output.strip().split(",") if x.strip()]) == n


def _v_newline_items(output: str, n: int) -> bool:
    return len([l for l in output.strip().splitlines() if l.strip()]) == n


def _v_json_with(output: str, **kv) -> bool:
    try:
        # Extract the first {...} block
        m = re.search(r"\{.*\}", output, re.DOTALL)
        if not m:
            return False
        d = json.loads(m.group(0))
        return all(d.get(k) == v for k, v in kv.items())
    except Exception:
        return False


def _v_single_sentence(output: str) -> bool:
    # Crude: count sentence-ending punctuation not inside parens
    sents = re.findall(r"[.!?](?:\s|$)", output.strip())
    return len(sents) == 1


def _v_haiku_575(output: str) -> bool:
    """Check 3 lines with 5-7-5 syllable count (English approximation)."""
    lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
    if len(lines) != 3:
        return False
    # Very rough English syllable counter
    def count_syllables(s: str) -> int:
        s = s.lower()
        s = re.sub(r"[^a-z]", " ", s)
        words = [w for w in s.split() if w]
        count = 0
        vowels = "aeiouy"
        for w in words:
            wcount = 0
            prev_vowel = False
            for c in w:
                is_v = c in vowels
                if is_v and not prev_vowel:
                    wcount += 1
                prev_vowel = is_v
            if w.endswith("e") and wcount > 1:
                wcount -= 1
            count += max(1, wcount)
        return count
    sc = [count_syllables(l) for l in lines]
    return sc == [5, 7, 5]


def _v_lines_capitalized(output: str, n: int) -> bool:
    lines = [l for l in output.strip().splitlines() if l.strip()]
    return len(lines) == n and all(l[0].isupper() for l in lines if l)


def _v_lines_are_primes(output: str, primes: list[int]) -> bool:
    lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
    try:
        nums = [int(re.sub(r"[^\d]", "", l)) for l in lines]
    except ValueError:
        return False
    return nums == primes


def _v_no_preamble(output: str, contains: str) -> bool:
    """First non-empty line must not contain the forbidden word."""
    first = next((l for l in output.strip().splitlines() if l.strip()), "")
    return contains.lower() not in first.lower()


VALIDATORS: dict[str, Callable[..., bool]] = {
    "num_list_items": lambda o, n: _v_num_list_items(o, n),
    "ends_with": lambda o, phrase: _v_ends_with(o, phrase),
    "no_commas": lambda o: _v_no_commas(o),
    "min_word": lambda o, word, n: _v_min_word(o, word, n),
    "only_number": lambda o: _v_only_number(o),
    "no_letter": lambda o, letter: _v_no_letter(o, letter),
    "words": lambda o, n: _v_words(o, n),
    "words_in": lambda o, lo, hi: _v_words_in(o, lo, hi),
    "words_max": lambda o, n: _v_words_max(o, n),
    "paragraphs": lambda o, n: _v_paragraphs(o, n),
    "csv_items": lambda o, n: _v_csv_items(o, n),
    "newline_items": lambda o, n: _v_newline_items(o, n),
    "json_with": lambda o, **kv: _v_json_with(o, **kv),
    "single_sentence": lambda o: _v_single_sentence(o),
    "haiku_575": lambda o: _v_haiku_575(o),
    "lines_capitalized": lambda o, n: _v_lines_capitalized(o, n),
    "lines_are_primes": lambda o, primes: _v_lines_are_primes(o, primes),
    "no_preamble": lambda o, contains: _v_no_preamble(o, contains),
}


def run_ifeval(model: str) -> TaskResult:
    res = TaskResult(task="ifeval", model=model)
    with open(DATA_DIR / "ifeval_20.jsonl") as f:
        items = [json.loads(l) for l in f if l.strip()]
    res.total = len(items)
    start = time.perf_counter()
    for it in items:
        try:
            r = ollama_generate(model, it["prompt"], num_predict=512, temperature=0.0)
            out = r.get("response", "")
            ok = _check_ifeval(it["validator"], out)
            if ok:
                res.correct += 1
            res.total_tokens += r.get("eval_count", 0)
            res.prompt_tokens += r.get("prompt_eval_count", 0)
            res.gen_tokens += r.get("eval_count", 0)
            res.items.append({
                "id": it["id"],
                "constraint": it["constraint"],
                "validator": it["validator"],
                "ok": ok,
                "raw": out[:400],
            })
        except Exception as e:
            res.items.append({"id": it["id"], "ok": False, "error": str(e)})
    res.total_time_s = time.perf_counter() - start
    return res


def _check_ifeval(validator: str, output: str) -> bool:
    """Parse validator spec and run it. e.g. 'min_word(\\'orange\\',3)' or 'json_with(name=Alice,age=30)' """
    import ast
    m = re.match(r"^(\w+)(?:\((.*)\))?$", validator.strip())
    if not m:
        return False
    name, args_str = m.group(1), m.group(2)
    fn = VALIDATORS.get(name)
    if fn is None:
        return False
    if not args_str:
        return fn(output)
    try:
        # Parse as a function call so we can extract positional and keyword args
        tree = ast.parse(f"_({args_str})", mode="eval")
        call = tree.body
        args = [ast.literal_eval(a) for a in call.args]
        kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
        return fn(output, *args, **kwargs)
    except Exception:
        return False


# ---- Speed benchmark ----

SPEED_PROMPTS = [
    ("short_chat", "Explain the difference between TCP and UDP in one paragraph.", 256),
    ("medium_summarize", "Summarize the following article in 5 bullet points: " + (
        "Large language models have transformed natural language processing. "
        "The Transformer architecture introduced self-attention as a core mechanism, "
        "replacing recurrence with parallel sequence processing. Pretraining on web-scale "
        "text data produces models with broad linguistic competence. Fine-tuning adapts "
        "these models to downstream tasks. Recent work has explored scaling laws, mixture-of-experts, "
        "and chain-of-thought reasoning. The field continues to evolve rapidly with new architectures, "
        "training recipes, and alignment techniques appearing monthly. Open-weight releases from Meta, "
        "Mistral, Alibaba, and now OpenAI have made frontier capabilities accessible to anyone with a GPU. "
        "Local inference has become practical on consumer hardware, with quantization shrinking 70B-class "
        "models to fit on a single high-end laptop. The economics of running models locally versus via API "
        "depend on usage patterns, but the gap has narrowed significantly. " * 8
    ), 256),
    ("long_generation", "Write a detailed Python function that parses a CSV file with header detection, type inference, and graceful error handling. Include docstring and 3 example calls.", 1024),
]


def run_speed(model: str) -> TaskResult:
    res = TaskResult(task="speed", model=model)
    res.extras["trials"] = []
    for trial_idx in range(3):
        # Cold load before trial 0
        cold_load_s = None
        if trial_idx == 0:
            stop_model(model)
        t_trial_start = time.perf_counter()
        for label, prompt, num_predict in SPEED_PROMPTS:
            t0 = time.perf_counter()
            try:
                r = ollama_generate(
                    model, prompt, num_predict=num_predict, temperature=0.0,
                    num_ctx=8192, keep_alive="5m",
                )
                dt = time.perf_counter() - t0
                evals = r.get("eval_count", 0)
                p_eval = r.get("prompt_eval_count", 0)
                # Convert ns to s for ollama-native measurements
                # Ollama returns: total_duration, load_duration, prompt_eval_duration, eval_duration (all in ns)
                tps = evals / (r.get("eval_duration", 1) / 1e9) if r.get("eval_duration") else 0
                tpt = p_eval / (r.get("prompt_eval_duration", 1) / 1e9) if r.get("prompt_eval_duration") else 0
                res.extras["trials"].append({
                    "trial": trial_idx,
                    "label": label,
                    "wall_s": round(dt, 2),
                    "prompt_tokens": p_eval,
                    "gen_tokens": evals,
                    "tok_per_s_gen": round(tps, 2),
                    "tok_per_s_prompt": round(tpt, 2),
                    "load_duration_s": round(r.get("load_duration", 0) / 1e9, 2) if r.get("load_duration") else 0,
                    "total_duration_s": round(r.get("total_duration", 0) / 1e9, 2) if r.get("total_duration") else 0,
                })
                if trial_idx == 0 and label == SPEED_PROMPTS[0][0]:
                    cold_load_s = r.get("load_duration", 0) / 1e9
            except Exception as e:
                res.extras["trials"].append({
                    "trial": trial_idx, "label": label, "error": str(e)
                })
        res.total_time_s += time.perf_counter() - t_trial_start
        if cold_load_s is not None:
            res.cold_load_s = round(cold_load_s, 2)
        # Pause between trials
        if trial_idx < 2:
            time.sleep(2)
    res.total = len(res.extras["trials"])
    res.correct = sum(1 for t in res.extras["trials"] if "tok_per_s_gen" in t)
    return res


# ---------- Orchestration ----------

TASKS = {
    "mmlu": run_mmlu,
    "gsm8k": run_gsm8k,
    "humaneval": run_humaneval,
    "ifeval": run_ifeval,
    "speed": run_speed,
}

DEFAULT_MODELS = [
    "gpt-oss:20b",
    "qwen3:30b-a3b-instruct-2507-q4_K_M",
    "mistral-small:24b-instruct-2501-q4_K_M",
]


def _result_to_dict(res: TaskResult) -> dict:
    d = asdict(res)
    d["accuracy"] = res.accuracy
    d["tok_per_s"] = res.tok_per_s
    return d


def smoke(model: str) -> None:
    """Single quick test to confirm a model is loaded and answering."""
    print(f"[smoke] {model}: ", end="", flush=True)
    r = ollama_generate(model, "What is 2+2? Reply with one number.", num_predict=10)
    print(f"ok in {r.get('total_duration', 0)/1e9:.2f}s, answer={r.get('response','')!r}")


def run(args: argparse.Namespace) -> None:
    models = args.model.split(",") if args.model else DEFAULT_MODELS
    tasks = args.task.split(",") if args.task else list(TASKS.keys())
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"results_{timestamp}.json"
    all_results: list[dict] = []
    t_start = time.perf_counter()
    for model in models:
        for task_name in tasks:
            print(f"\n[{model}] [{task_name}] starting", flush=True)
            t0 = time.perf_counter()
            try:
                res = TASKS[task_name](model)
                dt = time.perf_counter() - t0
                print(
                    f"[{model}] [{task_name}] done in {dt:.1f}s — "
                    f"{res.correct}/{res.total} correct "
                    f"({res.accuracy*100:.1f}%), "
                    f"{res.tok_per_s:.2f} tok/s, "
                    f"{res.gen_tokens} gen tokens"
                )
            except Exception as e:
                print(f"[{model}] [{task_name}] FAILED: {e}")
                res = TaskResult(task=task_name, model=model, total=0)
                res.extras["error"] = str(e)
            all_results.append(_result_to_dict(res))
            # Save incrementally so we don't lose progress
            with open(out_path, "w") as f:
                json.dump({
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "total_elapsed_s": time.perf_counter() - t_start,
                    "results": all_results,
                }, f, indent=2)
    print(f"\nResults saved to {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--model", default="")
    pr.add_argument("--task", default="")
    pr.set_defaults(func=run)
    ps = sub.add_parser("smoke")
    ps.add_argument("--model", required=True)
    ps.set_defaults(func=lambda a: smoke(a.model))
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
