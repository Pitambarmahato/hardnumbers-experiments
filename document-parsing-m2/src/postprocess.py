"""Re-score the benchmark results with a markdown-stripped text fidelity metric.

The raw character-level edit distance penalizes structural differences (extra
table separators, heading hashes) that are actually correct output. This
post-processor strips markdown and re-computes accuracy on the underlying
text, which is what the user actually cares about for a RAG pipeline.
"""
import json
import re
from pathlib import Path

RESULTS = Path("results")
all_results = json.loads((RESULTS / "all.json").read_text())


def strip_markdown(s: str) -> str:
    """Drop markdown decoration: heading hashes, table pipes, bold/italic."""
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)        # headings
    s = re.sub(r"\|", " ", s)                                # table pipes
    s = re.sub(r"^[\s\-:|]+$", "", s, flags=re.MULTILINE)   # table separator lines
    s = s.replace("**", "").replace("__", "").replace("`", "")  # bold/italic/code
    s = re.sub(r"[ \t]+", " ", s)                            # collapse spaces
    s = re.sub(r"\n{3,}", "\n\n", s)                         # collapse blank lines
    return s.strip().lower()


def edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur[j] = min(ins, dele, sub)
        prev = cur
    return prev[-1]


def normalized_edit_distance(hyp: str, ref: str) -> float:
    hyp_n = strip_markdown(hyp)
    ref_n = strip_markdown(ref)
    if not ref_n:
        return 0.0
    return edit_distance(hyp_n, ref_n) / max(len(ref_n), 1)


# Re-score each result
gt_cache = {}
for r in all_results:
    if "error" in r and r.get("error"):
        continue
    pdf_stem = r["pdf"].replace(".pdf", "")
    gt_path = Path("data/ground_truth") / f"{pdf_stem}.txt"
    if not gt_path.exists():
        r["stripped_accuracy_pct"] = None
        continue
    if pdf_stem not in gt_cache:
        gt_cache[pdf_stem] = gt_path.read_text()
    gt = gt_cache[pdf_stem]
    hyp = r.get("output_text", "")
    norm = normalized_edit_distance(hyp, gt)
    r["stripped_accuracy_pct"] = round((1.0 - norm) * 100, 2)
    r["output_chars_stripped"] = len(strip_markdown(hyp))
    r["gt_chars_stripped"] = len(strip_markdown(gt))

# Save re-scored
(RESULTS / "all_rescored.json").write_text(json.dumps(all_results, indent=2))

# Print summary table
print(f"{'PDF':<20} {'Parser':<12} {'Wall (s)':<10} {'RSS (MB)':<10} {'Raw acc%':<10} {'Stripped acc%':<15} {'Char ratio':<10}")
print("-" * 90)
for r in all_results:
    raw = r.get("accuracy_pct")
    strip = r.get("stripped_accuracy_pct")
    raw_s = f"{raw:.1f}" if raw is not None else "n/a"
    strip_s = f"{strip:.1f}" if strip is not None else "n/a"
    ratio = (r.get("output_chars_stripped", 0) / r.get("gt_chars_stripped", 1)) if r.get("gt_chars_stripped") else 0
    print(f"{r['pdf']:<20} {r['parser']:<12} {r.get('total_seconds', 0):<10.1f} {r.get('peak_rss_mb', 0):<10.0f} {raw_s:<10} {strip_s:<15} {ratio:<10.2f}")
