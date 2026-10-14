"""Shared helpers for the documents plugin.

Consolidates output-directory resolution that was previously duplicated in
doc_convert and doc_create.
"""

import os
from pathlib import Path


def _get_output_dir() -> Path:
    """Resolve output directory for documents.

    Uses DOCS_OUTPUT_DIR env var if set, otherwise defaults to ~/Documents.
    Fleet pCloud routing is handled by the document-routing skill, not here.
    """
    d = os.environ.get("DOCS_OUTPUT_DIR")
    if d:
        p = Path(d).expanduser()
    else:
        p = Path.home() / "Documents"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_in_output_dir(path: Path) -> bool:
    """Check if path is under the configured output directory."""
    try:
        resolved = path.expanduser().resolve()
        user_dir = _get_output_dir()
        return resolved != user_dir and user_dir in resolved.parents
    except Exception:
        return False


def _resolve_output_dir(category: str = None) -> Path:
    """Return output directory with optional category subfolder."""
    base = _get_output_dir()
    if category:
        out = base / category
        out.mkdir(parents=True, exist_ok=True)
        return out
    return base
