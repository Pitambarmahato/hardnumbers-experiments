"""Full speculative decoding benchmark for the Hard Numbers article.

Compares qwen3:14b at Q4_K_M with three draft configurations:
  - no draft (baseline)
  - qwen2.5:0.5b draft
  - qwen2.5:1.5b draft

The same prompt, deterministic settings, 5 trials each. Reports median wall
time, eval time, and tok/s. Saves raw results to results/spec_decode.json
for the article.
"""
import json
import statistics
import time
import urllib.request
from pathlib import Path

URL = "http://localhost:11434/api/generate"
PROMPT = (
    "Write a Python function `merge_dicts(*dicts)` that takes any number of "
    "dicts and returns a single dict with all keys merged. If the same key "
    "appears in multiple dicts, the later value wins. Include a type hint for "
    "the return. Output only the code, no explanation."
)
NUM_PREDICT = 200
TRIALS = 5

CONFIGS = [
    {"label": "no_draft", "draft": None},
    {"label": "draft_qwen2.5_0.5b", "draft": "qwen2.5:0.5b"},
    {"label": "draft_qwen2.5_1.5b", "draft": "qwen2.5:1.5b"},
]


def run(cfg: dict, trial: int) -> dict:
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
    if cfg["draft"]:
        payload["draft_model"] = cfg["draft"]

    body = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    wall = time.perf_counter() - t0
    return {
        "config": cfg["label"],
        "trial": trial,
        "wall_s": wall,
        "total_duration_s": data.get("total_duration", 0) / 1e9,
        "load_duration_s": data.get("load_duration", 0) / 1e9,
        "prompt_eval_count": data.get("prompt_eval_count"),
        "prompt_eval_duration_s": data.get("prompt_eval_duration", 0) / 1e9,
        "eval_count": data.get("eval_count"),
        "eval_duration_s": data.get("eval_duration", 0) / 1e9,
        "tok_per_s": data["eval_count"] / (data.get("eval_duration", 1) / 1e9) if data.get("eval_count") else 0,
    }


def main():
    results = []

    # Warmup each config to load the model files
    print("Warming up configurations...")
    for cfg in CONFIGS:
        print(f"  - {cfg['label']}...", end=" ", flush=True)
        run(cfg, 0)
        print("ok")

    print(f"\nRunning {TRIALS} trials per config...")
    for cfg in CONFIGS:
        print(f"\n=== {cfg['label']} ===")
        trials = []
        for t in range(1, TRIALS + 1):
            r = run(cfg, t)
            trials.append(r)
            results.append(r)
            print(f"  trial {t}: wall {r['wall_s']:.2f}s, "
                  f"eval {r['eval_count']} tokens in {r['eval_duration_s']:.2f}s "
                  f"({r['tok_per_s']:.1f} tok/s)")
        med_eval = statistics.median([t["eval_duration_s"] for t in trials])
        med_tps = statistics.median([t["tok_per_s"] for t in trials])
        print(f"  median eval: {med_eval:.2f}s, {med_tps:.1f} tok/s")

    # Speedup summary
    print("\n=== Summary ===")
    by_cfg = {}
    for r in results:
        by_cfg.setdefault(r["config"], []).append(r)
    base_tps = statistics.median([r["tok_per_s"] for r in by_cfg["no_draft"]])
    for cfg, trials in by_cfg.items():
        med_tps = statistics.median([r["tok_per_s"] for r in trials])
        speedup = med_tps / base_tps
        print(f"  {cfg}: {med_tps:.1f} tok/s, {speedup:.2f}x vs baseline")

    out = Path("results/spec_decode.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "experiment": "spec_decode_m2",
        "description": "Speculative decoding on M2 24GB: Qwen3 14B target, qwen2.5 draft models",
        "target": "qwen3:14b (Q4_K_M, 9.3 GB)",
        "drafts": ["qwen2.5:0.5b (397 MB)", "qwen2.5:1.5b (~1 GB)"],
        "prompt_chars": len(PROMPT),
        "num_predict": NUM_PREDICT,
        "trials": TRIALS,
        "results": results,
    }, indent=2))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
