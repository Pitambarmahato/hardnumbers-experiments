"""Run the arms over the sampled earnings events. Resumable. Stops on any error (no blind retries).

    python3 run_arms.py selftest                   # fake clients only; proves cap, resume, parsing. Never calls Jev.
    python3 run_arms.py sample [--n 500]           # seeded sample of events that have returns -> data/sample.jsonl
    python3 run_arms.py run --arms rules,always_up,qwen3-14b [--limit N]
    python3 run_arms.py run --arms jev --limit 20  # the Jev probe (needs TYPESAFE_API_KEY in YOUR shell)
    python3 run_arms.py determinism --arm jev      # 20 events x 3 repeats on Jev (60 calls, tiny cost)

JEV_SPEND_CAP_USD (default 0.50) is enforced by the client before every request.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import sys
import tempfile

import arms

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.environ.get("EXP_OUT", os.path.join(HERE, "results"))
SEED = 1
STOP_PARSE_FAIL = 0.02


def load_key() -> None:
    """Read TYPESAFE_API_KEY from the environment, else from ONE git-ignored file (JEV_ENV_FILE). Never printed or logged."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    path = os.environ.get("JEV_ENV_FILE")  # optional: a chmod 600 file containing TYPESAFE_API_KEY=...
    if not path or not os.path.exists(path):
        return
    if os.stat(path).st_mode & 0o077:
        sys.exit(f"STOP: {path} is readable by other users; run: chmod 600 {path}")
    for line in open(path):
        k, _, v = line.strip().partition("=")
        if k == "TYPESAFE_API_KEY" and v:
            os.environ[k] = v.strip().strip("'\"")


def read(path: str) -> list[dict]:
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def build_sample(n: int) -> None:
    events = {e["accession"]: e for e in read(os.path.join(DATA, "events.jsonl"))}
    rets = read(os.path.join(DATA, "returns.jsonl"))
    rows = [{**events[r["accession"]], **{k: r[k] for k in ("entry", "exit", "ret", "spy", "abn", "abn_oc")}} for r in rets if r["accession"] in events]
    # One filing can list several securities (common, preferred, share classes). Keep ONE per accession by a rule
    # that never looks at returns: no hyphen (not a preferred/warrant) first, then shorter ticker, then alphabetical.
    best: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: ("-" in r["ticker"], len(r["ticker"]), r["ticker"])):
        best.setdefault(r["accession"], r)
    print(f"dedupe: {len(rows)} rows -> {len(best)} unique filings")
    rows = sorted(best.values(), key=lambda r: r["accession"])   # deterministic base order before the seeded shuffle
    random.Random(SEED).shuffle(rows)
    with open(os.path.join(DATA, "sample.jsonl"), "w") as f:
        for r in rows[:n]:
            f.write(json.dumps(r) + "\n")
    print(f"sample: {min(n, len(rows))} of {len(rows)} events with returns (seed {SEED}); first 20 = probe set")


def text_for(acc: str) -> str:
    return open(os.path.join(DATA, "text", acc + ".txt")).read()


def swap_used_mb() -> float:
    import subprocess
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    return float(out.split("used =")[1].split("M")[0])


def mem_free_pct() -> float:
    import re, subprocess
    out = subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout
    m = re.search(r"free percentage:\s*(\d+)%", out)
    return float(m.group(1)) if m else 100.0


