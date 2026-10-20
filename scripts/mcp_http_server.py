#!/usr/bin/env python3
"""tabella MCP server — streamable-HTTP transport (stdio removed).

Tool surface: doc_read, doc_read_meta, doc_convert, doc_create_document,
doc_edit_pdf. POST /mcp JSON-RPC, GET /status health, SSE responses when
Accept: text/event-stream, Mcp-Session-Id reuse, protocol 2025-06-18.

Keyless loopback by default (127.0.0.1:8602); TABELLA_TOKEN env makes it a
Bearer wall (401 on missing/wrong token). Python stdlib only.

On main() startup the docs venv bootstrap runs (scripts/setup.sh) when
DOCS_VENV_PYTHON is unset or the venv is missing — idempotent, stderr-noted,
never fatal.

Run:  python3 scripts/mcp_http_server.py [--addr 127.0.0.1:8602]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

PROTOCOL = "2025-06-18"
# Catalog review finding 3: the loopback lane requires a token OUT OF THE BOX.
# Order: TABELLA_TOKEN env > persisted generated token (<PLUGIN_DATA|~/.local/share)/tabella/http.token).
def _resolve_token() -> str:
    env = os.environ.get("TABELLA_TOKEN")
    if env:
        return env
    data_dir = os.environ.get("PLUGIN_DATA") or os.path.expanduser("~/.local/share/tabella")
    os.makedirs(data_dir, exist_ok=True)
    tok_file = os.path.join(data_dir, "http.token")
    if os.path.exists(tok_file):
        return open(tok_file, encoding="utf-8").read().strip()
    import secrets
    tok = secrets.token_urlsafe(32)
    fd = os.open(tok_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok + "\n")
    sys.stderr.write(f"tabella: generated HTTP lane token at {tok_file}\n")
    return tok


TOKEN = _resolve_token()

# ── Bootstrap: ensure docs venv exists before serving ───────────────────────
# shared with the stdio server (mcp_server.py) — one implementation
from tabella.bootstrap import ensure_venv

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
            '{"html": "<html>...</html>"} with full CSS (Grid, Flexbox, gradients, '
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

# ── HTTP transport ─────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # quieter
        pass

    def _auth(self) -> bool:
        if not TOKEN:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _sse(self, payload: dict, sid: str | None):
        body = "event: message\ndata: " + json.dumps(payload) + "\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        if sid:
            self.send_header("Mcp-Session-Id", sid)
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def _json(self, payload: dict, code: int = 200, sid: str | None = None):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        if sid:
            self.send_header("Mcp-Session-Id", sid)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._json({"ok": True, "server": "tabella",
                        "tools": [t["name"] for t in TOOLS]})
            return
        self._json({"jsonrpc": "2.0", "error": {"code": -32600, "message": "use POST /mcp"}}, 405)

    def do_POST(self):
        if self.path != "/mcp":
            self._json({"jsonrpc": "2.0", "error": {"code": -32600, "message": "unknown path"}}, 404)
            return
        origin = self.headers.get("Origin")
        if origin:
            self._json({"jsonrpc": "2.0", "error": {"code": -32000, "message": "blocked: request must not carry an Origin header (browser-CSRF guard)"}}, 403)
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype and ctype != "application/json":
            self._json({"jsonrpc": "2.0", "error": {"code": -32000, "message": f"Content-Type must be application/json, got {ctype!r}"}}, 415)
            return
        if not self._auth():
            self._json({"jsonrpc": "2.0", "error": {"code": -32000, "message": "unauthorized"}}, 401)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            msg = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"jsonrpc": "2.0", "error": {"code": -32700, "message": "bad json"}}, 400)
            return
        sid = (self.headers.get("Mcp-Session-Id")
               or msg.get("params", {}).get("_meta", {}).get("session") or "s1")
        method = msg.get("method", "")
        mid = msg.get("id")
        want_sse = "text/event-stream" in (self.headers.get("Accept") or "")
        try:
            if method == "initialize":
                res = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                       "serverInfo": {"name": "tabella", "version": "2.0.2"},
                       "instructions": "Document lifecycle suite. Tools: doc_read, "
                                       "doc_read_meta, doc_convert, doc_create_document, "
                                       "doc_edit_pdf."}
            elif method == "notifications/initialized":
                self._json({}, 202, sid)
                return
            elif method == "tools/list":
                res = {"tools": TOOLS}
            elif method == "tools/call":
                name = msg["params"]["name"]
                args = msg["params"].get("arguments") or {}
                out = _handle_tool(name, args)  # already a JSON string
                res = {"content": [{"type": "text", "text": out}]}
            elif method == "ping":
                res = {}
            else:
                self._json({"jsonrpc": "2.0", "id": mid,
                            "error": {"code": -32601, "message": method}}, sid=sid)
                return
        except Exception as e:
            self._json({"jsonrpc": "2.0", "id": mid,
                        "error": {"code": -32603, "message": str(e)[:300]}}, sid=sid)
            return
        payload = {"jsonrpc": "2.0", "id": mid, "result": res}
        if want_sse:
            self._sse(payload, sid)
        else:
            self._json(payload, sid=sid)


def main() -> None:
    # Bootstrap venv, then re-exec into the venv python so tool imports
    # resolve from it rather than the ambient interpreter. Env marker guards
    # against exec-loop when the venv python is unusable.
    if not os.environ.get("TABELL_REEXEC"):
        venv_python = ensure_venv()
        if Path(venv_python).exists() and Path(sys.executable) != Path(venv_python):
            os.environ["TABELL_REEXEC"] = "1"
            os.execv(venv_python, [venv_python] + sys.argv)

    ap = argparse.ArgumentParser(prog="tabella-mcp-http")
    ap.add_argument("--addr", default="127.0.0.1:8602")
    a = ap.parse_args()
    host, port = a.addr.rsplit(":", 1)
    httpd = ThreadingHTTPServer((host, int(port)), Handler)
    httpd.daemon_threads = True
    print(f"tabella-mcp-http on http://{host}:{port}/mcp "
          f"(auth={'token' if TOKEN else 'keyless-loopback'})", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
