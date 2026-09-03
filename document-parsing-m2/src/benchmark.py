"""Orchestrate the document-parsing benchmark.

For each parser (in its own venv) and each PDF, spawn a subprocess, capture
the JSON output, and merge into a single results.json. Accuracy is scored by
character-level normalized edit distance against the ground truth.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
PDF_DIR = ROOT / "data" / "pdfs"
GT_DIR = ROOT / "data" / "ground_truth"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

# venv paths (one per parser, for dep isolation)
VENVS = {
    "docling": ROOT / ".venv-docling" / "bin" / "python",
    "marker": ROOT / ".venv-marker" / "bin" / "python",
    "paddleocr": ROOT / ".venv-paddleocr" / "bin" / "python",
}

PARSERS = list(VENVS.keys())


def normalize(s: str) -> str:
    """Strip markdown punctuation, collapse whitespace, lowercase for fuzzy match."""
    s = s.replace("\r\n", "\n")
    # Remove markdown table separators
    s = re.sub(r"^\s*\|[\s\-:|]+\|\s*$", "", s, flags=re.MULTILINE)
    # Remove pipe chars in tables
    s = re.sub(r"\|", " ", s)
    # Strip heading hashes, bold/italic markers
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    # Collapse all whitespace to single spaces
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def edit_distance(a: str, b: str) -> int:
    """Standard Wagner-Fischer Levenshtein. O(len(a)*len(b))."""
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
    """1 - (edit_distance / max(len(ref), 1)). 0 = perfect, 1 = total mismatch."""
    if not ref:
        return 0.0
    return edit_distance(normalize(hyp), normalize(ref)) / max(len(normalize(ref)), 1)


def load_ground_truth(pdf_path: Path) -> Optional[str]:
    gt_path = GT_DIR / (pdf_path.stem + ".txt")
    if gt_path.exists():
        return gt_path.read_text()
    return None


def run_one(parser: str, pdf_path: Path) -> dict:
    """Invoke the parser venv on the PDF. Returns the parsed result dict."""
    cmd = [
        str(VENVS[parser]), str(SRC / "run_parser.py"), parser, str(pdf_path),
    ]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {
            "parser": parser, "pdf": pdf_path.name, "error": "timeout after 600s",
            "wall_seconds": 600.0, "peak_rss_mb": 0.0, "output_chars": 0,
        }
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return {
            "parser": parser, "pdf": pdf_path.name, "error": f"exit {proc.returncode}: {proc.stderr[-500:]}",
            "wall_seconds": round(wall, 3), "peak_rss_mb": 0.0, "output_chars": 0,
        }
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {
            "parser": parser, "pdf": pdf_path.name, "error": f"json decode: {e}; stdout first 500: {proc.stdout[:500]}",
            "wall_seconds": round(wall, 3), "peak_rss_mb": 0.0, "output_chars": 0,
        }
    result["pdf"] = pdf_path.name
    result["wall_seconds"] = round(wall, 3)
    # If the parser itself reported a peak, trust it; else use ours
    if "peak_rss_mb" not in result or not result["peak_rss_mb"]:
        result["peak_rss_mb"] = 0.0
    return result


def score(result: dict, pdf_path: Path) -> dict:
    """Add accuracy fields to a result dict."""
    gt = load_ground_truth(pdf_path)
    if not gt:
        result["has_ground_truth"] = False
        return result
    result["has_ground_truth"] = True
    result["ground_truth_chars"] = len(gt)
    if "output_text" in result and result.get("output_text"):
        result["edit_distance_norm"] = round(normalized_edit_distance(
            result["output_text"], gt), 4)
        result["accuracy_pct"] = round((1.0 - result["edit_distance_norm"]) * 100, 2)
    else:
        result["edit_distance_norm"] = None
        result["accuracy_pct"] = None
    return result


def main():
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {PDF_DIR}")
        sys.exit(1)

    all_results = []
    for pdf in pdfs:
        print(f"\n=== {pdf.name} ({pdf.stat().st_size} bytes) ===")
        for parser in PARSERS:
            print(f"  -> {parser} ...", end="", flush=True)
            t0 = time.perf_counter()
            result = run_one(parser, pdf)
            result = score(result, pdf)
            elapsed = time.perf_counter() - t0
            acc = f"{result.get('accuracy_pct', 'n/a')}" + ("%" if result.get('accuracy_pct') is not None else "")
            rss = f"{result.get('peak_rss_mb', 'n/a')}MB"
            err = result.get("error", "")
            print(f" {elapsed:.1f}s wall, {acc} acc, {rss} rss {' ERR: ' + err if err else ''}")
            all_results.append(result)
            # Save incrementally so a crash doesn't lose progress
            (RESULTS / "raw.json").write_text(json.dumps(all_results, indent=2))

    (RESULTS / "all.json").write_text(json.dumps(all_results, indent=2))
    print(f"\nWrote {len(all_results)} results to {RESULTS / 'all.json'}")


if __name__ == "__main__":
    main()
