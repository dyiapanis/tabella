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
from tabella import __version__
from tabella.toolspec import PROTOCOL_VERSION, SUPPORTED_PROTOCOLS, TOOLS, handle_tool

PROTOCOL = PROTOCOL_VERSION  # one constant, shared with the stdio server

# ── Tool definitions ─────────────────────────────────────────────────────────

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
                requested = (msg.get("params") or {}).get("protocolVersion")
                res = {"protocolVersion": requested if requested in SUPPORTED_PROTOCOLS else PROTOCOL,
                       "capabilities": {"tools": {}},
                       "serverInfo": {"name": "tabella", "version": __version__},
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
                out = handle_tool(name, args)  # already a JSON string
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
