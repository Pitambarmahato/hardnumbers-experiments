"""Score the pre-registered hypotheses from results/results.jsonl + data/sample.jsonl. Regenerates every table.

    python3 analyze.py             # real data: writes results/analysis.json and prints the hypothesis verdicts
    python3 analyze.py selftest    # synthetic data only; proves the statistics before any real outcome is looked at

Primary outcome (plan): sign of the abnormal return from the last close at or before acceptance to the close of the first
session that starts after acceptance. Neutral calls are excluded from hit rate and counted. Zero abnormal returns are dropped.
Events whose press-release text is under MIN_TEXT_CHARS are excluded for every arm (rule fixed before any outcome was scored).
Hypotheses are scored exactly as written in docs/plan-earnings-release-ai-signal.md (H1-H4); nothing here may be edited after the
first real run.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RES = os.environ.get("EXP_OUT", os.path.join(HERE, "results"))
ARMS = ["jev", "qwen2.5-7b", "rules", "always_up"]
ALPHA_PER_ARM = 0.05 / 3  # 3 model arms tested on one primary window (plan: Bonferroni, 0.017)
MIN_TEXT_CHARS = 500


def read(path: str) -> list[dict]:
    return [json.loads(l) for l in open(path) if l.strip()]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def binom_p_two_sided(k: int, n: int) -> float:
    """Exact two-sided binomial test against p = 0.5 (log-space, safe for large n)."""
    if n == 0:
        return float("nan")
    logp = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) - n * math.log(2) for i in range(n + 1)]
    return min(1.0, sum(math.exp(lp) for lp in logp if lp <= logp[k] + 1e-9))


def rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for t in range(i, j + 1):
            r[order[t]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x: list[float], y: list[float]) -> tuple[float, float]:
    """Spearman rho with a normal-approximation two-sided p (adequate for n in the hundreds)."""
    n = len(x)
    if n < 10:
        return (float("nan"), float("nan"))
    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    rho = sxy / (sx * sy) if sx and sy else float("nan")
    return rho, math.erfc(abs(rho * math.sqrt(n - 1)) / math.sqrt(2))


def signed(label: str) -> int:
    return {"bullish": 1, "bearish": -1}.get(label, 0)


def score(r: dict) -> float:
    """Signed score for the correlation: direction x confidence (confidence 1.0 where an arm has none)."""
    return signed(r["label"]) * (r.get("confidence") if r.get("confidence") is not None else 1.0)


def arm_stats(rows: list[dict], truth: dict[str, float]) -> dict:
    calls = [(r, truth[r["accession"]]) for r in rows if r["accession"] in truth and r["parsed"]]
    calls = [(r, a) for r, a in calls if a != 0]
    nn = [(r, a) for r, a in calls if r["label"] != "neutral"]
    hits = sum((signed(r["label"]) > 0) == (a > 0) for r, a in nn)
    lo, hi = wilson(hits, len(nn))
    rho, rho_p = spearman([score(r) for r, _ in calls], [a for _, a in calls])
    ms = sorted(r["ms"] for r in rows if not r.get("cache_suspect"))
    return {"n": len(calls), "non_neutral": len(nn), "neutral": len(calls) - len(nn), "hits": hits,
            "hit_rate": hits / len(nn) if nn else None, "wilson95": [lo, hi], "binom_p": binom_p_two_sided(hits, len(nn)),
            "spearman": rho, "spearman_p": rho_p,
            "labels": {k: sum(r["label"] == k for r, _ in calls) for k in ("bullish", "neutral", "bearish")},
            "latency_ms": {"p50": ms[len(ms) // 2], "p95": ms[int(0.95 * len(ms)) - 1], "max": ms[-1]} if ms else None,
            "tokens_in": sum(r["tokens_in"] for r in rows)}


def tercile_gap(rows: list[dict], truth: dict[str, float]) -> dict:
    """H3: hit rate of Jev's top-third-confidence non-neutral calls minus its bottom third."""
    nn = [(r, truth[r["accession"]]) for r in rows if r["accession"] in truth and r["parsed"] and r["label"] != "neutral" and truth[r["accession"]] != 0]
    nn.sort(key=lambda t: t[0]["confidence"] or 0)
    k = len(nn) // 3
    if k == 0:
        return {"gap": None}
    f = lambda part: sum((signed(r["label"]) > 0) == (a > 0) for r, a in part) / len(part)  # noqa: E731
    return {"bottom": f(nn[:k]), "top": f(nn[-k:]), "gap": f(nn[-k:]) - f(nn[:k]), "n_each": k}


