---
name: pdf
description: Read, create, and review PDF files using Python. Use when the user wants to read a PDF, generate a new PDF, fill out a PDF form, merge/split PDFs, or do any PDF-related task.
metadata:
  { "mmclaw": { "emoji": "📄", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["python3"], "pip": ["reportlab>=4.0.0", "pypdf>=4.0.0"] } } }
---

# PDF Skill

Use this skill when the user wants to read, create, edit, merge, split, or inspect PDF files. Trigger phrases: "PDF", "read PDF", "create PDF", "generate PDF", "merge PDFs", "split PDF", "fill PDF form", "extract text from PDF".

## Dependencies

`reportlab` and `pypdf` are generally available. `pdfplumber` may or may not be installed — check at runtime and degrade gracefully if absent:

```python
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
```

## Reading PDFs

### Preferred: render to PNG then read visually

Convert PDF pages to PNG images, then read them as images. This is the most reliable method because it captures figures, tables, diagrams, and layout that text extraction misses.

```python
from PIL import Image
import pypdf, io

def pdf_pages_to_pil(pdf_path):
    """Render each PDF page to a PIL Image via pypdf + Pillow."""
    images = []
    reader = pypdf.PdfReader(pdf_path)
    for page in reader.pages:
        for img_obj in page.images:
            images.append(Image.open(io.BytesIO(img_obj.data)))
    return images
```

> If the PDF contains vector graphics or complex layout without embedded raster images, fall back to text extraction (see below) and note to the user that full visual rendering requires poppler (`apt install poppler-utils` / `brew install poppler`).

### Text extraction fallback

Use `pdfplumber` when available; otherwise fall back to `pypdf`:

```python
def extract_text(pdf_path):
    if HAS_PDFPLUMBER:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    else:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)
```

`pdfplumber` gives better table and layout-aware extraction. `pypdf` is the safe baseline. Never rely solely on text extraction when the PDF contains figures or diagrams — always note the limitation to the user.

### Installing pdfplumber (optional upgrade)

```bash
pip install "pdfplumber>=0.11.0"
```

## Creating PDFs

Use `reportlab` as the primary tool for generating new PDFs.

### Basic document

```python
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm

def create_pdf(output_path, title, body_text):
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 0.5*cm),
        Paragraph(body_text, styles["BodyText"]),
    ]
    doc.build(story)
```

### Render and inspect after every meaningful change

After each content addition, layout change, or style update, render pages to images and inspect before continuing:

```python
from PIL import Image
import pypdf, io

def render_pdf_pages(pdf_path):
    """Return list of PIL Images, one per page (embedded raster only)."""
    reader = pypdf.PdfReader(pdf_path)
    images = []
    for i, page in enumerate(reader.pages):
        page_images = list(page.images)
        if page_images:
            images.append(Image.open(io.BytesIO(page_images[0].data)))
        else:
            print(f"Page {i+1}: no embedded raster image found - inspect manually.")
    return images
```

Open and review each returned image. If anything looks off — clipped text, overlapping elements, misaligned tables — fix the source and re-render before continuing.

## Merging and Splitting PDFs

```python
import pypdf

def merge_pdfs(input_paths, output_path):
    writer = pypdf.PdfWriter()
    for path in input_paths:
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)

def split_pdf(input_path, output_dir):
    reader = pypdf.PdfReader(input_path)
    for i, page in enumerate(reader.pages):
        writer = pypdf.PdfWriter()
        writer.add_page(page)
        out = f"{output_dir}/page_{i+1}.pdf"
        with open(out, "wb") as f:
            writer.write(f)
        print(f"Saved: {out}")
```

## Quality Expectations

- Consistent typography, spacing, margins, and color palette across all pages.
- No clipped text, overlapping elements, black squares, or broken tables.
- Charts, tables, and images must be sharp, well-aligned, and properly labeled.
- Use ASCII hyphens only — never U+2011 non-breaking hyphens or other Unicode dashes.
- No placeholder text, tool-internal tokens, or malformed URLs in the final document.

## Final Checks

Do not deliver the PDF until a visual inspection shows zero formatting defects. Verify page numbering, headers/footers, and section transitions. Fix any typos, spacing, or alignment issues found and re-render for a final pass.