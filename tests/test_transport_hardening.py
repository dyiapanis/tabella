"""Transports must fail in the protocol, not by dying or by lying.

Three shipped behaviours this covers:
  - a malformed Content-Length made the stdio server exit mid-session instead
    of answering -32700;
  - an unknown tool came back as a *successful* result carrying
    {"success": false} — the same shape that hid the ODT bug;
  - the HTTP lane compared the bearer with == and read Content-Length without
    a ceiling, and created its token file at import time.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import tabella
from tabella.toolspec import UnknownToolError, handle_tool

ROOT = Path(__file__).resolve().parent.parent
STDIO = ROOT / "mcp_server.py"


def _run_stdio(payload: str, timeout=60):
    env = dict(os.environ, TABELL_REEXEC="1")
    proc = subprocess.run(
        [sys.executable, str(STDIO)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_malformed_content_length_answers_and_keeps_serving():
    init = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
    out = _run_stdio("Content-Length: not-a-number\n" + init + "\n")
    assert len(out) == 2, out
    assert out[0]["error"]["code"] == -32700
    assert "Content-Length" in out[0]["error"]["message"]
    assert out[1]["result"]["serverInfo"]["name"] == "tabella", "server stopped after the bad frame"


def test_unknown_tool_is_a_protocol_error_not_a_result():
    with pytest.raises(UnknownToolError):
        handle_tool("doc_nope", {})

    call = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "doc_nope", "arguments": {}}})
    out = _run_stdio(call + "\n")
    assert out[0]["error"]["code"] == -32602, out[0]
    assert "result" not in out[0]


def test_http_rejects_an_oversized_body_before_reading_it(tmp_path):
    """Content-Length is capped before rfile.read(n), so the server cannot be
    made to allocate on request."""
    import socket
    import time

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    env = dict(os.environ, TABELLA_TOKEN="test-token", PLUGIN_DATA=str(tmp_path / "pd"),
               TABELL_REEXEC="1")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "mcp_http_server.py"), "--addr", f"127.0.0.1:{port}"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.1)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=b"",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/json",
                     "Content-Length": "5000000"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("oversized body was accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code == 413, exc.code
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_http_import_does_not_create_a_token_file(tmp_path):
    data = tmp_path / "plugin-data"
    env = dict(os.environ, PLUGIN_DATA=str(data), TABELLA_TOKEN="")
    env.pop("TABELLA_TOKEN")
    code = (
        "import sys; sys.path.insert(0, %r); "
        "import importlib.util as u; "
        "spec = u.spec_from_file_location('h', %r); "
        "m = u.module_from_spec(spec); spec.loader.exec_module(m); "
        "print('imported')" % (str(ROOT), str(ROOT / "scripts" / "mcp_http_server.py"))
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60)
    assert "imported" in proc.stdout, proc.stderr[-400:]
    assert not (data / "http.token").exists(), "importing the server minted a token"
