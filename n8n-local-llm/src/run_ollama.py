"""Direct Ollama benchmark runner.

Measures wall time, peak RSS, tokens/sec, and accuracy for each
model × workflow cell. This is the "model latency" baseline —
n8n's overhead will be added on top in run_n8n.py.

Why we run this first: the n8n setup is slow and may fail. If we
have the pure-model numbers, the article can still be written.

Outputs: results/ollama_<model>_<workflow>_r<n>.json per run,
plus results/ollama_summary.json (aggregated, for the article).
"""

import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
DATA = json.loads((ROOT / "data" / "test_workflows.json").read_text())
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def measure_peak_rss_mb() -> float:
    """Current process RSS in MB (Linux-style). On macOS ru_maxrss is bytes."""
    ru = resource.getrusage(resource.RUSAGE_SELF)
    # macOS: ru_maxrss is in bytes
    return ru.ru_maxrss / (1024 * 1024)


def ollama_generate(model: str, system: str, user: str, options: dict | None = None) -> dict:
    """Call /api/generate (non-streaming) and time it."""
    url = f"{DATA['ollama_url']}/api/generate"
    body = {
        "model": model,
        "system": system,
        "prompt": user,
        "stream": False,
    }
    if options:
        body["options"] = options
    t0 = time.perf_counter()
    r = requests.post(url, json=body, timeout=180)
    wall = time.perf_counter() - t0
    r.raise_for_status()
    out = r.json()
    out["_wall_s"] = wall
    return out


def ollama_chat_json(model: str, system: str, user: str, options: dict | None = None) -> dict:
    """Call /api/chat (non-streaming) with json format, time it."""
    url = f"{DATA['ollama_url']}/api/chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "stream": False,
        "format": "json",
    }
    if options:
        body["options"] = options
    t0 = time.perf_counter()
    r = requests.post(url, json=body, timeout=180)
    wall = time.perf_counter() - t0
    r.raise_for_status()
    out = r.json()
    out["_wall_s"] = wall
    return out


def score_classification(expected: str, response_text: str) -> float:
    """1.0 if response contains the expected label as a single word, else 0.0."""
    if not response_text:
        return 0.0
    text = response_text.strip().lower()
    # accept exact match or "label." or "label "
    if text == expected:
        return 1.0
    if text.startswith(expected) and len(text) <= len(expected) + 2:
        return 1.0
    # any of the words is the expected
    tokens = [t.strip(".,!? ") for t in text.split()]
    if len(tokens) == 1 and tokens[0] == expected:
        return 1.0
    return 0.0


def score_extraction(expected: dict, response_text: str) -> float:
    """Score JSON extraction on total/currency/date fields. 1 point each = 3 max."""
    import json as _json
    try:
        # tolerate markdown wrapping
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = _json.loads(text)
    except Exception:
        return 0.0
    score = 0.0
    for k in ("total", "currency", "date"):
        if k not in expected:
            continue
        want = expected[k]
        got = parsed.get(k)
        if want is None and got is None:
            score += 1
        elif want is None or got is None:
            continue
        elif k == "total":
            try:
                if abs(float(want) - float(got)) < 0.01:
                    score += 1
            except (TypeError, ValueError):
                continue
        else:
            if str(want).strip() == str(got).strip():
                score += 1
    return score / 3.0


def score_summarization(expected_bullets: list, response_text: str) -> float:
    """ROUGE-L F1 between response bullets and expected bullets, averaged."""
    try:
        from rouge_score import rouge_scorer
    except ImportError:
        # Fallback: simple word overlap
        def rouge_l_f1(ref, hyp):
            ref_words = ref.lower().split()
            hyp_words = hyp.lower().split()
            if not ref_words or not hyp_words:
                return 0.0
            # LCS by DP
            m, n = len(ref_words), len(hyp_words)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            for i in range(m):
                for j in range(n):
                    if ref_words[i] == hyp_words[j]:
                        dp[i + 1][j + 1] = dp[i][j] + 1
                    else:
                        dp[i + 1][j + 1] = max(dp[i + 1][j], dp[i][j + 1])
            lcs = dp[m][n]
            if lcs == 0:
                return 0.0
            prec = lcs / n
            rec = lcs / m
            return 2 * prec * rec / (prec + rec)
        scorer = None
    else:
        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    bullets_resp = [b.strip().lstrip("-•* ") for b in response_text.split("\n") if b.strip()]
    if not bullets_resp:
        return 0.0
    scores = []
    for exp in expected_bullets:
        if scorer:
            s = scorer.score(exp, " ".join(bullets_resp))["rougeL"].fmeasure
        else:
            s = rouge_l_f1(exp, " ".join(bullets_resp))
        scores.append(s)
    return sum(scores) / len(scores)


