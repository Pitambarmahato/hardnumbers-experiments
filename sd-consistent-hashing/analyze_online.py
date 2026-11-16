#!/usr/bin/env python3
"""Summarise results/online/*.json into results/online_tables.md (median and min-max over repeats). Metrics: docs/kw-sd-consistent-hashing.md A2."""
import json, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
SCHEMES = ["modn", "ring1", "ring10", "ring150"]
NAME = {"modn": "mod-N", "ring1": "ring V=1", "ring10": "ring V=10", "ring150": "ring V=150"}


def load(sc, sch):
    return [json.loads(f.read_text()) for f in sorted((HERE / "results/online").glob(f"{sc}-{sch}-r*.json"))]


def hit(b): return b["hit"] / max(1, b["n"])


def per_run(sc, d):
    bs, m = d["buckets"], d["meta"]
    base_h = st.mean(hit(b) for b in bs[2:10])
    r = {"wrong": sum(b["wrong"] for b in bs), "base_hit": base_h}
    tot = [sum(b["node"][i] for b in bs) for i in range(4)]
    r["busiest_share"] = max(tot) / sum(tot)
    if sc in ("s2", "s3"):
        sw = m["switch_at"]; post = bs[sw:]
        r["dip_hit"] = min(hit(b) for b in post)
        r["hit_last"] = hit(bs[-1])
        r["peak_db"] = max(b["db"] for b in post)
        r["peak_p99"] = max(b["p99"] for b in post)
        r["extra_db_60s"] = sum(b["db"] for b in post)
        r["errors"] = sum(b["err"] for b in bs)
        rec = next((i for i, b in enumerate(post) if i > 0 and hit(b) >= base_h - 0.05 and all(hit(x) >= base_h - 0.05 for x in post[i:])), None)
        r["recovered_s"] = rec
        if sc == "s3":
            after = bs[sw + m["detect_s"] + 1:]; t = [sum(b["node"][i] for b in after) for i in range(2)]
            r["survivor_share"] = max(t) / sum(t)
    else:
        r["p50"] = st.median(b["p50"] for b in bs); r["p99"] = st.median(b["p99"] for b in bs); r["db_s"] = st.mean(b["db"] for b in bs)
    return r


def cell(vals, fmt):
    vals = [v for v in vals if v is not None]
    if not vals: return "n/a"
    if len(vals) == 1: return fmt(vals[0])
    return f"{fmt(st.median(vals))} ({fmt(min(vals))}-{fmt(max(vals))})"


def table(sc, cols):
    rows = ["| Scheme | n | " + " | ".join(c[0] for c in cols) + " |", "|---|---|" + "---|" * len(cols)]
    for sch in SCHEMES:
        runs = [per_run(sc, d) for d in load(sc, sch)]
        if not runs: continue
        rows.append(f"| {NAME[sch]} | {len(runs)} | " + " | ".join(cell([r.get(c[1]) for r in runs], c[2]) for c in cols) + " |")
    return "\n".join(rows)


pct = lambda v: f"{v:.1%}"; i0 = lambda v: f"{v:,.0f}"; f1 = lambda v: f"{v:.1f}"
out = ["# Online results (median, min-max across repeats)\n"]
out += ["## S1 steady, uniform keys", table("s1", [("hit rate", "base_hit", pct), ("p50 ms", "p50", f1), ("p99 ms", "p99", f1), ("busiest node share", "busiest_share", pct), ("wrong", "wrong", i0)])]
out += ["\n## S2 add node 3 at t=10 s", table("s2", [("hit rate before", "base_hit", pct), ("lowest hit rate", "dip_hit", pct), ("hit rate at t=69 s", "hit_last", pct), ("peak Postgres q/s", "peak_db", i0), ("peak p99 ms", "peak_p99", i0), ("extra Postgres queries, 60 s", "extra_db_60s", i0), ("recovered after (s)", "recovered_s", i0), ("wrong", "wrong", i0)])]
out += ["\n## S3 kill node 2 at t=10 s (dropped from routing at t=15 s)", table("s3", [("lowest hit rate", "dip_hit", pct), ("hit rate at t=69 s", "hit_last", pct), ("peak Postgres q/s", "peak_db", i0), ("peak p99 ms", "peak_p99", i0), ("extra Postgres queries, 60 s", "extra_db_60s", i0), ("failed cache calls", "errors", i0), ("busiest survivor share (of 2)", "survivor_share", pct), ("wrong", "wrong", i0)])]
out += ["\n## S4 Zipf s=1.1 traffic", table("s4", [("hit rate", "base_hit", pct), ("busiest node share", "busiest_share", pct), ("p99 ms", "p99", f1), ("wrong", "wrong", i0)])]
(HERE / "results/online_tables.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