def ece(rows: list[dict], truth: dict[str, float], bins: int = 10) -> float | None:
    """Expected calibration error of Jev's confidence for its non-neutral calls (correct = sign matches)."""
    pts = [(r["confidence"], (signed(r["label"]) > 0) == (truth[r["accession"]] > 0)) for r in rows
           if r["accession"] in truth and r["parsed"] and r["label"] != "neutral" and truth[r["accession"]] != 0 and r["confidence"] is not None]
    if not pts:
        return None
    tot = 0.0
    for b in range(bins):
        grp = [(c, ok) for c, ok in pts if b / bins <= c < (b + 1) / bins or (b == bins - 1 and c == 1.0)]
        if grp:
            tot += len(grp) / len(pts) * abs(sum(c for c, _ in grp) / len(grp) - sum(ok for _, ok in grp) / len(grp))
    return tot


def analyze(res_dir: str, sample_path: str, outcome_key: str = "abn", text_dir: str | None = None) -> dict:
    sample = {e["accession"]: e for e in read(sample_path)}
    dropped_short = 0
    if text_dir and os.path.isdir(text_dir):
        for acc in list(sample):
            p = os.path.join(text_dir, acc + ".txt")
            if not os.path.exists(p) or len(open(p).read()) < MIN_TEXT_CHARS:
                sample.pop(acc)
                dropped_short += 1
    else:  # fresh clone: the published sample records each text's length (-1 = no exhibit)
        for acc in list(sample):
            if sample[acc].get("text_chars", MIN_TEXT_CHARS) < MIN_TEXT_CHARS:
                sample.pop(acc)
                dropped_short += 1
    truth = {a: e[outcome_key] for a, e in sample.items()}
    rows = read(os.path.join(res_dir, "results.jsonl"))
    out = {"outcome": outcome_key, "events": len(sample), "dropped_no_or_short_text": dropped_short, "arms": {}}
    for arm in ARMS:
        r = [x for x in rows if x["arm"] == arm and x.get("rep", 1) == 1]
        if r:
            out["arms"][arm] = arm_stats(r, truth)
    jev_rows = [x for x in rows if x["arm"] == "jev" and x.get("rep", 1) == 1]
    if jev_rows:
        out["jev_tercile"] = tercile_gap(jev_rows, truth)
        out["jev_ece"] = ece(jev_rows, truth)
    a = out["arms"]
    h = {}
    if a:
        beats = {k: (v["wilson95"][0] > 0.5 and v["binom_p"] < ALPHA_PER_ARM) for k, v in a.items() if k != "always_up" and v["hit_rate"] is not None}
        h["H1_no_arm_beats_chance"] = {"holds": not any(beats.values()), "arms_that_beat": [k for k, v in beats.items() if v],
                                       "rule": f"Wilson 95% lower bound > 0.5 and binomial p < {ALPHA_PER_ARM:.4f}"}
        if "jev" in a and "qwen2.5-7b" in a and a["jev"]["hit_rate"] is not None and a["qwen2.5-7b"]["hit_rate"] is not None:
            gap = abs(a["jev"]["hit_rate"] - a["qwen2.5-7b"]["hit_rate"]) * 100
            h["H2_cheap_equals_paid"] = {"gap_points": gap, "holds": gap <= 3, "falsified": gap >= 5}
        if out.get("jev_tercile", {}).get("gap") is not None:
            g = out["jev_tercile"]["gap"] * 100
            h["H3_confidence_matters"] = {"gap_points": g, "holds": g >= 5, "falsified": g < 2}
        best = max((v for k, v in a.items() if k != "always_up" and v["spearman"] == v["spearman"]), key=lambda v: abs(v["spearman"]), default=None)
        if best:
            h["H4_weak_correlation"] = {"best_spearman": best["spearman"], "p": best["spearman_p"], "holds": best["spearman"] <= 0.10,
                                        "falsified": best["spearman"] >= 0.15 and best["spearman_p"] < 0.01}
    out["hypotheses"] = h
    return out


