"""Quick smoke test for Ollama speculative decoding support.

Runs the same prompt against qwen3:14b with and without a draft model, several
trials, and prints the median wall time per config. The real benchmark will
extend this with a non-trivial prompt and structured metrics.
"""
import json
import statistics
import time
import urllib.request

URL = "http://localhost:11434/api/generate"
PROMPT = (
    "Write a Python function `merge_dicts(*dicts)` that takes any number of "
    "dicts and returns a single dict with all keys merged. If the same key "
    "appears in multiple dicts, the later value wins. Include a type hint for "
    "the return. Output only the code, no explanation."
)
NUM_PREDICT = 200
TRIALS = 3


def run(use_draft: bool, trial: int) -> dict:
    payload = {
        "model": "qwen3:14b",
        "prompt": PROMPT,
        "stream": False,
        "options": {
            "num_predict": NUM_PREDICT,
            "temperature": 0.0,
            "seed": 42,
        },
    }
    if use_draft:
        payload["draft_model"] = "qwen2.5:0.5b"

    body = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    wall = time.perf_counter() - t0
    return {
        "trial": trial,
        "draft": use_draft,
        "wall_s": wall,
        "total_duration_s": data.get("total_duration", 0) / 1e9,
        "load_duration_s": data.get("load_duration", 0) / 1e9,
        "prompt_eval_count": data.get("prompt_eval_count"),
        "prompt_eval_duration_s": data.get("prompt_eval_duration", 0) / 1e9,
        "eval_count": data.get("eval_count"),
        "eval_duration_s": data.get("eval_duration", 0) / 1e9,
    }


def main():
    # Warmup: load the target model into memory
    print("Warming up target model (qwen3:14b)...", end=" ", flush=True)
    run(False, 0)
    print("ok")

    print("Warming up draft model (qwen2.5:0.5b)...", end=" ", flush=True)
    run(True, 0)
    print("ok")

    print("\n=== Without draft ===")
    no_draft = [run(False, t) for t in range(1, TRIALS + 1)]
    for r in no_draft:
        print(f"  trial {r['trial']}: wall {r['wall_s']:.2f}s, "
              f"eval {r['eval_count']} tokens in {r['eval_duration_s']:.2f}s "
              f"({r['eval_count']/r['eval_duration_s']:.1f} tok/s)")

    print("\n=== With draft (qwen2.5:0.5b) ===")
    with_draft = [run(True, t) for t in range(1, TRIALS + 1)]
    for r in with_draft:
        print(f"  trial {r['trial']}: wall {r['wall_s']:.2f}s, "
              f"eval {r['eval_count']} tokens in {r['eval_duration_s']:.2f}s "
              f"({r['eval_count']/r['eval_duration_s']:.1f} tok/s)")

    no_eval_dur = statistics.median([r["eval_duration_s"] for r in no_draft])
    with_eval_dur = statistics.median([r["eval_duration_s"] for r in with_draft])
    speedup = no_eval_dur / with_eval_dur if with_eval_dur else 0

    print(f"\nMedian eval duration — no draft: {no_eval_dur:.2f}s, with draft: {with_eval_dur:.2f}s")
    print(f"Speedup: {speedup:.2f}x")


if __name__ == "__main__":
    main()
