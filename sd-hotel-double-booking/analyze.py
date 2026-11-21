#!/usr/bin/env python3
"""Read results/full/*.json, write results/tables.md: median over repeats, with min-max in brackets for the counts that matter."""
import json, statistics as st
from pathlib import Path

HERE = Path(__file__).parent
VARIANTS = ["naive", "pessimistic", "optimistic", "exclusion", "exclusion-retry"]
runs = [json.loads(p.read_text()) for p in sorted((HERE / "results" / "full").glob("*.json"))]


def pick(sc, v, key):
    return [r[key] for r in runs if r["scenario"] == sc and r["variant"] == v]


def med(xs, nd=1):
    return "n/a" if not xs else f"{st.median(xs):,.{nd}f}"


def rng(xs):
    return "n/a" if not xs else (f"{st.median(xs):,.0f}" if min(xs) == max(xs) else f"{st.median(xs):,.0f} ({min(xs):,}-{max(xs):,})")


out = [f"# Results: {len(runs)} runs (median of 3 repeats; counts show min-max in brackets when the repeats differ)\n"]
for sc, title in (("s1", "S1 spread: 10,000 attempts, 200 rooms, concurrency 50"),
                  ("s2", "S2 hot: 2,000 attempts, 10 rooms, 5 nights, concurrency 100"),
                  ("s3", "S3 pool pressure: S2 workload, concurrency 400, pool of 20")):
    out += [f"## {title}\n", "| Variant | Double bookings | Room-nights oversold | Accepted | Errors | Deadlocks (Postgres) | Retries | Attempts/s | p50 ms | p99 ms |", "|---|---|---|---|---|---|---|---|---|---|"]
    for v in VARIANTS:
        g = lambda k: pick(sc, v, k)
        out.append(f"| {v} | {rng(g('double_bookings'))} | {rng(g('nights_oversold'))} | {rng(g('accepted'))} | {rng(g('errors'))} | {rng(g('pg_deadlocks'))} | {rng(g('retries_total'))} | {med(g('throughput_per_s'), 0)} | {med(g('p50_ms'))} | {med(g('p99_ms'), 0)} |")
    out.append("")
kinds = {}
for r in runs:
    for k, n in r["error_kinds"].items():
        kinds.setdefault((r["scenario"], r["variant"]), {}).setdefault(k, 0)
        kinds[(r["scenario"], r["variant"])][k] += n
out += ["## Error kinds (summed over repeats)\n", "| Scenario | Variant | Kinds |", "|---|---|---|"]
out += [f"| {s} | {v} | {', '.join(f'{k}: {n}' for k, n in d.items())} |" for (s, v), d in sorted(kinds.items())]
r0 = runs[0] if runs else {}
out += ["", f"Environment: Postgres {r0.get('postgres')}, asyncpg {r0.get('asyncpg')}, Python {r0.get('python')}, {r0.get('platform')}. deadlock_timeout = Postgres default (1 s)."]
(HERE / "results" / "tables.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
