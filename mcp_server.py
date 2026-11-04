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
import sys
from pathlib import Path
from typing import Any

# ── Bootstrap: ensure docs venv exists before serving ───────────────────────
# shared with the HTTP server (scripts/mcp_http_server.py) — one implementation
from tabella.bootstrap import ensure_venv
from tabella import __version__
from tabella.toolspec import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOLS,
    TOOLS,
    UnknownToolError,
    handle_tool,
)

# ── MCP protocol ─────────────────────────────────────────────────────────────

class FramingError(Exception):
    """The bytes on stdin were not a readable message.

    Distinct from EOF: main() answers this with a -32700 and keeps serving.
    Returning None for it (what this used to do) exited the server, so one
    malformed header ended every later tool call in the session.
    """


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
            raw = stripped.split(":", 1)[1].strip()
            try:
                headers["content-length"] = int(raw)
            except ValueError as exc:
                raise FramingError(f"invalid Content-Length header: {raw!r}") from exc
            continue
        # Newline-delimited JSON (MCP stdio spec framing)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            if headers.get("content-length"):
                raise FramingError("Content-Length header without a JSON body") from exc
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

# ── Request handlers ─────────────────────────────────────────────────────────

def _handle_request(msg: dict) -> dict | None:
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": (msg.get("params") or {}).get("protocolVersion")
            if (msg.get("params") or {}).get("protocolVersion") in SUPPORTED_PROTOCOLS
            else PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "tabella", "version": __version__},
        })

    elif method == "notifications/initialized":
        return None  # notification — no response

    elif method == "tools/list":
        return _result(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        try:
            result_str = handle_tool(tool_name, tool_args)
        except UnknownToolError as exc:
            return _error(req_id, -32602, str(exc))
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
        venv_python = ensure_venv()
        if Path(venv_python).exists() and Path(sys.executable) != Path(venv_python):
            os.environ["TABELL_REEXEC"] = "1"
            os.execv(venv_python, [venv_python] + sys.argv)

    while True:
        try:
            msg = _read_message()
        except FramingError as exc:
            _write_message(_error(None, -32700, f"Parse error: {exc}"))
            continue
        if msg is None:
            break
        response = _handle_request(msg)
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    main()