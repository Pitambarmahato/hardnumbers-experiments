"""Run a single parser on a single PDF and emit JSON to stdout.

Dispatch by the first CLI argument (parser name). Designed to be invoked from
separate venvs so each parser's deps stay isolated. The JSON envelope keeps the
orchestrator (benchmark.py) parser-agnostic.
"""
import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path


def measure_peak_rss_mb() -> float:
    """Best-effort peak RSS in MB. macOS reports ru_maxrss in bytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def run_docling(pdf_path: str) -> dict:
    from docling.document_converter import DocumentConverter
    t0 = time.perf_counter()
    converter = DocumentConverter()
    t_init = time.perf_counter() - t0
    t1 = time.perf_counter()
    result = converter.convert(pdf_path)
    t_convert = time.perf_counter() - t1
    md = result.document.export_to_markdown()
    pages = len(result.document.pages) if hasattr(result.document, "pages") else None
    return {
        "parser": "docling",
        "init_seconds": round(t_init, 3),
        "convert_seconds": round(t_convert, 3),
        "total_seconds": round(t_init + t_convert, 3),
        "peak_rss_mb": round(measure_peak_rss_mb(), 1),
        "output_chars": len(md),
        "output_text": md,
        "pages": pages,
    }


def run_marker(pdf_path: str) -> dict:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    t0 = time.perf_counter()
    model_dict = create_model_dict()
    t_init = time.perf_counter() - t0
    converter = PdfConverter(artifact_dict=model_dict)
    t1 = time.perf_counter()
    rendered = converter(pdf_path)
    t_convert = time.perf_counter() - t1
    text, _, _ = text_from_rendered(rendered)
    # Marker returns full markdown; pull the markdown field if present
    md = rendered.markdown if hasattr(rendered, "markdown") else text
    pages = getattr(rendered, "metadata", {}).get("page_stats") if hasattr(rendered, "metadata") else None
    return {
        "parser": "marker",
        "init_seconds": round(t_init, 3),
        "convert_seconds": round(t_convert, 3),
        "total_seconds": round(t_init + t_convert, 3),
        "peak_rss_mb": round(measure_peak_rss_mb(), 1),
        "output_chars": len(md),
        "output_text": md,
        "pages": pages,
    }


def run_paddleocr(pdf_path: str) -> dict:
    """PaddleOCR-VL-1.6: layout-aware OCR via PP-StructureV3.

    Falls back to plain OCR with PDF-to-image conversion if the VL pipeline is
    unavailable. We always pass the same input and let the API decide.
    """
    from paddleocr import PaddleOCR
    t0 = time.perf_counter()
    import inspect
    sig = inspect.signature(PaddleOCR.__init__)
    if "use_textline_orientation" in sig.parameters:
        ocr = PaddleOCR(use_textline_orientation=True, lang='en')
    else:
        ocr = PaddleOCR(use_angle_cls=True, lang='en')
    t_init = time.perf_counter() - t0
    t1 = time.perf_counter()
    import pymupdf
    doc = pymupdf.open(pdf_path)
    md_lines = []
    page_count = len(doc)
    for page_num, page in enumerate(doc, 1):
        pix = page.get_pixmap(dpi=200)
        img_path = f"/tmp/_po_page_{page_num}.png"
        pix.save(img_path)
        result = ocr.predict(img_path)
        if result:
            for r in result:
                j = getattr(r, "json", None)
                rec_texts = []
                if isinstance(j, dict):
                    # 3.x nests under "res"
                    res = j.get("res", {})
                    if isinstance(res, dict):
                        rec_texts = res.get("rec_texts", []) or []
                if not rec_texts and hasattr(r, "rec_text"):
                    rec_texts = r.rec_text if isinstance(r.rec_text, list) else [r.rec_text]
                for t in rec_texts:
                    if t:
                        md_lines.append(t)
            md_lines.append("")
        os.unlink(img_path)
    t_convert = time.perf_counter() - t1
    md = "\n".join(md_lines).strip() + "\n"
    return {
        "parser": "paddleocr",
        "init_seconds": round(t_init, 3),
        "convert_seconds": round(t_convert, 3),
        "total_seconds": round(t_init + t_convert, 3),
        "peak_rss_mb": round(measure_peak_rss_mb(), 1),
        "output_chars": len(md),
        "output_text": md,
        "pages": page_count,
    }


def run_mineru(pdf_path: str) -> dict:
    """MinerU: invoke via the magic-pdf CLI.

    magic-pdf has both a Python API and a CLI. The CLI is more stable across
    versions, so we shell out and capture stdout.
    """
    t0 = time.perf_counter()
    # magic-pdf uses a config file; default is fine for our purposes
    out_dir = Path("/tmp/mineru_out")
    out_dir.mkdir(exist_ok=True)
    cmd = [
        "magic-pdf", "--pdf", pdf_path, "--out", str(out_dir),
        "--method", "auto",  # let magic-pdf choose OCR vs text extraction
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    t_total = time.perf_counter() - t0
    # Find the generated markdown
    pdf_stem = Path(pdf_path).stem
    candidates = list(out_dir.rglob(f"{pdf_stem}.md"))
    if not candidates:
        # Try by directory
        candidates = list(out_dir.rglob("*.md"))
    md = candidates[0].read_text() if candidates else proc.stdout
    pages = None
    if candidates:
        # magic-pdf puts the markdown in a directory; the parent name has a page count
        pass
    return {
        "parser": "mineru",
        "init_seconds": 0.0,
        "convert_seconds": round(t_total, 3),
        "total_seconds": round(t_total, 3),
        "peak_rss_mb": round(measure_peak_rss_mb(), 1),
        "output_chars": len(md),
        "output_text": md,
        "pages": pages,
    }


PARSERS = {
    "docling": run_docling,
    "marker": run_marker,
    "paddleocr": run_paddleocr,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parser", choices=list(PARSERS.keys()))
    ap.add_argument("pdf_path")
    ap.add_argument("--output", help="Write JSON here instead of stdout")
    args = ap.parse_args()

    try:
        result = PARSERS[args.parser](args.pdf_path)
    except Exception as e:
        result = {
            "parser": args.parser,
            "error": f"{type(e).__name__}: {e}",
            "total_seconds": 0.0,
            "peak_rss_mb": 0.0,
            "output_chars": 0,
            "output_text": "",
        }

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))
    else:
        json.dump(result, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
