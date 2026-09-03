"""Compute the headline summary tables for the article.

Reads results/all_rescored.json and produces:
- A per-PDF table
- An aggregated mean-per-parser table
- A per-page speed comparison
"""
import json
from pathlib import Path

all_results = json.loads(Path("results/all_rescored.json").read_text())

# Group by (parser, pdf)
PAGES = {
    "text_only.pdf": 1,
    "list_heavy.pdf": 1,
    "multi_column.pdf": 1,
    "table_heavy.pdf": 1,
    "test_simple.pdf": 4,
}


def get_pages(r):
    p = PAGES.get(r["pdf"], 1)
    return p


# Mean per parser (skip test_simple since it has no GT for accuracy)
results_with_gt = [r for r in all_results if r.get("stripped_accuracy_pct") is not None]

by_parser = {}
for r in results_with_gt:
    p = r["parser"]
    by_parser.setdefault(p, []).append(r)

print("\n=== MEAN PER PARSER (averaged across the 4 PDFs with ground truth) ===\n")
print(f"{'Parser':<12} {'Mean wall (s)':<14} {'Mean per page (s)':<20} {'Mean RSS (MB)':<14} {'Mean acc%':<10}")
print("-" * 75)
for p, results in by_parser.items():
    walls = [r["total_seconds"] for r in results]
    rss = [r["peak_rss_mb"] for r in results]
    accs = [r["stripped_accuracy_pct"] for r in results]
    pages = [get_pages(r) for r in results]
    mean_wall = sum(walls) / len(walls)
    total_pages = sum(pages)
    mean_per_page = sum(walls) / total_pages
    mean_rss = sum(rss) / len(rss)
    mean_acc = sum(accs) / len(accs)
    print(f"{p:<12} {mean_wall:<14.2f} {mean_per_page:<20.2f} {mean_rss:<14.0f} {mean_acc:<10.1f}")

print("\n=== PER-PDF DETAIL (with GT) ===\n")
print(f"{'PDF':<18} {'Parser':<10} {'Pages':<7} {'Wall (s)':<10} {'Per page (s)':<14} {'RSS (MB)':<10} {'Acc%':<8}")
print("-" * 80)
for r in results_with_gt:
    pages = get_pages(r)
    per_page = r["total_seconds"] / pages
    print(
        f"{r['pdf']:<18} {r['parser']:<10} {pages:<7} {r['total_seconds']:<10.1f} "
        f"{per_page:<14.2f} {r['peak_rss_mb']:<10.0f} {r['stripped_accuracy_pct']:<8.1f}"
    )

# Per-page speed across ALL runs (including test_simple)
print("\n=== PER-PAGE SPEED (all 5 PDFs, warm cache) ===\n")
for p in ["docling", "marker", "paddleocr"]:
    rs = [r for r in all_results if r["parser"] == p]
    per_page_times = [r["total_seconds"] / get_pages(r) for r in rs]
    mean = sum(per_page_times) / len(per_page_times)
    minv = min(per_page_times)
    maxv = max(per_page_times)
    print(f"  {p:<12} mean {mean:.2f}s/page  min {minv:.2f}  max {maxv:.2f}")
