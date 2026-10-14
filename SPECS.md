# tabella — Specifications

## Architecture

Three independent modules, each with its own engine(s):

### Read (`agent_docs.read`)

Two-engine dispatch — anydoc primary, LiteParse fallback:

| Format | Engine | Output | Speed |
|--------|--------|--------|-------|
| DOCX, DOCM | anydoc | GitHub-Flavored Markdown | ~4ms |
| DOC (legacy) | anydoc | Markdown (OLE/CFB parser) | ~4ms |
| XLSX, XLS, XLSB | anydoc | Markdown tables (calamine) | ~4ms |
| PPTX, PPT, PPS, POT | anydoc | Markdown (slides, notes) | ~4ms |
| ODT, ODS, ODP | anydoc | Markdown (OpenDocument) | ~4ms |
| RTF | anydoc | Markdown (RTF parser) | ~4ms |
| EPUB | anydoc | Markdown (ZIP + XHTML) | ~4ms |
| CSV | anydoc | Markdown table | ~4ms |
| PDF (text layer) | anydoc | Markdown (pdf-inspector) | ~4ms |
| PDF (scanned) | LiteParse | Plain text (Tesseract OCR) | ~1-5s |
| JPG, PNG, TIFF, WEBP | LiteParse | Plain text (Tesseract OCR) | ~1-5s |
| TXT, MD, JSON, PY, YAML... | Direct read | Raw text | instant |

Dispatch logic:
1. Plain text extension → direct file read (no subprocess)
2. Image extension → LiteParse OCR
3. Office format or PDF → anydoc first
   - If anydoc returns empty (scanned PDF) → LiteParse OCR fallback

Tools: `doc_read(path, max_chars, extract_images)`, `doc_read_meta(path)`

### Create (`agent_docs.create`)

Structured JSON or raw HTML/CSS → document:

| Format | Engine | Input |
|--------|--------|-------|
| DOCX | python-docx | Structured JSON (sections, tables, images) |
| XLSX | openpyxl | Structured JSON (sheets, rows, styles) |
| PPTX | python-pptx | Structured JSON (slides, layouts) |
| PDF | weasyprint | Structured JSON → HTML, or raw HTML/CSS |
| ODT | odfpy | Structured JSON |
| ODS | odfpy | Structured JSON |
| ODP | odfpy | Structured JSON |

PDF generation supports two modes:
- **Document-style**: structured JSON with pages/elements → HTML → PDF
- **Visual-style**: `content={"html": "<html>...</html>"}` with full CSS
  (Grid, Flexbox, gradients, themed colors, custom fonts) → PDF

Tool: `doc_create_document(format, content, output_path, options)`

### Convert (`agent_docs.convert`)

Pandoc-based format conversion:

- Markdown → PDF (via xelatex/pdflatex)
- Markdown → DOCX, HTML, ODT, EPUB
- Any pandoc-supported format pair

Tool: `doc_convert(src, to_format, output_path)`

### Edit (`agent_docs.create`)

PDF text editing via PyMuPDF search-and-replace:

Tool: `doc_edit_pdf(path, page, instruction, output_path)`

## Dependencies

### Read module
- `firecrawl-anydoc` — office format parsing + text PDF extraction (Rust, MIT)
- `liteparse` — OCR for scanned PDFs and images (Rust + Tesseract, Apache-2.0)
- `PyMuPDF` — PDF editing (search-and-replace)

### Create module
- `python-docx` — DOCX creation
- `openpyxl` — XLSX creation
- `python-pptx` — PPTX creation
- `weasyprint` — PDF generation (HTML/CSS → PDF)
- `odfpy` — ODT/ODS/ODP creation
- `Pillow` — Image processing (transitive dep)
- `lxml` — XML processing (transitive dep)

### Convert module
- `pandoc` (system) — format conversion
- `texlive-xetex` (system) — LaTeX for PDF generation

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DOCS_VENV_PYTHON` | Path to docs venv Python binary | `~/.venvs/docs/bin/python` |
| `DOCS_OUTPUT_DIR` | Default output directory for documents | `~/documents` |