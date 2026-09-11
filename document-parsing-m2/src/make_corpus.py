"""Generate a small curated test PDF corpus with different content types.

Each PDF is paired with a ground-truth text file used for edit-distance
accuracy scoring. Keeping the corpus small and the ground truth human-written
keeps the experiment reproducible without external dependencies.
"""
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.units import inch

PDF_DIR = Path("data/pdfs")
GT_DIR = Path("data/ground_truth")
PDF_DIR.mkdir(parents=True, exist_ok=True)
GT_DIR.mkdir(parents=True, exist_ok=True)


def make_table_pdf():
    """A financial report with multiple tables, mostly borderless.
    Tests TableFormer-style reconstruction."""
    out = PDF_DIR / "table_heavy.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Annual Performance Report", styles['Title']))
    story.append(Paragraph("Fiscal Year 2025", styles['Heading2']))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Executive Summary", styles['Heading3']))
    story.append(Paragraph(
        "Revenue grew 18 percent year over year. Operating margin expanded by "
        "three percentage points. Free cash flow reached an all-time high of "
        "two point four billion dollars.",
        styles['BodyText']))

    story.append(Paragraph("Revenue by Segment", styles['Heading3']))
    data = [
        ['', '2024', '2025', 'Change'],
        ['Cloud', '4.2B', '5.1B', '+21%'],
        ['Hardware', '2.1B', '2.3B', '+10%'],
        ['Services', '1.4B', '1.7B', '+21%'],
        ['Total', '7.7B', '9.1B', '+18%'],
    ]
    t = Table(data)
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(t)

    story.append(Paragraph("Regional Breakdown", styles['Heading3']))
    data2 = [
        ['Region', 'Q1', 'Q2', 'Q3', 'Q4'],
        ['North America', '1.8B', '1.9B', '2.0B', '2.1B'],
        ['Europe', '1.1B', '1.2B', '1.2B', '1.3B'],
        ['Asia Pacific', '0.8B', '0.9B', '1.0B', '1.1B'],
        ['Latin America', '0.2B', '0.2B', '0.3B', '0.3B'],
    ]
    t2 = Table(data2)
    t2.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(t2)

    story.append(Paragraph("Capital Allocation", styles['Heading3']))
    story.append(Paragraph(
        "The company returned one point eight billion dollars to shareholders "
        "through dividends and buybacks. Capital expenditure was four hundred "
        "million dollars, focused on data center expansion.",
        styles['BodyText']))

    doc.build(story)

    # Ground truth: the actual text content, structured as paragraphs
    gt = """Annual Performance Report
Fiscal Year 2025

Executive Summary
Revenue grew 18 percent year over year. Operating margin expanded by three percentage points. Free cash flow reached an all-time high of two point four billion dollars.

Revenue by Segment
Cloud 2024 4.2B 2025 5.1B Change 21%
Hardware 2024 2.1B 2025 2.3B Change 10%
Services 2024 1.4B 2025 1.7B Change 21%
Total 2024 7.7B 2025 9.1B Change 18%

Regional Breakdown
Region Q1 Q2 Q3 Q4
North America 1.8B 1.9B 2.0B 2.1B
Europe 1.1B 1.2B 1.2B 1.3B
Asia Pacific 0.8B 0.9B 1.0B 1.1B
Latin America 0.2B 0.2B 0.3B 0.3B

Capital Allocation
The company returned one point eight billion dollars to shareholders through dividends and buybacks. Capital expenditure was four hundred million dollars, focused on data center expansion.
"""
    (GT_DIR / "table_heavy.txt").write_text(gt.strip() + "\n")
    return out


def make_multicolumn_pdf():
    """A two-column research-paper style document. Tests reading order."""
    out = PDF_DIR / "multi_column.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=letter)
    styles = getSampleStyleSheet()
    # Force two-column by using a frame layout
    from reportlab.platypus import Frame, PageTemplate
    left_frame = Frame(0.6 * inch, 0.6 * inch, 3.3 * inch, 9.5 * inch, id='left')
    right_frame = Frame(4.1 * inch, 0.6 * inch, 3.3 * inch, 9.5 * inch, id='right')
    doc.addPageTemplates([
        PageTemplate(id='two_col', frames=[left_frame, right_frame])
    ])

    story = []
    story.append(Paragraph(
        "On the Evaluation of Local Document Parsing Pipelines: A Comparative Study",
        ParagraphStyle('title', parent=styles['Title'], fontSize=14, spaceAfter=10)))
    story.append(Paragraph(
        "Abstract. We compare four open-source document parsing tools across a "
        "diverse corpus. We find that table accuracy varies by an order of "
        "magnitude between the best and worst parsers, while text accuracy "
        "remains within five percentage points for all but the most degraded "
        "inputs.",
        ParagraphStyle('abstract', parent=styles['BodyText'], fontSize=9, spaceAfter=12)))
    story.append(Paragraph("1. Introduction", styles['Heading3']))
    story.append(Paragraph(
        "Document parsing is the first step in most retrieval-augmented "
        "generation pipelines. The output of this step feeds every downstream "
        "decision, so accuracy and structure preservation matter as much as "
        "raw text fidelity.",
        styles['BodyText']))
    story.append(Paragraph(
        "In this study, we focus on the four most popular open-source parsers "
        "as of mid-2026: Docling from IBM Research, Marker from Datalab, "
        "PaddleOCR-VL from Baidu, and MinerU from OpenDataLab.",
        styles['BodyText']))
    story.append(Paragraph("2. Methodology", styles['Heading3']))
    story.append(Paragraph(
        "We ran each parser on the same eight-document corpus, measuring wall "
        "time, peak resident memory, and text fidelity against a hand-curated "
        "ground truth. Tables were scored separately using tree edit distance.",
        styles['BodyText']))
    story.append(Paragraph("3. Results", styles['Heading3']))
    story.append(Paragraph(
        "On simple digital PDFs all four parsers achieved edit distance under "
        "five percent. On scanned documents with complex tables, the gap "
        "widened to over forty percentage points between the best and worst "
        "parsers.",
        styles['BodyText']))

    doc.build(story)

    gt = """On the Evaluation of Local Document Parsing Pipelines: A Comparative Study
Abstract. We compare four open-source document parsing tools across a diverse corpus. We find that table accuracy varies by an order of magnitude between the best and worst parsers, while text accuracy remains within five percentage points for all but the most degraded inputs.
1. Introduction
Document parsing is the first step in most retrieval-augmented generation pipelines. The output of this step feeds every downstream decision, so accuracy and structure preservation matter as much as raw text fidelity.
In this study, we focus on the four most popular open-source parsers as of mid-2026: Docling from IBM Research, Marker from Datalab, PaddleOCR-VL from Baidu, and MinerU from OpenDataLab.
2. Methodology
We ran each parser on the same eight-document corpus, measuring wall time, peak resident memory, and text fidelity against a hand-curated ground truth. Tables were scored separately using tree edit distance.
3. Results
On simple digital PDFs all four parsers achieved edit distance under five percent. On scanned documents with complex tables, the gap widened to over forty percentage points between the best and worst parsers.
"""
    (GT_DIR / "multi_column.txt").write_text(gt.strip() + "\n")
    return out


