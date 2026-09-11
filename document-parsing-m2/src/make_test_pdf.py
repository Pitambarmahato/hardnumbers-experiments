"""Generate a 4-page synthetic test PDF for smoke testing the parsers."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.units import inch
from pathlib import Path

OUT = Path("data/pdfs/test_simple.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)

doc = SimpleDocTemplate(str(OUT), pagesize=letter)
styles = getSampleStyleSheet()
story = []

# Page 1: plain text
story.append(Paragraph("Test Document for OCR Benchmarking", styles['Title']))
story.append(Spacer(1, 0.3 * inch))
story.append(Paragraph(
    "This is the first paragraph of a test document. It contains a known set of "
    "words so we can measure OCR accuracy with edit distance.",
    styles['BodyText']))
story.append(Paragraph(
    "The quick brown fox jumps over the lazy dog. Pack my box with five dozen "
    "liquor jugs. How vexingly quick daft zebras jump!",
    styles['BodyText']))
story.append(PageBreak())

# Page 2: a table
story.append(Paragraph("Quarterly Revenue Breakdown", styles['Heading2']))
story.append(Spacer(1, 0.2 * inch))
data = [
    ['Quarter', 'Revenue', 'Cost', 'Profit'],
    ['Q1 2026', '$1.2M', '$0.8M', '$0.4M'],
    ['Q2 2026', '$1.5M', '$0.9M', '$0.6M'],
    ['Q3 2026', '$1.7M', '$1.0M', '$0.7M'],
    ['Q4 2026', '$1.9M', '$1.1M', '$0.8M'],
]
t = Table(data)
t.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
]))
story.append(t)
story.append(PageBreak())

# Page 3: structured prose
story.append(Paragraph("Section A: Introduction", styles['Heading2']))
story.append(Paragraph(
    "Local document parsing has become a critical capability for "
    "retrieval-augmented generation pipelines. The four open-source parsers "
    "benchmarked in this study differ significantly in both speed and accuracy.",
    styles['BodyText']))
story.append(Paragraph("Section B: Methodology", styles['Heading2']))
story.append(Paragraph(
    "Each parser was run on the same set of PDF inputs, with wall time, peak "
    "memory, and output text captured. Ground truth was established by manual "
    "transcription or by extracting the source LaTeX.",
    styles['BodyText']))
story.append(PageBreak())

# Page 4: numbered list
story.append(Paragraph("Key Findings", styles['Heading2']))
story.append(Paragraph("1. The fastest parser is not always the most accurate.", styles['BodyText']))
story.append(Paragraph(
    "2. PaddleOCR-VL-1.6 has 0.9B parameters and leads OmniDocBench v1.6 at 96.34.",
    styles['BodyText']))
story.append(Paragraph(
    "3. Docling's TableFormer model preserves borderless accounting tables "
    "better than heuristics-based parsers.",
    styles['BodyText']))

doc.build(story)
print(f"PDF generated: {OUT} ({OUT.stat().st_size} bytes)")
