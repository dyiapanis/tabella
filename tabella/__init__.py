"""tabella — Document lifecycle suite.

Three modules:
  - create  — Generate .docx/.xlsx/.pptx/.pdf/.odt/.ods/.odp from structured JSON
  - convert — Format conversion via pandoc + LaTeX
  - read    — Extract text and metadata from any document via LiteParse
"""

from __future__ import annotations

import os
from pathlib import Path

from .bootstrap import resolve_venv_python


def _read_version() -> str:
    """The package version, from installed metadata or pyproject.toml.

    One source: pyproject.toml. Installed distributions read it back from
    their metadata (so a wheel cannot disagree with itself); a checkout or a
    plugin directory parses the file beside the package. plugin.json carries
    its own literal because a manifest must, and tests/test_version_sync.py
    fails when the two disagree.
    """
    # Source tree first: when this file sits next to a pyproject.toml we are
    # being imported from a checkout, and that file is the version being
    # edited — installed metadata would still say the previous release.
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.startswith("version = "):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    # Installed from a wheel/sdist: the built metadata is authoritative.
    try:
        from importlib.metadata import version

        return version("tabella-docs")
    except Exception:
        return "0+unknown"


__version__ = _read_version()

# ── Configuration ─────────────────────────────────────────────

def get_docs_venv_python() -> str:
    """Path to the Python binary in the docs venv.

    Resolution order:
    1. DOCS_VENV_PYTHON env var (explicit override)
    2. PLUGIN_DATA/venv/bin/python (v1 client-managed data directory)
    3. ~/.venvs/docs/venv/bin/python (fallback)

    Delegates to tabella.bootstrap so the path can only be wrong in one place.
    """
    return resolve_venv_python()


def get_output_dir() -> Path:
    """Default output directory for generated documents.

    Override with DOCS_OUTPUT_DIR env var. Defaults to ~/Documents.
    """
    d = os.environ.get("DOCS_OUTPUT_DIR")
    if d:
        p = Path(d).expanduser()
    else:
        p = Path.home() / "Documents"
    p.mkdir(parents=True, exist_ok=True)
    return p


__all__ = ["get_docs_venv_python", "get_output_dir"]