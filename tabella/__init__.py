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

__version__ = "2.0.3"

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