"""One version, or a released package that lies about itself.

pyproject.toml is the source; tabella.__version__ reads it back (via installed
metadata when available) and both transports report that value. plugin.json
must carry the same literal because a manifest cannot compute it.
"""

import json
import re
from pathlib import Path

import tabella

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no version line"
    return match.group(1)


def test_version_is_read_from_pyproject():
    assert tabella.__version__ == _pyproject_version()


def test_plugin_manifest_agrees_with_the_package():
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == tabella.__version__


def test_documented_imports_resolve():
    """README/SPECS show `from tabella.x import y` — those must exist."""
    from tabella.convert import doc_convert  # noqa: F401
    from tabella.create import create_document  # noqa: F401
    from tabella.read import read, read_meta  # noqa: F401


def test_both_transports_import_the_same_surface():
    """The stdio and HTTP servers used to carry two copies of the tool table."""
    for path in (ROOT / "mcp_server.py", ROOT / "scripts" / "mcp_http_server.py"):
        source = path.read_text(encoding="utf-8")
        assert "from tabella.toolspec import" in source, f"{path} does not use the shared surface"
        assert "TOOLS = [" not in source, f"{path} still defines its own tool table"
