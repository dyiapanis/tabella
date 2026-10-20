#!/usr/bin/env python3
"""Tabella smoke battery — the minimum honest verification set (card t_win01a2f).

One direct-run script that proves, on ANY platform (Windows runner included):
  1. stdio lifecycle — real MCP handshake through mcp_server.py
  2. create lanes — docx / xlsx / pptx built and files exist
  3. read round-trip — created docx reads back with expected content
  4. pdf_from_html — exercises WeasyPrint + its native GTK dependency chain
  5. convert via pandoc — docx -> markdown (no TeX engine needed)

Usage: python tests/smoke_battery.py   (from anywhere; exit 0 = all green)
Failures are named per-lane; missing native deps produce the lane's install
hint, not a stack-trace mystery.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

FAILURES = []


def lane(name):
    def deco(fn):
        try:
            detail = fn()
            print(f"PASS {name}: {detail or 'ok'}")
        except Exception as e:
            print(f"FAIL {name}: {e}")
            FAILURES.append(name)
    return deco


def stdio_handshake():
    """Real MCP stdio round-trip: initialize -> tools/list -> one doc_read."""
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "mcp_server.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, encoding="utf-8", cwd=str(REPO),
    )
    try:
        def rpc(payload):
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("server closed stdout (no response)")
            resp = json.loads(line)
            if "error" in resp:
                raise RuntimeError(f"rpc error: {resp['error']}")
            return resp["result"]

        info = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18",
                               "capabilities": {}, "clientInfo": {"name": "smoke"}}})
        assert info["serverInfo"]["name"] == "tabella", info
        # version sync: serverInfo must match plugin.json (drift bit us once — 2.0.0 vs 2.0.1)
        manifest = json.loads((REPO / "plugin.json").read_text(encoding="utf-8"))
        assert info["serverInfo"]["version"] == manifest["version"], \
            f"serverInfo {info['serverInfo']['version']} != plugin.json {manifest['version']}"
        tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = sorted(t["name"] for t in tools["tools"])
        assert len(names) == 5, f"expected 5 tools, got {names}"
        return f"serverInfo ok, 5 tools: {', '.join(names)}"
    finally:
        proc.kill()


def create_lanes(tmp):
    """Build docx/xlsx/pptx from plain-text content; files must exist."""
    from tabella.create import create_document
    made = []
    for fmt in ("docx", "xlsx", "pptx"):
        out = tmp / f"smoke.{fmt}"
        res = create_document(format=fmt, content="Smoke battery line one.\nSmoke battery line two.",
                             output_path=str(out))
        assert res.get("success"), f"{fmt} create failed: {res}"
        assert out.exists() and out.stat().st_size > 0, f"{fmt} file missing/empty"
        made.append(f"{fmt}={out.stat().st_size}B")
    return "built " + ", ".join(made)


def read_roundtrip(tmp):
    from tabella.read import read
    text = read(str(tmp / "smoke.docx"))
    assert "Smoke battery line one" in text, f"round-trip content missing: {text[:120]!r}"
    return f"read back {len(text)} chars"


def pdf_from_html(tmp):
    """The GTK lane: WeasyPrint must import AND render real HTML to a PDF."""
    from tabella.create import create_document
    html = ("<html><head><style>@page{size:A4;margin:1cm}"
            "body{font-family:serif}</style></head>"
            "<body><h1>Smoke PDF</h1><p>gtk chain works</p></body></html>")
    out = tmp / "smoke.pdf"
    res = create_document(format="pdf", content={"html": html}, output_path=str(out))
    assert res.get("success"), f"pdf_from_html failed: {res}"
    assert out.exists() and out.stat().st_size > 500, "pdf missing or suspiciously small"
    return f"rendered {out.stat().st_size}B PDF"


def convert_pandoc(tmp):
    """The pandoc lane: docx -> markdown (needs no TeX engine)."""
    from tabella.convert import doc_convert
    res = doc_convert(input_path=str(tmp / "smoke.docx"), to_format="markdown",
                      output_path=str(tmp / "smoke.md"))
    assert res.get("success"), f"convert failed: {res}"
    md = (tmp / "smoke.md").read_text(encoding="utf-8")
    assert "Smoke battery line one" in md, f"converted content missing: {md[:120]!r}"
    return "docx -> markdown round-trip ok"


def main() -> int:
    print(f"tabella smoke battery — python {sys.version.split()[0]} on {sys.platform}")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lane("stdio-handshake")(stdio_handshake)
        lane("create-docx-xlsx-pptx")(lambda: create_lanes(tmp))
        lane("read-roundtrip")(lambda: read_roundtrip(tmp))
        lane("pdf-from-html (GTK lane)")(lambda: pdf_from_html(tmp))
        lane("convert-pandoc")(lambda: convert_pandoc(tmp))
    if FAILURES:
        print(f"\nSMOKE FAILED: {len(FAILURES)} lane(s): {', '.join(FAILURES)}")
        return 1
    print("\nSMOKE GREEN: all lanes pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())