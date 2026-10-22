"""Security gates from the catalog review round (#138305) — negative-case tests.

Three gates shipped in commit 21432b3 with manual verification only; these pin
them so a refactor can't silently reopen them:

  1. extra_args allowlist (convert.py) — pandoc --filter/--lua-filter is a
     code-execution vector; only --toc/--number-sections/-V k=v pass.
  2. WeasyPrint local-only URL fetcher (create.py) — model-supplied HTML must
     not reach the network or the host filesystem.
  3. HTTP lane token (scripts/mcp_http_server.py) — TABELLA_TOKEN env takes
     precedence; otherwise a persisted token is generated 0600.

Run: python3 -m pytest tests/test_security_gates.py  (stdlib-only for the
reject paths; the data-URI allow test needs weasyprint and skips if absent).
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tabella.convert import doc_convert  # noqa: E402
from tabella.create import _safe_url_fetcher  # noqa: E402


def _md(tmp_path):
    p = tmp_path / "src.md"
    p.write_text("# Title\n\nbody text\n", encoding="utf-8")
    return str(p)


# ── Gate 1: pandoc extra_args allowlist ───────────────────────────────

@pytest.mark.parametrize("evil", [
    "--lua-filter=evil.lua", "--filter", "./evil.sh", "--template=/etc/passwd",
])
def test_extra_args_rejects_code_exec_vectors(tmp_path, evil):
    with pytest.raises(ValueError, match="unsupported pandoc argument"):
        doc_convert(_md(tmp_path), "html", extra_args=[evil])


def test_extra_args_accepts_the_allowlist(tmp_path):
    out = doc_convert(_md(tmp_path), "html", extra_args=["--toc", "-Vmargin=1in"])
    assert out.get("success") is True, out


# ── Gate 2: WeasyPrint local-only fetcher ─────────────────────────────

def test_fetcher_blocks_host_files_and_network():
    fetcher = _safe_url_fetcher(None)  # no font_config → no tmp carve-out at all
    for url in ("file:///etc/passwd", "file://c/evil.svg",
                "http://evil.example/x.png", "https://evil.example/x.css",
                "//evil.example/x.png"):
        with pytest.raises(ValueError, match="blocked external URL"):
            fetcher(url)


def test_fetcher_allows_data_uri():
    pytest.importorskip("weasyprint")
    fetcher = _safe_url_fetcher(None)
    uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = fetcher(uri)  # delegates to weasyprint's default fetcher
    assert result is not None


# ── Gate 3: HTTP lane token ───────────────────────────────────────────

def test_token_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("TABELLA_TOKEN", "env-token-for-test")
    sys.modules.pop("mcp_http_server", None)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        mod = importlib.import_module("mcp_http_server")
        importlib.reload(mod)  # bind TOKEN under this env
        assert mod.TOKEN == "env-token-for-test"
    finally:
        sys.modules.pop("mcp_http_server", None)
        sys.path.remove(str(Path(__file__).resolve().parent.parent / "scripts"))


def test_token_generates_persisted_token_0600(monkeypatch, tmp_path):
    monkeypatch.delenv("TABELLA_TOKEN", raising=False)
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        sys.modules.pop("mcp_http_server", None)
        mod = importlib.import_module("mcp_http_server")
        assert mod.TOKEN  # generated at import in the tmp data dir
        tok_file = tmp_path / "http.token"
        assert tok_file.exists()
        assert tok_file.read_text().strip() == mod.TOKEN
        if os.name == "posix":  # windows has no posix mode bits
            assert tok_file.stat().st_mode & 0o777 == 0o600
        # a second import (no reload of a live module) must reuse the file
        sys.modules.pop("mcp_http_server", None)
        mod2 = importlib.import_module("mcp_http_server")
        assert mod2.TOKEN == mod.TOKEN
    finally:
        sys.modules.pop("mcp_http_server", None)
        sys.path.remove(str(Path(__file__).resolve().parent.parent / "scripts"))