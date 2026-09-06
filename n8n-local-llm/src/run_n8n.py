"""n8n + Ollama benchmark runner.

Calls each workflow via its webhook URL and measures the same metrics
as run_ollama.py: wall time, score, peak RSS. The n8n overhead is the
delta we want to surface in the article.

Output: results/n8n_<model>_<workflow>_r<n>.json + summaries, parallel
to the ollama_ files.
"""

import json
import os
import resource
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
DATA = json.loads((ROOT / "data" / "test_workflows.json").read_text())
URLS = json.loads((ROOT / "n8n_workflow_urls.json").read_text())
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def measure_peak_rss_mb() -> float:
    ru = resource.getrusage(resource.RUSAGE_SELF)
    return ru.ru_maxrss / (1024 * 1024)


# Reuse the scorers from run_ollama.py by importing the module.
sys.path.insert(0, str(ROOT / "src"))
from run_ollama import (  # noqa: E402
    score_classification,
    score_extraction,
    score_summarization,
    score_rag_qa,
    score_tool_calling,
)


SCORERS = {
    "classification": score_classification,
    "extraction": score_extraction,
    "summarization": score_summarization,
    "rag_qa": score_rag_qa,
    "tool_calling": score_tool_calling,
}


def n8n_call(webhook_url: str, model: str, user: str, workflow: str) -> tuple[dict, float]:
    """POST to the n8n webhook, return (response_body, wall_seconds)."""
    body = {"model": model, "user": user}
    t0 = time.perf_counter()
    r = requests.post(webhook_url, json=body, timeout=180)
    wall = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json(), wall


def build_user_prompt(workflow: str, inp: dict) -> str:
    if workflow == "rag_qa":
        return f"Context:\n{inp['context']}\n\nQuestion: {inp['question']}"
    return inp["input"]


def run_one(model: str, workflow: str, run_idx: int) -> dict:
    wf = DATA["workflows"][workflow]
    inp = wf["test_inputs"][run_idx % len(wf["test_inputs"])]
    user_prompt = build_user_prompt(workflow, inp)

    peak_before = measure_peak_rss_mb()
    resp, wall = n8n_call(URLS[workflow]["webhook_url"], model, user_prompt, workflow)
    peak_after = measure_peak_rss_mb()

    text = resp.get("response", "")
    if workflow == "classification":
        score = score_classification(inp["expected"], text)
    elif workflow == "extraction":
        score = score_extraction(inp["expected"], text)
    elif workflow == "summarization":
        score = score_summarization(inp["expected"], text)
    elif workflow == "rag_qa":
        score = score_rag_qa(inp["expected"], text)
    elif workflow == "tool_calling":
        score = score_tool_calling(inp["expected_first_action"], text)
    else:
        score = 0.0

    return {
        "model": model,
        "workflow": workflow,
        "run": run_idx,
        "input": (inp.get("input") or f"{inp.get('context', '')[:80]}... Q: {inp.get('question', '')}")[:200],
        "expected": inp.get("expected") or inp.get("expected_bullets") or inp.get("expected_first_action"),
        "response": text[:500],
        "wall_s": wall,
        "score": score,
        "peak_rss_mb": max(peak_before, peak_after),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_n8n.py [model|all] [--only w1,w2] [--runs N]")
        sys.exit(1)

    if sys.argv[1] == "all":
        models = [m["name"] for m in DATA["models"]]
    else:
        models = [sys.argv[1]]

    workflows = list(DATA["workflows"].keys())
    n_runs = DATA["runs_per_cell"]
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        only = set(sys.argv[idx + 1].split(","))
        workflows = [w for w in workflows if w in only]
    if "--runs" in sys.argv:
        idx = sys.argv.index("--runs")
        n_runs = int(sys.argv[idx + 1])

    for model in models:
        print(f"\n=== n8n | {model} ===", flush=True)
        # warmup
        try:
            warm, w = n8n_call(URLS["classification"]["webhook_url"], model, "Reply: ok", "classification")
            print(f"  warmup: {w:.1f}s, response='{warm.get('response', '')[:50]}'", flush=True)
        except Exception as e:
            print(f"  WARMUP FAILED: {e}")
            continue
        for workflow in workflows:
            results = []
            for r in range(n_runs):
                print(f"  {workflow} run {r + 1}/{n_runs}...", end=" ", flush=True)
                try:
                    rec = run_one(model, workflow, r)
                    out_path = RESULTS / f"n8n_{model.replace(':', '_')}_{workflow}_r{r + 1}.json"
                    out_path.write_text(json.dumps(rec, indent=2))
                    print(f"wall={rec['wall_s']:.1f}s score={rec['score']:.2f}", flush=True)
                    results.append(rec)
                except Exception as e:
                    print(f"FAIL: {e}", flush=True)
            if results:
                wall = sorted(rec["wall_s"] for rec in results)
                score = sum(rec["score"] for rec in results) / len(results)
                rss = max(rec["peak_rss_mb"] for rec in results)
                summary = {
                    "model": model,
                    "workflow": workflow,
                    "n_runs": len(results),
                    "wall_s_min": min(wall),
                    "wall_s_median": wall[len(wall) // 2],
                    "wall_s_max": max(wall),
                    "score_mean": score,
                    "peak_rss_mb_max": rss,
                }
                (RESULTS / f"n8n_{model.replace(':', '_')}_{workflow}_summary.json").write_text(json.dumps(summary, indent=2))
                print(f"    median={summary['wall_s_median']:.1f}s  score={score:.2f}  peak_rss={rss:.0f}MB", flush=True)


if __name__ == "__main__":
    main()
