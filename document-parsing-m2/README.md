# document-parsing-m2

Benchmark of three open-source PDF parsers (Docling, Marker, PaddleOCR) on a
small 5-PDF corpus. Designed to answer the question: "which parser should I
use to feed PDFs into a RAG pipeline on a 24 GB unified memory machine?"

## Quick start

```bash
# Set up 4 venvs (one per parser, due to dep conflicts)
python3 -m venv .venv-docling && .venv-docling/bin/pip install docling
python3 -m venv .venv-marker && .venv-marker/bin/pip install marker-pdf
python3 -m venv .venv-paddleocr && .venv-paddleocr/bin/pip install paddleocr paddlepaddle pymupdf

# Generate the test PDFs
.venv/bin/python src/make_corpus.py

# Warmup + run
.venv-docling/bin/python src/run_parser.py docling data/pdfs/text_only.pdf
.venv-marker/bin/python src/run_parser.py marker data/pdfs/text_only.pdf
.venv-paddleocr/bin/python src/run_parser.py paddleocr data/pdfs/text_only.pdf

# Full benchmark
.venv/bin/python src/benchmark.py
.venv/bin/python src/postprocess.py
.venv/bin/python src/summarize.py
```

## Layout

```
data/
  pdfs/          # 5 generated test PDFs (digital, table, list, multi-col, warmup)
  ground_truth/  # 4 hand-written ground-truth text files
results/
  all.json       # Raw run data
  all_rescored.json  # Re-scored with markdown-stripped accuracy
  summary.txt    # Human-readable headline numbers
src/
  make_corpus.py     # Generates the 4 test PDFs
  run_parser.py      # Subprocess runner; one parser per invocation
  benchmark.py       # Orchestrates all (parser, pdf) pairs
  postprocess.py     # Strips markdown + recomputes accuracy
  summarize.py       # Headline tables
```

## Headline results

| Parser    | Per page | Peak RSS | Mean acc |
|-----------|----------|----------|----------|
| Marker    | 0.86 s   | 496 MB   | 95.6%    |
| Docling   | 4.80 s   | 1.13 GB  | 83.9%    |
| PaddleOCR | 26.99 s  | 4.43 GB  | 93.3%    |

## Caveats

- All measurements are CPU. Docling and PaddleOCR are 3-5x faster on a discrete GPU.
- The corpus is 4 hand-curated synthetic PDFs. Real-world PDFs with scans, formulas, or heavy multi-column layouts will behave differently.
- MinerU was excluded after a 14 GB model install and missing dep errors.
- PaddleOCR was tested with the standard `pip install paddleocr` pipeline (PP-OCRv6 + UVDoc). PaddleOCR-VL-1.6 (the OmniDocBench leader) needs the heavier PaddleX setup.
