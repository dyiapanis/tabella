"""Security gates from the catalog review round (#138305) — negative-case tests.

Three gates shipped in commit 21432b3 with manual verification only; these pin
them so a refactor can't silently reopen them:

  1. extra_args allowlist (convert.py) — pandoc --filter/--lua-filter is a
     code-execution vector; only --toc/--number-sections/-V k=v pass.
  2. WeasyPrint local-only URL fetcher (create.py) — model-supplied HTML must
     not reach the network or the host filesystem.
  5. HTTP lane token (scripts/mcp_http_server.py) — TABELLA_TOKEN env takes
     precedence; otherwise a persisted token is generated 0600.
  3. Format-name grammar (convert.py) — pandoc treats a format name ending in
     ".lua" as a path to a Lua reader/writer and executes it; only built-in
     names (alphanumeric/underscore, optional +ext/-ext) pass.
  4. CSS escaping (create.py) — a newline or backslash in header/footer text
     must not break out of a `content: '...'` declaration.

Run: python3 -m pytest tests/test_security_gates.py  (stdlib-only for the
reject paths; the data-URI allow test needs weasyprint and skips if absent).
"""
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tabella.convert import doc_convert, _check_format, _FORMAT_RE  # noqa: E402
from tabella.create import _safe_url_fetcher, _css_escape  # noqa: E402


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
        with pytest.raises(ValueError, match="blocked"):
            fetcher(url)


def test_fetcher_allows_data_uri():
    pytest.importorskip("weasyprint")
    fetcher = _safe_url_fetcher(None)
    uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = fetcher(uri)  # delegates to weasyprint's default fetcher
    assert result is not None


@pytest.mark.parametrize("evil", [
    # EPS/PS reaches Pillow's format dispatcher and, when a ghostscript binary
    # is installed, a separate interpreter (GHSA-r543-q48m-4c9j). The fetcher
    # allowlists image/font MIME types so the class stays closed even if a
    # future weasyprint regresses.
    "data:application/postscript;base64,JSFQUy1BZG9iZQ==",
    "data:application/eps;base64,JSFQUy1BZG9iZQ==",
    "data:image/eps;base64,JSFQUy1BZG9iZQ==",
    "data:text/html;base64,PHNjcmlwdD4=",
    "data:application/octet-stream;base64,AA==",
])
def test_fetcher_rejects_non_image_data_uris(evil):
    fetcher = _safe_url_fetcher(None)
    with pytest.raises(ValueError, match="blocked"):
        fetcher(evil)


@pytest.mark.parametrize("payload", [
    # Pillow dispatches on the bytes, not the declared type: EPS behind an
    # image/png label still reaches EpsImagePlugin. The fetcher sniffs magic.
    "data:image/png;base64,JSFQUy1BZG9iZS0zLjAgRVBTRi0zLjA=",
    "data:image/svg+xml;base64,JSFQUw==",
    "data:image/png,%25!PS-Adobe-3.0",  # %25 = a literal "%"
    # ...and the sniffer must decode exactly the way urllib does, or these
    # three wrappers smuggle the same bytes past it:
    "data:image/png;base64,JSFQ\nUy1BZG9iZS0zLjAgRVBTRi0zLjA=",          # whitespace in the base-64
    "data:image/png;base64,%4A%53%46%51%55%79%31%42%5A%47%39%69",       # percent-encoded base-64
    "data:image/png;base64,xdDTxg==",          # base-64 of the DOS EPS header \xC5\xD0\xD3\xC6
    "data:image/png,%C5%D0%D3%C6",            # same bytes, percent-encoded
])
def test_fetcher_rejects_postscript_payload_hidden_in_an_allowed_type(payload):
    fetcher = _safe_url_fetcher(None)
    with pytest.raises(ValueError, match="PostScript"):
        fetcher(payload)


def test_fetcher_confines_file_urls_to_the_font_tmp_dir(tmp_path):
    """Prefix matching would let <tmp>_evil/ through; containment must be by resolved path."""
    fonts = tmp_path / "t_abc"
    sibling = tmp_path / "t_abc_evil"
    fonts.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("TOP-SECRET")
    (fonts / "ok.woff").write_bytes(b"wOF2")

    fetcher = _safe_url_fetcher(SimpleNamespace(tmp_directory=str(fonts)))
    with pytest.raises(ValueError, match="outside the font temp directory"):
        fetcher("file://" + str(sibling / "secret.txt"))


# ── Gate 3: format-name grammar (ported from the retired test_security.py) ──

@pytest.mark.parametrize("evil", [
    "evil.lua", "/tmp/x.lua", "a b", "'evil'", "markdown+lua.lua",
])
def test_check_format_rejects_lua_readers(evil):
    with pytest.raises(ValueError, match="must be a built-in pandoc format"):
        _check_format(evil, "from_format")


@pytest.mark.parametrize("good", [
    "pdf", "markdown", "docx", "markdown+tex_math_dollars",
    "markdown-header_attributes",
])
def test_check_format_accepts_builtin_names(good):
    assert _FORMAT_RE.match(good), good
    _check_format(good, "to_format")  # must not raise


# ── Gate 4: CSS escaping (ported from the retired test_security.py) ─────────

def test_css_escape_cannot_smuggle_a_newline():
    malicious = "x'\n@font-face { src: url(http://169.254.169.254/x) }"
    escaped = _css_escape(malicious)
    assert "\n" not in escaped, escaped
    assert "'\\n@font-face" not in escaped, escaped
    assert "\\A " in escaped, escaped


# ── Gate 5: HTTP lane token ───────────────────────────────────────────

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