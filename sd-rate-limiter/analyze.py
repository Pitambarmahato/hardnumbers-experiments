#!/usr/bin/env python3
"""Read results/full/*.json, write results/tables.md: median over repeats, min-max in brackets when repeats differ."""
import json, statistics as st
from pathlib import Path

HERE = Path(__file__).parent
VARIANTS = ["naive-fixed", "fixed", "sliding-log", "sliding-counter", "token-bucket"]
runs = [json.loads(p.read_text()) for p in sorted((HERE / "results" / "full").glob("*.json"))]
pick = lambda sc, v, k: [r[k] for r in runs if r["scenario"] == sc and r["variant"] == v and r.get(k) is not None]
med = lambda xs, nd=0: "n/a" if not xs else f"{st.median(xs):,.{nd}f}"
rng = lambda xs: "n/a" if not xs else (f"{st.median(xs):,.0f}" if min(xs) == max(xs) else f"{st.median(xs):,.0f} ({min(xs):,}-{max(xs):,})")

out = [f"# Results: {len(runs)} runs (median of 3 repeats; min-max in brackets when repeats differ). Limit = 100 per 1 s window.\n"]
for sc, title, cols in (
    ("s1", "S1 boundary burst: 100 requests 60 ms before a window edge and 100 10 ms after it, 10 cycles", ["max_sliding", "max_aligned", "allowed", "denied", "errors"]),
    ("s2", "S2 flood: 100 workers on one key for 10 s", ["max_sliding", "max_sliding_after2s", "max_aligned", "allowed", "errors", "throughput_per_s"]),
):
    out += [f"## {title}\n", "| Variant | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for v in VARIANTS:
        out.append(f"| {v} | " + " | ".join(rng(pick(sc, v, c)) for c in cols) + " |")
    out.append("")
out += ["## S3 many keys: 2,000 keys x 100 requests, window 3600 s, concurrency 100\n", "| Variant | Requests/s | p50 ms | p99 ms | Bytes per key | Allowed (of 200,000) | Errors |", "|---|---|---|---|---|---|---|"]
for v in VARIANTS:
    out.append(f"| {v} | {rng(pick('s3', v, 'throughput_per_s'))} | {med(pick('s3', v, 'p50_ms'), 2)} | {med(pick('s3', v, 'p99_ms'), 1)} | {rng(pick('s3', v, 'mem_per_key_bytes'))} | {rng(pick('s3', v, 'allowed'))} | {rng(pick('s3', v, 'errors'))} |")
r0 = runs[0] if runs else {}
out += ["", f"Environment: Redis {r0.get('redis')}, redis-py {r0.get('redis_py')}, Python {r0.get('python')}, {r0.get('platform')}."]
(HERE / "results" / "tables.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
