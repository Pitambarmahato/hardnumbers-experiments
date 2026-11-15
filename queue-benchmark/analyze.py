#!/usr/bin/env python3
"""results.json -> markdown tables (median of repeats, min-max alongside). Pass a file name to read another file."""
import json, statistics as st, sys
from collections import defaultdict
from pathlib import Path

name = next((a for a in sys.argv[1:] if not a.startswith("-")), "results.json")
d = json.loads((Path(__file__).parent / "results" / name).read_text())
perf, crash = d["perf"], d["crash"]
configs = list(dict.fromkeys(r["config"] for r in perf + crash))
med = lambda xs: st.median(xs)
rng = lambda xs: f"{min(xs):.0f}-{max(xs):.0f}"

def cell(cfg, scenario, key, workers=None):
    rs = [r for r in perf if r["config"] == cfg and r["scenario"] == scenario and (workers is None or r["workers"] == workers)]
    return [r[key] for r in rs]

print("\n### Throughput (jobs/s, median; min-max in brackets)\n")
ws = sorted({r["workers"] for r in perf if r["scenario"] == "drain"})
print("| Config | Enqueue (10 in flight) | " + " | ".join(f"Drain, {w} worker{'s' if w > 1 else ''}" for w in ws) + " |")
print("|---|---|" + "---|" * len(ws))
for c in configs:
    row = []
    for sc, w in [("enqueue", None)] + [("drain", w) for w in ws]:
        v = cell(c, sc, "jobs_per_s", w)
        row.append(f"{med(v):.0f} ({rng(v)})" if v else "-")
    print(f"| {c} | " + " | ".join(row) + " |")

print("\n### End-to-end latency at 1000 jobs/s, 4 workers (ms, median of repeats)\n")
print("| Config | p50 | p95 | p99 | max | Jobs skipped (overload) |")
print("|---|---|---|---|---|---|")
for c in configs:
    g = lambda k: cell(c, "latency", k)
    if g("p50_ms"):
        print(f"| {c} | {med(g('p50_ms')):.1f} | {med(g('p95_ms')):.1f} | {med(g('p99_ms')):.1f} | {med(g('max_ms')):.0f} | {sum(g('skipped'))} |")

print("\n### SIGKILL the broker 5 s into a 2000 jobs/s producer\n")
print("| Config | Confirmed | Survived | Lost | Lost % | Processed but not confirmed | Duplicates | Runs |")
print("|---|---|---|---|---|---|---|---|")
for c in configs:
    rs = [r for r in crash if r["config"] == c]
    if rs:
        print(f"| {c} | {med([r['confirmed'] for r in rs]):.0f} | {med([r['survived'] for r in rs]):.0f} | "
              f"{med([r['lost'] for r in rs]):.0f} ({rng([r['lost'] for r in rs])}) | {med([r['lost_pct'] for r in rs]):.1f}% | "
              f"{med([r['processed_not_confirmed'] for r in rs]):.0f} | {sum(r['duplicates'] for r in rs)} | {len(rs)} |")

print("\n### Resources at peak (the driver is one single-threaded Node process, so ~90-100% means the driver, not the broker, is the ceiling)\n")
print("| Config | Broker CPU % | Driver CPU % | Broker MiB |")
print("|---|---|---|---|")
for c in configs:
    rs = [r for r in perf if r["config"] == c]
    if rs:
        print(f"| {c} | {max(r['broker_cpu_pct'] for r in rs)} | {max(r['driver_cpu_pct'] for r in rs)} | {max(r['broker_mem_mib'] for r in rs)} |")
