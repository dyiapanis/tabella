#!/usr/bin/env python3
"""tabella MCP server — streamable-HTTP transport.

Serves the same tool surface as the stdio mcp_server.py (doc_read,
doc_read_meta, doc_convert, doc_create_document, doc_edit_pdf) over
streamable-HTTP: POST /mcp JSON-RPC, GET /status health, SSE responses when
Accept: text/event-stream, Mcp-Session-Id reuse, protocol 2025-06-18.

Keyless loopback by default (127.0.0.1:8602); TABELLA_TOKEN env makes it a
Bearer wall (401 on missing/wrong token). Python stdlib only.

Run:  python3 scripts/mcp_http_server.py [--addr 127.0.0.1:8602]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import mcp_server as stdio_srv  # reuse TOOLS + _handle_tool verbatim

PROTOCOL = "2025-06-18"
TOKEN = os.environ.get("TABELLA_TOKEN")


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
                        "tools": [t["name"] for t in stdio_srv.TOOLS]})
            return
        self._json({"jsonrpc": "2.0", "error": {"code": -32600, "message": "use POST /mcp"}}, 405)

    def do_POST(self):
        if self.path != "/mcp":
            self._json({"jsonrpc": "2.0", "error": {"code": -32600, "message": "unknown path"}}, 404)
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
                       "serverInfo": {"name": "tabella", "version": "2.0.0"},
                       "instructions": "Document lifecycle suite. Tools: doc_read, "
                                       "doc_read_meta, doc_convert, doc_create_document, "
                                       "doc_edit_pdf."}
            elif method == "notifications/initialized":
                self._json({}, 202, sid)
                return
            elif method == "tools/list":
                res = {"tools": stdio_srv.TOOLS}
            elif method == "tools/call":
                name = msg["params"]["name"]
                args = msg["params"].get("arguments") or {}
                out = stdio_srv._handle_tool(name, args)  # already a JSON string
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