def make_text_only_pdf():
    """A simple text-only academic abstract. Baseline for digital PDFs."""
    out = PDF_DIR / "text_only.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(
        "Speculative Decoding for Local Language Models",
        styles['Title']))
    story.append(Paragraph(
        "Speculative decoding accelerates inference by drafting tokens with a "
        "small fast model and verifying them with a larger target model. This "
        "study measures the speedup on a 24-gigabyte Apple Silicon Mac using a "
        "Qwen three 14 billion parameter target model.",
        styles['BodyText']))
    story.append(Paragraph(
        "We find that a 0.5 billion parameter draft model achieves a 1.8x "
        "speedup at batch size one, with no quality loss. At batch size four "
        "the speedup shrinks to 1.3x as verification cost dominates.",
        styles['BodyText']))
    story.append(Paragraph(
        "These results suggest speculative decoding is a free lunch for "
        "interactive local inference, where batch sizes are small and latency "
        "matters more than throughput.",
        styles['BodyText']))

    doc.build(story)

    gt = """Speculative Decoding for Local Language Models
Speculative decoding accelerates inference by drafting tokens with a small fast model and verifying them with a larger target model. This study measures the speedup on a 24-gigabyte Apple Silicon Mac using a Qwen three 14 billion parameter target model.
We find that a 0.5 billion parameter draft model achieves a 1.8x speedup at batch size one, with no quality loss. At batch size four the speedup shrinks to 1.3x as verification cost dominates.
These results suggest speculative decoding is a free lunch for interactive local inference, where batch sizes are small and latency matters more than throughput.
"""
    (GT_DIR / "text_only.txt").write_text(gt.strip() + "\n")
    return out


def make_list_heavy_pdf():
    """Document with lots of lists, headings, structured prose. Tests markdown output fidelity."""
    out = PDF_DIR / "list_heavy.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Installation Guide", styles['Title']))
    story.append(Paragraph("Prerequisites", styles['Heading2']))
    story.append(Paragraph("Before you begin, ensure you have the following:", styles['BodyText']))
    for line in [
        "Python 3.10 or newer installed.",
        "At least 16 gigabytes of free disk space.",
        "A working internet connection for model downloads.",
        "macOS 14 or Ubuntu 22.04 as the operating system.",
    ]:
        story.append(Paragraph(f"* {line}", styles['BodyText']))
    story.append(Paragraph("Steps", styles['Heading2']))
    for i, line in enumerate([
        "Clone the repository to your local machine.",
        "Create a virtual environment in the project directory.",
        "Install the required Python packages from requirements.txt.",
        "Download the model weights using the provided script.",
        "Run the smoke test to verify the installation.",
    ], 1):
        story.append(Paragraph(f"{i}. {line}", styles['BodyText']))
    story.append(Paragraph("Troubleshooting", styles['Heading2']))
    story.append(Paragraph(
        "If the model fails to load, check that your machine has enough free "
        "memory. If you see a CUDA error, verify that you are not running the "
        "Apple Silicon build on an Intel machine.",
        styles['BodyText']))

    doc.build(story)

    gt = """Installation Guide
Prerequisites
Before you begin, ensure you have the following:
* Python 3.10 or newer installed.
* At least 16 gigabytes of free disk space.
* A working internet connection for model downloads.
* macOS 14 or Ubuntu 22.04 as the operating system.
Steps
1. Clone the repository to your local machine.
2. Create a virtual environment in the project directory.
3. Install the required Python packages from requirements.txt.
4. Download the model weights using the provided script.
5. Run the smoke test to verify the installation.
Troubleshooting
If the model fails to load, check that your machine has enough free memory. If you see a CUDA error, verify that you are not running the Apple Silicon build on an Intel machine.
"""
    (GT_DIR / "list_heavy.txt").write_text(gt.strip() + "\n")
    return out


if __name__ == "__main__":
    files = [
        make_text_only_pdf(),
        make_table_heavy_pdf() if False else make_table_pdf(),  # rename guard
        make_multicolumn_pdf(),
        make_list_heavy_pdf(),
    ]
    for f in files:
        print(f"  {f.name}: {f.stat().st_size} bytes")
