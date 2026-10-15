# tabella

A portable document lifecycle suite: create, convert, and read documents
from structured JSON or raw HTML/CSS.

## Cross-Platform Compatibility

This package conforms to the [Agent Plugins v1.0.0](https://agent-plugins.org/specification)
specification. It works with any compatible AI agent client that supports
MCP servers, including:

- [Hermes Agent](https://hermes-agent.nousresearch.com)
- [Cursor](https://cursor.com)
- [Claude Desktop](https://claude.ai/download)
- Any client that supports the Model Context Protocol

### Three installation paths

**Transports:** the plugin ships both.

- **stdio (default)** — the declaring client spawns `mcp_server.py` itself
  (Agent Plugins v1 lifecycle; `PLUGIN_ROOT`/`PLUGIN_DATA` injected by the
  client). Nothing to run by hand.
- **streamable-HTTP (self-host lane)** — for clients that prefer connecting
  to a URL, run the server yourself:

  ```bash
  python3 scripts/mcp_http_server.py   # serves 127.0.0.1:8602
  ```

  First run bootstraps the dependency venv (or `scripts/setup.sh`);
  `TABELLA_TOKEN` enables bearer auth. Then point an `mcp.json`
  `streamable-http` entry at `http://127.0.0.1:8602/mcp`.



**Agent Plugins v1 package** — clients that support the v1 spec auto-discover
`plugin.json` + `mcp.json` from the repo root and launch the MCP server:

```bash
# Hermes Agent
hermes plugins install dyiapanis/tabella --no-enable
hermes plugins enable tabella

# Other v1-compatible clients: follow your client's plugin installation instructions
```

**MCP server (manual)** — point any MCP-compatible client at the server directly:

```json
{
  "mcpServers": {
    "tabella": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/tabella/mcp_server.py"]
    }
  }
}
```

**pip install** — use the Python library directly:

```bash
pip install tabella-docs[all]
```

Or install only the modules you need:

```bash
pip install tabella-docs[create]    # python-docx, openpyxl, python-pptx, weasyprint, odfpy
pip install tabella-docs[read]      # firecrawl-anydoc, liteparse, PyMuPDF
pip install tabella-docs[convert]   # no python deps (needs system pandoc + texlive-xetex)
```

## Modules

### Create

Generate documents from structured JSON content or raw HTML/CSS:

- **DOCX** — Word documents (python-docx)
- **XLSX** — Spreadsheets (openpyxl)
- **PPTX** — Presentations (python-pptx)
- **PDF** — Print-ready documents and visual designs (WeasyPrint)
  - Document-style: structured JSON → HTML → PDF
  - Visual-style: raw HTML/CSS (Grid, Flexbox, gradients, themes) → PDF
- **ODT/ODS/ODP** — OpenDocument formats (odfpy)

Accepts plain strings (auto-normalized), HTML, or structured dicts with
sections, sheets, slides, tables, images, and page breaks.

### Convert

Format conversion via pandoc + LaTeX (page size, margins, headers/footers
configurable). **Pandoc 3.1 supports 44 input and 54 output formats** —
`doc_convert` passes your `from`/`to` through, so all of them work. The
everyday set:

| Format | In | Out | Notes |
|---|---|---|---|
| Markdown (`.md`, variants) | ✅ | ✅ | gfm, commonmark, multimarkdown, strict… |
| HTML | ✅ | ✅ | html4/html5, chunkedhtml |
| DOCX (Word) | ✅ | ✅ | |
| ODT | ✅ | ✅ | + `opendocument` |
| PDF | ✅ | ✅ | in: text-based PDFs (pandoc's pdf reader); out: needs `pdflatex`/`xelatex` (texlive) — engine auto-selected |
| LaTeX (`.tex`) | ✅ | ✅ | incl. beamer slides out |
| RST | ✅ | ✅ | |
| EPUB | ✅ | ✅ | out: epub2/epub3 |
| CSV / TSV | ✅ | ✅ | out via markdown/AST route |
| RTF | ✅ | ✅ | |
| Plain text (`.txt`) | ✅ | ✅ | |
| Org-mode, MediaWiki, Jira wiki, Textile, DocBook, FB2, OPML, IPynb, JATS | ✅ | ✅ | writers for most |
| Typst / man / ms / texinfo / AsciiDoc | ✅ | ✅ | typst in+out |
| Presentations | — | ✅ | beamer, revealjs, slidy, s5, dzslides (from any reader, Markdown especially) |
| Pandoc AST (JSON) | ✅ | ✅ | for programmatic pipelines |

Everything not in the table: if `pandoc --list-input-formats` /
`--list-output-formats` lists it, `doc_convert` accepts it as-is — unknown
extensions pass through untouched.

### Read

Extract text and metadata from any document:

- **Office formats** (DOCX, DOC, XLSX, XLSB, PPTX, PPT, ODT, ODS, ODP, RTF,
  EPUB, CSV) and **text-based PDFs** → GitHub-Flavored Markdown via
  [anydoc](https://github.com/firecrawl/anydoc) (~4ms, in-process)
- **Scanned PDFs** and **images** (JPG, PNG, TIFF) → OCR via
  [LiteParse](https://github.com/run-llama/liteparse) (Tesseract)
- **Plain text** (.txt, .md, .json, .py, .yaml, etc.) → direct file read
- Returns structured Markdown (office formats) or plain text (OCR, plain text)

## Prerequisites

### Create module

The create module uses a separate Python venv for heavy document libraries.
Set `DOCS_VENV_PYTHON` to point to it:

```bash
# Create a dedicated venv
python -m venv ~/.venvs/docs
~/.venvs/docs/bin/pip install python-docx openpyxl python-pptx weasyprint odfpy Pillow lxml PyMuPDF firecrawl-anydoc liteparse
```

Or install the libraries into your main Python environment:

```bash
pip install tabella-docs[create]
```

### Read module

```bash
~/.venvs/docs/bin/pip install firecrawl-anydoc liteparse PyMuPDF
```

Or:

```bash
pip install tabella-docs[read]
```

### Convert module

```bash
pip install tabella-docs[convert]
```

Requires system-installed pandoc and a LaTeX engine:

```bash
# Debian/Ubuntu
sudo apt install pandoc texlive-xetex

# macOS
brew install pandoc basictex

# Arch
sudo pacman -S pandoc texlive
```

### WeasyPrint system dependencies (PDF creation)

```bash
# Debian/Ubuntu
sudo apt install libcairo2 libpango-1.0-0 libgdk-pixbuf-2.0-0

# macOS
brew install cairo pango gdk-pixbuf
```

## Installation from source

```bash
git clone https://github.com/dyiapanis/tabella.git
cd tabella
pip install -e ".[all]"
```

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `DOCS_VENV_PYTHON` | Python binary for document libraries | `PLUGIN_DATA/venv/bin/python` or `~/.venvs/docs/bin/python` |
| `DOCS_OUTPUT_DIR` | Default output directory for generated documents | `~/Documents` |
| `PLUGIN_DATA` | Client-managed data directory (set by v1 client) | — |
| `PLUGIN_ROOT` | Plugin root directory (set by v1 client) | — |

### Automatic bootstrap

On first startup, the MCP server checks if the docs venv exists. If not,
it runs `scripts/setup.sh` to create a venv in `PLUGIN_DATA` (provided by
the v1 client) or `~/.venvs/docs` as fallback, and installs all dependencies:
python-docx, openpyxl, python-pptx, weasyprint, odfpy, PyMuPDF,
firecrawl-anydoc, liteparse.

This means the v1 package is fully self-contained — no manual pip install
required. The bootstrap runs once; subsequent startups use the existing venv.

## Usage

### Create a PDF from HTML/CSS

```python
from agent_docs.create import create_document

result = create_document(
    format="pdf",
    content={"html": "<html><body><h1>Hello</h1></body></html>"},
    output_path="/tmp/output.pdf",
    options={"page_size": "A4"}
)
```

### Read a DOCX file

```python
from agent_docs.read import read

text = read("/path/to/document.docx")
# Returns GitHub-Flavored Markdown
```

### Convert Markdown to PDF

```python
from agent_docs.convert import doc_convert

result = doc_convert(
    input_path="/path/to/input.md",
    to_format="pdf",
    output_path="/path/to/output.pdf"
)
```

### Via MCP

The bundled MCP server exposes five tools: `doc_read`, `doc_read_meta`,
`doc_convert`, `doc_create_document`, `doc_edit_pdf`. Any MCP-compatible
client can call these directly.

## License

MIT