def run(arm_fns: dict, events: list[dict], out_dir: str, text_fn=text_for, repeat: int = 1, swap_guard_mb: float | None = None,
        latency_guard_s: float | None = None, min_free_pct: float | None = None) -> int:
    os.makedirs(out_dir, exist_ok=True)
    swap0 = swap_used_mb() if swap_guard_mb else 0.0
    recent: list[float] = []
    path = os.path.join(out_dir, "results.jsonl")
    done = {(r["arm"], r["accession"], r.get("rep", 1)) for r in read(path)}
    n_new = fails = calls = 0
    for ev in events:
        txt = text_fn(ev["accession"])
        for rep in range(1, repeat + 1):
            for name, fn in arm_fns.items():                    # arms interleaved per event: drift hits all arms
                if (name, ev["accession"], rep) in done:
                    continue
                try:
                    res = fn(txt)
                except Exception as e:  # noqa: BLE001 - stop rule: report and exit, never retry blindly
                    print(f"STOP at {name}/{ev['accession']}: {type(e).__name__}: {e}")
                    return 2
                calls += 1
                recent.append(res["ms"])
                if latency_guard_s and len(recent) >= 10 and sorted(recent[-10:])[5] > latency_guard_s * 1000:
                    print(f"STOP: rolling median latency {sorted(recent[-10:])[5] / 1000:.1f}s exceeds {latency_guard_s:.0f}s after {calls} calls; rows so far are saved")
                    return 2
                if min_free_pct and calls % 10 == 0 and mem_free_pct() < min_free_pct:
                    print(f"STOP: free memory {mem_free_pct():.0f}% below {min_free_pct:.0f}% after {calls} calls; rows so far are saved")
                    return 2
                if swap_guard_mb and calls % 10 == 0 and swap_used_mb() - swap0 > swap_guard_mb:
                    print(f"STOP: swap grew {swap_used_mb() - swap0:.0f} MB (limit {swap_guard_mb:.0f} MB) after {calls} calls; rows so far are saved")
                    return 2
                ok = res["label"] in arms.LABELS
                fails += not ok
                row = {"arm": name, "accession": ev["accession"], "ticker": ev["ticker"], "rep": rep,
                       "label": res["label"], "parsed": ok, "confidence": res.get("confidence"),
                       "probabilities": res.get("probabilities"), "score": res.get("score"),
                       "tokens_in": res["tokens_in"], "ms": round(res["ms"], 1), "raw": res["raw"],
                       "rules_version": arms.RULES_VERSION if name == "rules" else None,
                       "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
                with open(path, "a") as f:
                    f.write(json.dumps(row) + "\n")
                n_new += 1
                if calls >= 20 and fails / calls > STOP_PARSE_FAIL:
                    print(f"STOP: parse failures {fails}/{calls} exceed {STOP_PARSE_FAIL:.0%}")
                    return 2
    print(f"done: {n_new} new rows, {fails} parse failures")
    return 0


def selftest() -> None:
    ok = {}
    texts = {"bull": "Record revenue. The company raised its full-year guidance after strong growth.",
             "bear": "Revenue decline and a weak quarter. The company lowered its outlook and reported an impairment.",
             "flat": "The company held its annual meeting on Tuesday."}
    ok["rules: bullish text -> bullish"] = arms.rules(texts["bull"])["label"] == "bullish"
    ok["rules: bearish text -> bearish"] = arms.rules(texts["bear"])["label"] == "bearish"
    ok["rules: boilerplate -> neutral"] = arms.rules(texts["flat"])["label"] == "neutral"
    ok["always_up -> bullish"] = arms.always_up("x")["label"] == "bullish"
    ok["truncation at MAX_CHARS"] = len(arms.truncate("a" * 50_000)) == arms.MAX_CHARS

    with tempfile.TemporaryDirectory() as d:
        calls = []

        def fake_transport(url, headers, body):
            calls.append(json.loads(body))
            return {"model": "fake", "answers": {"tone": {"type": "choice", "choice": "bullish", "confidence": 0.9,
                    "probabilities": {"bullish": 0.9, "neutral": 0.07, "bearish": 0.03}}},
                    "usage": {"input_tokens": 3000, "output_tokens": 0}}

        # fake usage reports 3,000 tokens per call but the pre-send estimate is ~2,300, so a cap of $0.0003 must stop after 2 calls
        spend = arms.Spend(os.path.join(d, "spend.json"), cap_usd=0.0003)
        fn = lambda t: arms.jev(t, spend, transport=fake_transport)          # noqa: E731
        evs = [{"accession": f"a{i}", "ticker": "T"} for i in range(6)]
        code = run({"jev": fn}, evs, d, text_fn=lambda a: "x" * 6_000)
        rows = read(os.path.join(d, "results.jsonl"))
        ok["cap: run stops with exit 2 when the next call would pass the cap"] = code == 2
        ok["cap: calls actually sent stay under the cap"] = spend.usd <= 0.0003 and len(calls) == len(rows) == 2
        ok["cap: spend persisted to disk"] = json.load(open(os.path.join(d, "spend.json")))["tokens"] == spend.tokens
        spend2 = arms.Spend(os.path.join(d, "spend.json"), cap_usd=0.0003)  # simulated restart
        ok["cap: restart cannot reset the spend"] = spend2.tokens == spend.tokens
        ok["request: one choice question with three criteria, model jev-latest"] = (
            calls[0]["model"] == "jev-latest" and list(calls[0]["questions"]["tone"]["criteria"]) == arms.LABELS)
        ok["request: state truncated to MAX_CHARS"] = len(calls[0]["state"]) == arms.MAX_CHARS
        ok["no key leaks into saved rows"] = "Bearer" not in open(os.path.join(d, "results.jsonl")).read()

    with tempfile.TemporaryDirectory() as d:
        evs = [{"accession": f"b{i}", "ticker": "T"} for i in range(4)]
        run({"rules": arms.rules, "always_up": arms.always_up}, evs, d, text_fn=lambda a: texts["bull"])
        n1 = len(read(os.path.join(d, "results.jsonl")))
        run({"rules": arms.rules, "always_up": arms.always_up}, evs, d, text_fn=lambda a: texts["bull"])
        ok["resume: second run adds 0 rows"] = len(read(os.path.join(d, "results.jsonl"))) == n1 == 8

    with tempfile.TemporaryDirectory() as d:
        bad = lambda t: {"label": "???", "confidence": None, "raw": {}, "tokens_in": 0, "ms": 1.0}   # noqa: E731
        code = run({"bad": bad}, [{"accession": f"c{i}", "ticker": "T"} for i in range(30)], d, text_fn=lambda a: "x")
        ok["parse-failure stop rule triggers (exit 2)"] = code == 2
    for k, v in ok.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    sys.exit(0 if all(ok.values()) else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["selftest", "sample", "run", "determinism"])
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--arms", default="rules,always_up,qwen3-14b")
    ap.add_argument("--arm", default="jev")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    elif a.cmd == "sample":
        build_sample(a.n)
    else:
        load_key()
        spend = arms.Spend(os.path.join(OUT, "spend.json"), float(os.environ.get("JEV_SPEND_CAP_USD", "0.50")))
        table = {"rules": arms.rules, "always_up": arms.always_up, "qwen3-14b": arms.qwen, "qwen2.5-7b": lambda t: arms.qwen(t, model="qwen2.5:7b"),
                 "jev": lambda t: arms.jev(t, spend)}
        names = [a.arm] if a.cmd == "determinism" else a.arms.split(",")
        sample = read(os.path.join(DATA, "sample.jsonl"))
        sample = [e for e in sample if os.path.exists(os.path.join(DATA, "text", e["accession"] + ".txt"))
                  and os.path.getsize(os.path.join(DATA, "text", e["accession"] + ".txt")) >= 500]  # rule-based drop: no / near-empty EX-99.1 text (same rule as analyze.py)
        evs = sample[: (20 if a.cmd == "determinism" else a.limit)]
        out = OUT if a.cmd == "run" else os.path.join(OUT, "determinism")
        local = any(n.startswith("qwen") for n in names)
        code = run({n: table[n] for n in names}, evs, out, repeat=3 if a.cmd == "determinism" else 1,
                   latency_guard_s=25 if local else None, min_free_pct=10 if local else None)
        if "jev" in names:
            print(f"Jev spend so far (estimate from reported tokens): ${spend.usd:.5f} of ${spend.cap:.2f} cap")
        sys.exit(code)
