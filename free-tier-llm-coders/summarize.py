"""Summarize the latest benchmark results into a publishable table."""
import json
import sys
from pathlib import Path
from collections import defaultdict

results_dir = Path("/private/tmp/hardnumbers-experiments-staging/free-tier-llm-coders/results")
files = sorted(results_dir.glob("benchmark_*.json"))
# Pick the most recent one with 20 records (full run)
target = None
for f in reversed(files):
    data = json.load(open(f))
    if len(data) == 20:
        target = f
        break
if not target:
    print("No full run found")
    sys.exit(1)

print(f"Using {target}\n")
data = json.load(open(target))

# Group by provider
by_provider = defaultdict(list)
for r in data:
    by_provider[r["provider"]].append(r)

PROVIDER_LABELS = {
    "nvidia_nim": "NVIDIA NIM (Nemotron 120B)",
    "openrouter_minimax_m3": "OpenRouter (MiniMax M3)",
    "groq": "Groq (Qwen 3.6 27B)",
    "cline_claude": "Cline API (Claude fable 5.1)",
}
PROVIDER_FREE = {
    "nvidia_nim": "Free",
    "openrouter_minimax_m3": "Free",
    "groq": "Free",
    "cline_claude": "Paid",
}

# Headline table
print("=" * 80)
print("HEADLINE: 5 coding tasks × 4 providers, 1 trial each")
print("=" * 80)
print(f"{'Provider':<32} {'Pass':>5} {'Avg wall':>10} {'P50 wall':>10} {'Avg tok/s':>10} {'Avg TTFT':>10} {'Cost':>8}")
print("-" * 95)
summary = []
for pid in ["nvidia_nim", "groq", "openrouter_minimax_m3", "cline_claude"]:
    recs = by_provider[pid]
    n = len(recs)
    passes = sum(1 for r in recs if r["success"])
    walls = sorted([r["wall_time_s"] for r in recs])
    avg_wall = sum(walls) / n
    p50 = walls[n // 2]
    avg_tps = sum(r["tokens_per_s"] for r in recs) / n
    avg_ttft = sum(r["time_to_first_token_s"] for r in recs) / n
    label = PROVIDER_LABELS.get(pid, pid)
    free = PROVIDER_FREE.get(pid, "?")
    print(f"{label:<32} {passes}/{n:>3} {avg_wall:>9.1f}s {p50:>9.1f}s {avg_tps:>9.0f} {avg_ttft:>9.1f}s {free:>8}")
    summary.append({
        "provider": pid,
        "label": label,
        "free": free,
        "pass": passes,
        "n": n,
        "avg_wall_s": round(avg_wall, 2),
        "p50_wall_s": round(p50, 2),
        "avg_tok_per_s": round(avg_tps, 1),
        "avg_ttft_s": round(avg_ttft, 2),
    })

print()
print("=" * 80)
print("PER-TASK: wall time (s) and success")
print("=" * 80)
TASKS = ["csv-header-infer", "function-docstring", "function-unit-test", "refactor-api-call", "cli-flag"]
header = f"{'Task':<22}" + "".join(f"{PROVIDER_LABELS.get(p, p)[:14]:>16}" for p in ["nvidia_nim", "groq", "openrouter_minimax_m3", "cline_claude"])
print(header)
print("-" * len(header))
for tid in TASKS:
    row = f"{tid:<22}"
    for pid in ["nvidia_nim", "groq", "openrouter_minimax_m3", "cline_claude"]:
        rec = next((r for r in by_provider[pid] if r["task_id"] == tid), None)
        if rec:
            mark = "✓" if rec["success"] else "✗"
            row += f"{rec['wall_time_s']:>5.1f}s {mark:>2}      "
        else:
            row += f"{'?':>16}"
    print(row)

print()
print("=" * 80)
print("PER-TASK: tokens per second")
print("=" * 80)
print(header)
print("-" * len(header))
for tid in TASKS:
    row = f"{tid:<22}"
    for pid in ["nvidia_nim", "groq", "openrouter_minimax_m3", "cline_claude"]:
        rec = next((r for r in by_provider[pid] if r["task_id"] == tid), None)
        if rec:
            row += f"{rec['tokens_per_s']:>14.0f}  "
        else:
            row += f"{'?':>16}"
    print(row)

# Save summary as JSON for the seed script
out = {
    "timestamp": target.stem.replace("benchmark_", ""),
    "headline_table": summary,
    "per_task": {
        tid: {
            pid: {
                "wall_time_s": next((r["wall_time_s"] for r in by_provider[pid] if r["task_id"] == tid), None),
                "tokens_in": next((r["tokens_in"] for r in by_provider[pid] if r["task_id"] == tid), None),
                "tokens_out": next((r["tokens_out"] for r in by_provider[pid] if r["task_id"] == tid), None),
                "tokens_per_s": next((r["tokens_per_s"] for r in by_provider[pid] if r["task_id"] == tid), None),
                "time_to_first_token_s": next((r["time_to_first_token_s"] for r in by_provider[pid] if r["task_id"] == tid), None),
                "success": next((r["success"] for r in by_provider[pid] if r["task_id"] == tid), None),
                "diff_lines": next((r["diff_lines"] for r in by_provider[pid] if r["task_id"] == tid), None),
            }
            for pid in ["nvidia_nim", "groq", "openrouter_minimax_m3", "cline_claude"]
        }
        for tid in TASKS
    },
}
Path("/tmp/hardnumbers-experiments-staging/free-tier-llm-coders/results/summary.json").write_text(json.dumps(out, indent=2))
print(f"\nSummary saved to results/summary.json")
