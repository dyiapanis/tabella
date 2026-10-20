#!/usr/bin/env python3
"""tabella MCP server — stdio Model Context Protocol server.

Exposes three tools:
  - doc_read:       Read/extract text from any document
  - doc_convert:    Convert between formats via pandoc
  - doc_create:     Create documents from structured JSON or raw HTML/CSS

On first startup, if the docs venv is missing, the server runs
scripts/setup.sh to create a venv in PLUGIN_DATA (or ~/.venvs/docs)
and install all dependencies automatically.

Run standalone for testing:
    python3 mcp_server.py

Or wire into an MCP client via stdio.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── Bootstrap: ensure docs venv exists before serving ───────────────────────

def _ensure_venv() -> str:
    """Return the path to the docs venv Python, bootstrapping if needed.

    Checks DOCS_VENV_PYTHON env var first. If not set or the venv doesn't
    exist, runs scripts/setup.sh to create one in PLUGIN_DATA (provided by
    the v1 client) or ~/.venvs/docs as fallback.
    """
    # If DOCS_VENV_PYTHON is set and exists, use it
    venv_python = os.environ.get("DOCS_VENV_PYTHON")
    if venv_python and Path(venv_python).exists():
        return venv_python

    # Determine where to create the venv
    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        venv_dir = Path(plugin_data) / "venv"
    else:
        venv_dir = Path.home() / ".venvs" / "docs"

    # venv layout differs by platform: bin/python vs Scripts\python.exe
    if os.name == "nt":
        venv_python = str(venv_dir / "Scripts" / "python.exe")
    else:
        venv_python = str(venv_dir / "bin" / "python")

    if venv_dir.exists() and Path(venv_python).exists():
        return venv_python

    plugin_root = Path(__file__).parent.resolve()

    if os.name == "nt":
        # No bash on a stock Windows box — build the venv with the stdlib
        # venv module + the venv's own pip, mirroring scripts/setup.sh.
        pinned = plugin_root / "requirements-pinned.txt"
        sys.stderr.write("tabella: bootstrapping docs venv (first run)...\n")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            result = subprocess.run(
                [venv_python, "-m", "pip", "install", "--quiet", "--require-hashes",
                 "-r", str(pinned)],
                capture_output=True, text=True, timeout=600,
            )
        if result.returncode != 0:
            sys.stderr.write(f"tabella: bootstrap failed: {result.stderr[:500]}\n")
        else:
            sys.stderr.write("tabella: venv ready\n")
        return venv_python

    # POSIX bootstrap: run the setup script
    setup_script = plugin_root / "scripts" / "setup.sh"
    if not setup_script.exists():
        sys.stderr.write(f"tabella: setup script not found at {setup_script}\n")
        return venv_python  # let tool calls fail with a helpful error

    sys.stderr.write("tabella: bootstrapping docs venv (first run)...\n")
    data_dir = str(venv_dir.parent) if plugin_data else str(venv_dir)
    result = subprocess.run(
        ["bash", str(setup_script), data_dir],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        sys.stderr.write(f"tabella: bootstrap failed: {result.stderr[:500]}\n")
    else:
        sys.stderr.write("tabella: venv ready\n")
    
    return venv_python

# ── MCP protocol ─────────────────────────────────────────────────────────────

def _read_message() -> dict | None:
    """Read one JSON-RPC message from stdin.

    MCP stdio transport (spec): newline-delimited JSON, one message per line.
    Content-Length framed input (LSP convention) is tolerated for robustness
    but is NOT what spec-compliant clients send.
    """
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            continue
        if ":" in stripped and stripped.lower().startswith("content-length:"):
            headers["content-length"] = int(stripped.split(":", 1)[1].strip())
            continue
        # Newline-delimited JSON (MCP stdio spec framing)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            if headers.get("content-length"):
                return None
            continue  # tolerate stray blank/garbage lines


def _write_message(msg: dict) -> None:
    """Write a JSON-RPC message to stdout — newline-delimited (MCP stdio spec)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


# ── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "doc_read",
        "description": (
            "Read and extract text from documents. Uses anydoc for office formats "
            "(DOCX, XLSX, PPTX, ODT, RTF, EPUB, PDF → Markdown) and LiteParse for OCR "
            "(scanned PDFs, images). Plain text files read directly."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the document.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return.",
                    "default": 1000000,
                },
                "extract_images": {
                    "type": "boolean",
                    "description": "Extract text from images via OCR (LiteParse + Tesseract).",
                    "default": True,
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_read_meta",
        "description": "Read document metadata (PDF info, image EXIF, etc.) via LiteParse.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the document.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_convert",
        "description": (
            "Convert documents between formats (PDF, DOCX, HTML, ODT, EPUB, etc.) "
            "using pandoc + LaTeX. Requires system pandoc and texlive-xetex for PDF output."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Absolute path to the source document.",
                },
                "to_format": {
                    "type": "string",
                    "description": "Target format: pdf, docx, html, odt, epub, etc.",
                },
                "from_format": {
                    "type": "string",
                    "description": "Optional source format hint (e.g. markdown, html). Pandoc infers from extension if omitted.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional absolute output path. Defaults to the documents directory (DOCS_OUTPUT_DIR or ~/Documents).",
                },
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional extra pandoc CLI flags.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional subfolder under documents/ (e.g. 'reports').",
                },
            },
            "required": ["input_path", "to_format"],
        },
    },
    {
        "name": "doc_create_document",
        "description": (
            "Create .docx, .xlsx, .pptx, .pdf, .odt, .ods, or .odp documents. "
            "For PDFs: pass structured JSON for document-style output, or pass "
            '{\"html\": \"<html>...</html>\"} with full CSS (Grid, Flexbox, gradients, '
            "themes) for visual/print-ready PDFs via weasyprint. "
            "Supports page_size, header, footer, page_numbers options."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["docx", "xlsx", "pptx", "pdf", "odt", "ods", "odp"],
                    "description": "Output document format.",
                },
                "content": {
                    "anyOf": [
                        {"type": "string", "description": "Plain text or HTML content (auto-detected and normalized)."},
                        {"type": "object", "description": "Structured content dict. Format-specific schema."},
                    ],
                    "description": "Document content. Accepts plain text, HTML, or structured dict.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Absolute path for the output file. Defaults to the documents directory.",
                },
                "template": {
                    "type": "string",
                    "description": "Optional template path — honored by docx (.docx/.dotx) and pptx (.pptx/.potx) creation: styles, theme, headers/footers and slide layouts load from the file. Ignored by every other format.",
                },
                "options": {
                    "type": "object",
                    "description": "Optional format-specific options (title, page_size, auto_size, etc.)",
                },
            },
            "required": ["format", "content"],
        },
    },
    {
        "name": "doc_edit_pdf",
        "description": "Edit a PDF page using search-and-replace via PyMuPDF. Provide a natural language instruction like 'change <search> to <replace>'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the PDF file.",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number to edit (1-indexed).",
                    "default": 1,
                },
                "instruction": {
                    "type": "string",
                    "description": "Natural language instruction for the edit (e.g. 'change \"foo\" to \"bar\"').",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional output path. Defaults to <original>_edited.pdf",
                },
            },
            "required": ["path", "instruction"],
        },
    },
]

# ── Tool dispatch ────────────────────────────────────────────────────────────

def _handle_tool(name: str, args: dict) -> str:
    """Dispatch a tool call to the appropriate handler and return JSON result."""
    try:
        if name == "doc_read":
            from tabella.read import read
            text = read(
                args["path"],
                max_chars=args.get("max_chars", 1_000_000),
                extract_images=args.get("extract_images", True),
            )
            return json.dumps({
                "success": True,
                "path": args["path"],
                "text": text,
                "length": len(text),
                "message": f"Read {len(text)} chars from {args['path']}",
            })

        elif name == "doc_read_meta":
            from tabella.read import read_meta
            meta = read_meta(args["path"])
            return json.dumps({"success": True, "path": args["path"], "metadata": meta})

        elif name == "doc_convert":
            from tabella.convert import doc_convert
            result = doc_convert(
                input_path=args["input_path"],
                to_format=args["to_format"],
                from_format=args.get("from_format"),
                output_path=args.get("output_path"),
                extra_args=args.get("extra_args"),
                category=args.get("category"),
            )
            return json.dumps(result)

        elif name == "doc_create_document":
            from tabella.create import create_document
            output_path = args.get("output_path")
            if not output_path:
                from tabella import get_output_dir
                import time
                ts = int(time.time())
                fmt = args["format"]
                output_path = str(get_output_dir() / f"doc_{ts}.{fmt}")
            result = create_document(
                format=args["format"],
                content=args["content"],
                output_path=output_path,
                template=args.get("template"),
                options=args.get("options"),
            )
            return json.dumps(result)

        elif name == "doc_edit_pdf":
            from tabella.create import _edit_pdf_text
            result = _edit_pdf_text(
                path=args["path"],
                page=args.get("page", 1),
                instruction=args["instruction"],
                output_path=args.get("output_path"),
            )
            return json.dumps(result)

        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"})


# ── Request handlers ─────────────────────────────────────────────────────────

def _handle_request(msg: dict) -> dict | None:
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "tabella", "version": "2.0.0"},
        })

    elif method == "notifications/initialized":
        return None  # notification — no response

    elif method == "tools/list":
        return _result(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        result_str = _handle_tool(tool_name, tool_args)
        return _result(req_id, {
            "content": [{"type": "text", "text": result_str}],
        })

    elif method == "ping":
        return _result(req_id, {})

    else:
        if req_id is not None:
            return _error(req_id, -32601, f"Method not found: {method}")
        return None


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    # Bootstrap venv on first run, then re-exec into its python so all tool
    # imports (weasyprint/python-docx/...) resolve from the venv, not the
    # client's interpreter. Guard against exec loops via the env marker.
    if not os.environ.get("TABELL_REEXEC"):
        venv_python = _ensure_venv()
        if Path(venv_python).exists() and Path(sys.executable) != Path(venv_python):
            os.environ["TABELL_REEXEC"] = "1"
            os.execv(venv_python, [venv_python] + sys.argv)

    while True:
        msg = _read_message()
        if msg is None:
            break
        response = _handle_request(msg)
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    main()