"""Benchmark Qwen3 14B vs Llama 3.2 3B on Apple Silicon M2.

Generates JSON results that feed directly into the article.
Runs locally via Ollama. Re-runnable; outputs a stable JSON file
at experiments/runs/m2_benchmark_<timestamp>.json.

Usage:
    python3 scripts/benchmark_m2.py
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# Local Ollama API
OLLAMA_URL = "http://localhost:11434/api/generate"

# Models to compare. (display_name, ollama_tag, params_b)
MODELS = [
    ("Qwen3 14B (Q4_K_M)", "qwen3:14b", 14.8),
    ("Llama 3.2 3B (Q4_0)", "llama3.2:latest", 3.2),
]

# Test prompts: (category, prompt, expected_keywords)
# Keywords are checked case-insensitively; missing keywords = wrong.
TASKS = [
    ("reasoning", "If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly?", ["yes"]),
    ("math", "What is 17% of 240?", ["40.8"]),
    ("code", "Write a Python function `factorial(n)` that returns n! using recursion. Output only the code.", ["def factorial", "return"]),
    ("code", "Fix this bug: `def add(a, b): return a + b + 1`. What's wrong?", ["off-by-one", "adds an extra", "+ 1"]),
    ("instruction", "List exactly 3 fruits, one per line, no other text.", ["apple", "banana", "orange"]),
    ("instruction", "Translate to French: 'The meeting starts at 3pm.'", ["La réunion", "15"]),
    ("reasoning", "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?", ["0.05", "5 cents"]),
    ("math", "Solve: 3x + 7 = 22. What is x?", ["5"]),
]

def query(model: str, prompt: str, timeout: int = 180) -> dict:
    """Send a prompt to Ollama. Returns timing + response data."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 256,
            "temperature": 0.0,  # deterministic for benchmark
        },
    }
    start = time.perf_counter()
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", OLLAMA_URL,
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=timeout,
    )
    wall_ms = int((time.perf_counter() - start) * 1000)
    if result.returncode != 0:
        return {"ok": False, "wall_ms": wall_ms, "error": result.stderr[:200]}
    try:
        r = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "wall_ms": wall_ms, "error": f"json: {exc}"}

    return {
        "ok": True,
        "wall_ms": wall_ms,
        "eval_ms": r.get("eval_duration", 0) / 1e6,
        "gen_ms": r.get("total_duration", 0) / 1e6 - r.get("eval_duration", 0) / 1e6,
        "prompt_tokens": r.get("prompt_eval_count", 0),
        "response_tokens": r.get("eval_count", 0),
        "tokens_per_sec": r.get("eval_count", 0) / (r.get("total_duration", 0) / 1e9) if r.get("total_duration", 0) else 0,
        "response": r.get("response", ""),
        "load_ms": r.get("load_duration", 0) / 1e6,
    }


def check_keywords(response: str, expected: list[str]) -> bool:
    if not expected:
        return True
    lower = response.lower()
    return all(k.lower() in lower for k in expected)


def run_benchmark():
    runs_dir = Path("experiments/runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = runs_dir / f"m2_benchmark_{timestamp}.json"

    results: dict = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "machine": {
            "cpu": "Apple M2 (8 cores)",
            "ram": "24 GB unified",
            "gpu": "Apple integrated (Metal 3)",
        },
        "ollama": "localhost:11434",
        "models": [m[0] for m in MODELS],
        "tasks": [],
    }

    # Warmup pass (model load is the slowest part)
    print("Warming up...")
    for name, tag, _ in MODELS:
        warm = query(tag, "Say 'ready' and nothing else.", timeout=120)
        print(f"  {name}: {'ok' if warm['ok'] else 'fail'} ({warm.get('load_ms', 0):.0f}ms load)")

    # Real benchmark
    print("\nRunning benchmark...")
    for model_name, model_tag, params_b in MODELS:
        print(f"\n=== {model_name} ===")
        model_results = {"name": model_name, "tag": model_tag, "params_b": params_b, "tasks": []}
        for category, prompt, expected in TASKS:
            r = query(model_tag, prompt, timeout=180)
            correct = check_keywords(r.get("response", ""), expected) if r.get("ok") else False
            tps = r.get("tokens_per_sec", 0) if r.get("ok") else 0
            status = "✓" if correct else "✗"
            print(f"  [{status}] {category:12s} {tps:6.1f} tok/s | {r.get('wall_ms', 0):5d}ms | {prompt[:50]}")
            model_results["tasks"].append({
                "category": category,
                "prompt": prompt,
                "expected": expected,
                "response": r.get("response", ""),
                "ok": r.get("ok"),
                "correct": correct,
                "wall_ms": r.get("wall_ms", 0),
                "gen_ms": r.get("gen_ms", 0),
                "tokens_per_sec": round(tps, 2),
                "response_tokens": r.get("response_tokens", 0),
            })
        # Aggregate
        tps_values = [t["tokens_per_sec"] for t in model_results["tasks"] if t.get("ok")]
        correct_count = sum(1 for t in model_results["tasks"] if t["correct"])
        model_results["aggregate"] = {
            "tps_median": round(statistics.median(tps_values), 2) if tps_values else 0,
            "tps_mean": round(statistics.mean(tps_values), 2) if tps_values else 0,
            "tps_p10": round(sorted(tps_values)[max(0, len(tps_values) // 10)], 2) if tps_values else 0,
            "accuracy": round(correct_count / len(TASKS), 3),
            "correct": correct_count,
            "total": len(TASKS),
        }
        results["models_results" if False else "model_results"] = results.get("model_results", []) + [model_results]

    # Reorganize: results["model_results"] = [...]
    if "model_results" not in results:
        results["model_results"] = []
    # Remove the bad key we built
    if "models_results" in results:
        del results["models_results"]

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Results written to {output_path}")
    return results


if __name__ == "__main__":
    run_benchmark()