def selftest() -> None:
    import random
    rng = random.Random(7)
    ok = {}
    ok["wilson(50,100) centred on 0.5"] = abs((wilson(50, 100)[0] + wilson(50, 100)[1]) / 2 - 0.5) < 0.01
    ok["binomial p(50 of 100) = 1.0"] = abs(binom_p_two_sided(50, 100) - 1.0) < 1e-9
    ok["binomial p(65 of 100) about 0.0035"] = abs(binom_p_two_sided(65, 100) - 0.0035) < 0.0005
    ok["spearman perfect = 1"] = abs(spearman(list(range(20)), [2 * i for i in range(20)])[0] - 1) < 1e-9
    ok["spearman reversed = -1"] = abs(spearman(list(range(20)), [-i for i in range(20)])[0] + 1) < 1e-9
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(d + "/text")
        sample, rows = [], []
        for i in range(400):
            abn = rng.gauss(0, 0.05)
            acc = f"s{i}"
            sample.append({"accession": acc, "abn": abn, "abn_oc": 0.0})
            open(f"{d}/text/{acc}.txt", "w").write("x" * (50 if i < 5 else 2000))   # 5 empty-ish texts must be excluded

            def row(arm, label, conf=None, ms=100):
                rows.append({"arm": arm, "accession": acc, "rep": 1, "label": label, "parsed": True, "confidence": conf, "ms": ms, "tokens_in": 10})
            oracle = "bullish" if abn > 0 else "bearish"
            row("jev", oracle if rng.random() < 0.8 else ("bearish" if oracle == "bullish" else "bullish"), conf=rng.random())  # planted 80% edge
            row("qwen2.5-7b", rng.choice(["bullish", "bearish"]), ms=900)                                                      # coin flip
            row("rules", "bullish")
            row("always_up", "bullish")
        with open(d + "/results.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        with open(d + "/sample.jsonl", "w") as f:
            for s in sample:
                f.write(json.dumps(s) + "\n")
        a = analyze(d, d + "/sample.jsonl", text_dir=d + "/text")
        kept = [s for s in sample[5:]]
        ok["short-text events excluded (5 of 400)"] = a["events"] == 395 and a["dropped_no_or_short_text"] == 5
        ok["planted 80% edge detected for the planted arm (Jev)"] = a["arms"]["jev"]["wilson95"][0] > 0.7 and a["arms"]["jev"]["binom_p"] < 1e-6
        ok["coin-flip arm is NOT flagged as beating chance"] = not (a["arms"]["qwen2.5-7b"]["wilson95"][0] > 0.5 and a["arms"]["qwen2.5-7b"]["binom_p"] < ALPHA_PER_ARM)
        ok["H1 reports that exactly Jev beats chance"] = a["hypotheses"]["H1_no_arm_beats_chance"]["holds"] is False and a["hypotheses"]["H1_no_arm_beats_chance"]["arms_that_beat"] == ["jev"]
        ok["always-bullish hit rate = share of up moves"] = abs(a["arms"]["always_up"]["hit_rate"] - sum(s["abn"] > 0 for s in kept) / len(kept)) < 1e-9
        ok["H2 gap computed (planted gap > 20 points)"] = a["hypotheses"]["H2_cheap_equals_paid"]["gap_points"] > 20
        ok["latency percentiles computed"] = a["arms"]["qwen2.5-7b"]["latency_ms"]["p50"] == 900
    for k, v in ok.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    sys.exit(0 if all(ok.values()) else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    sample_path = os.path.join(DATA, "sample.jsonl")
    if not os.path.exists(sample_path):
        sample_path = os.path.join(HERE, "published", "sample_with_returns.jsonl")
    result = {key: analyze(RES, sample_path, key, os.path.join(DATA, "text")) for key in ("abn", "abn_oc")}
    json.dump(result, open(os.path.join(RES, "analysis.json"), "w"), indent=1)
    print(json.dumps(result["abn"]["hypotheses"], indent=1))
