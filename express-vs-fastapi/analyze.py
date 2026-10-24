#!/usr/bin/env python3
"""results.json -> markdown tables (median of repeats, min-max of rps)."""
import json, statistics as st
from collections import defaultdict
from pathlib import Path

data = json.loads((Path(__file__).parent / "results" / "results.json").read_text())["results"]
cells = defaultdict(list)
for r in data:
    cells[(r["task_id"], r["concurrency"], r["provider"])].append(r)

for task in dict.fromkeys(r["task_id"] for r in data):
    print(f"\n### {task}\n")
    print("| Concurrency | Server | RPS (median) | RPS min-max | p50 ms | p95 ms | p99 ms | Errors | RSS MiB |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (t, c, p), rs in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        if t != task:
            continue
        m = lambda k: st.median(x[k] for x in rs)
        rps = [x["rps"] for x in rs]
        print(f"| {c} | {p} | {m('rps'):.0f} | {min(rps):.0f}-{max(rps):.0f} | {m('p50_ms'):.1f} | "
              f"{m('p95_ms'):.1f} | {m('p99_ms'):.1f} | {m('error_rate')*100:.2f}% | {m('rss_mib'):.0f} |")