def score_rag_qa(expected: str, response_text: str) -> float:
    """1.0 if response contains the expected substring, else 0.0. 'I don't know' = 0 for in-context, 1 for out-of-context."""
    if not response_text:
        return 0.0
    text = response_text.strip().lower()
    if expected == "I don't know":
        return 1.0 if "i don't know" in text or "i do not know" in text else 0.0
    return 1.0 if expected.lower() in text else 0.0


def score_tool_calling(expected: dict, response_text: str) -> float:
    """1.0 if first action is the right tool with matching args, 0.0 otherwise."""
    import json as _json
    try:
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = _json.loads(text)
    except Exception:
        return 0.0
    if parsed.get("action") != "call_tool":
        return 0.0
    if parsed.get("tool") != expected.get("tool"):
        return 0.0
    # check that all expected arg keys match
    args_want = expected.get("args_contains", {})
    args_got = parsed.get("args", {})
    for k, v in args_want.items():
        if str(args_got.get(k, "")).strip() != str(v).strip():
            return 0.0
    return 1.0


def run_one(model: str, workflow: str, run_idx: int) -> dict:
    wf = DATA["workflows"][workflow]
    inp = wf["test_inputs"][run_idx % len(wf["test_inputs"])]
    # build the user prompt per workflow
    if workflow == "rag_qa":
        user_prompt = f"Context:\n{inp['context']}\n\nQuestion: {inp['question']}"
    else:
        user_prompt = inp["input"]
    peak_before = measure_peak_rss_mb()
    if workflow in ("extraction", "tool_calling"):
        out = ollama_chat_json(model, wf["system_prompt"], user_prompt)
    else:
        out = ollama_generate(model, wf["system_prompt"], user_prompt)
    peak_after = measure_peak_rss_mb()
    text = out.get("response", "")
    if not text and "message" in out:
        text = out["message"].get("content", "")
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
        "wall_s": out["_wall_s"],
        "prompt_tokens": out.get("prompt_eval_count", 0),
        "response_tokens": out.get("eval_count", 0),
        "total_duration_s": out.get("total_duration", 0) / 1e9,
        "load_duration_s": out.get("load_duration", 0) / 1e9,
        "score": score,
        "peak_rss_mb": max(peak_before, peak_after),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_ollama.py [model] [--only workflow1,workflow2]")
        print("       python run_ollama.py all     [--only workflow1,workflow2]")
        sys.exit(1)
    if sys.argv[1] == "all":
        models = [m["name"] for m in DATA["models"]]
    else:
        models = [sys.argv[1]]
    workflows = list(DATA["workflows"].keys())
    # filter
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        only = set(sys.argv[idx + 1].split(","))
        workflows = [w for w in workflows if w in only]
        if not workflows:
            print(f"No matching workflows. Available: {list(DATA['workflows'].keys())}")
            sys.exit(1)
    n_runs = DATA["runs_per_cell"]
    for model in models:
        print(f"\n=== {model} ===")
        # warm up
        print("  warming up (first call loads model)...", flush=True)
        try:
            warm = ollama_generate(model, "Reply with the single word: ok", "hi")
            print(f"  warmup: {warm['_wall_s']:.1f}s, {warm.get('eval_count', 0)} tokens")
        except Exception as e:
            print(f"  WARMUP FAILED: {e}")
            continue
        for workflow in workflows:
            results = []
            for r in range(n_runs):
                print(f"  {workflow} run {r + 1}/{n_runs}...", end=" ", flush=True)
                try:
                    rec = run_one(model, workflow, r)
                    out_path = RESULTS / f"ollama_{model.replace(':', '_')}_{workflow}_r{r + 1}.json"
                    out_path.write_text(json.dumps(rec, indent=2))
                    print(f"wall={rec['wall_s']:.1f}s score={rec['score']:.2f}")
                    results.append(rec)
                except Exception as e:
                    print(f"FAIL: {e}")
            if results:
                # write per-workflow summary
                wall = sorted(r["wall_s"] for r in results)
                score = sum(r["score"] for r in results) / len(results)
                rss = max(r["peak_rss_mb"] for r in results)
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
                (RESULTS / f"ollama_{model.replace(':', '_')}_{workflow}_summary.json").write_text(json.dumps(summary, indent=2))
                print(f"    median={summary['wall_s_median']:.1f}s  score={score:.2f}  peak_rss={rss:.0f}MB")


if __name__ == "__main__":
    main()
