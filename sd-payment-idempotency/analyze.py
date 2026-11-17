#!/usr/bin/env python3
"""Summarise results/full/*.json into results/tables.md (median and min-max over repeats). Hypotheses: docs/kw-sd-payment-idempotency.md."""
import json, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
VARIANTS = ["naive", "idem-local", "idem-e2e"]


def load(sc, v):
    return [json.loads(f.read_text()) for f in sorted((HERE / "results/full").glob(f"{sc}-{v}-r*.json"))]


def cell(vals, fmt=lambda x: f"{x:,.0f}"):
    if not vals: return "n/a"
    return fmt(vals[0]) if len(vals) == 1 else f"{fmt(st.median(vals))} ({fmt(min(vals))}-{fmt(max(vals))})"


def table(sc, cols, note=""):
    rows = [f"| Variant | runs | " + " | ".join(c[0] for c in cols) + " |", "|---|---|" + "---|" * len(cols)]
    for v in VARIANTS:
        runs = load(sc, v)
        if not runs: continue
        rows.append(f"| {v} | {len(runs)} | " + " | ".join(cell([r[c[1]] for r in runs], *(c[2:])) for c in cols) + " |")
    return "\n".join(rows) + (f"\n\n{note}" if note else "")


pct = lambda n: (lambda x: f"{x / n:.1%}")
f1 = lambda x: f"{x:,.1f}"
out = ["# Results (median, min-max across 3 repeats)\n"]
out += ["## S1 happy path, 10,000 orders", table("s1", [("orders/s", "orders_per_s", f1), ("p50 ms", "p50_ms", f1), ("p99 ms", "p99_ms", f1), ("charged twice", "orders_charged_twice_or_more")])]
s2n = 2000
out += ["\n## S2 slow provider (answers in 1.5 s, client times out at 1.0 s), 2,000 orders", table("s2", [("orders charged twice+", "orders_charged_twice_or_more"), ("extra charges", "extra_charges"), ("client gave up", "client_gave_up"), ("charged but client gave up", "charged_but_client_gave_up"), ("mean attempts", "mean_attempts", f1), ("p50 ms", "p50_ms")])]
out += ["\n## S3 service killed mid-load, 1,000 orders", table("s3", [("orders charged twice+", "orders_charged_twice_or_more"), ("never charged", "orders_never_charged"), ("client gave up", "client_gave_up"), ("charged but client gave up", "charged_but_client_gave_up"), ("p99 ms", "p99_ms"), ("kill during load", "kill_during_load", lambda x: str(bool(x)))])]
out += ["\n## S4 double click (each order sent twice at once), 2,000 orders", table("s4", [("orders charged twice+", "orders_charged_twice_or_more"), ("extra charges", "extra_charges"), ("client gave up", "client_gave_up"), ("mean attempts", "mean_attempts", f1)])]
out += ["\n## S5 same key, different amount, 500 orders", table("s5", [("second request rejected", "s5_second_rejected"), ("second accepted (200)", "s5_second_accepted_200"), ("extra charges", "extra_charges")])]
(HERE / "results/tables.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
