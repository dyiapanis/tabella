"""documents.read — read documents via anydoc (primary) + LiteParse (OCR fallback).

Merged from the doc_read plugin. Dependencies (firecrawl-anydoc, liteparse) are
now installed directly in the the bootstrapped per-plugin venv (PYTHON_BOOTSTRAP: scripts/setup.sh; stdio/HTTP servers exec into it on first serve)

Architecture:
  - Office formats (DOCX, DOC, XLSX, XLSB, PPTX, PPT, ODT, ODS, ODP, RTF,
    EPUB, CSV) and text-based PDFs → anydoc (Rust, in-process, ~4ms,
    GitHub-Flavored Markdown output).
  - Scanned PDFs and images (JPG, PNG, TIFF) → LiteParse (Tesseract OCR).
    Used when anydoc returns empty for a PDF, or for image files directly.
  - Plain text (.txt, .md, .json, .py, .yaml, etc.) → direct file read.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

# ── Format classification ────────────────────────────────────────────────────

TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".json", ".html", ".htm",
    ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".rst", ".fountain", ".log", ".py", ".js", ".ts", ".css",
}

# Formats anydoc handles (office + text PDF).
# Source: anydoc README — supported formats table.
ANYDOC_SUFFIXES = {
    ".doc", ".docx", ".docm",
    ".ppt", ".pps", ".pot", ".pptx", ".pptm", ".ppsx", ".ppsm",
    ".xls", ".xlsx", ".xlsm", ".xlsb",
    ".odt", ".ods", ".odp",
    ".rtf",
    ".epub",
    ".pdf",
    ".csv",
}

# Image formats that need OCR (LiteParse + Tesseract).
IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp", ".gif",
}

# ── anydoc (primary engine) ──────────────────────────────────────────────────

def _run_anydoc(path: str, timeout: int = 60) -> str:
    """Convert a document to Markdown using anydoc.

    Returns the Markdown text, or empty string if the document has no
    extractable text (e.g. scanned PDF without OCR).
    """
    import anydoc
    md = anydoc.to_markdown(path)
    return md or ""


# ── LiteParse (OCR fallback) ─────────────────────────────────────────────────

def _run_liteparse(path: str, extract_images: bool = True, timeout: int = 120) -> Dict[str, Any]:
    """Parse a document using LiteParse with OCR enabled.

    Used for scanned PDFs and images where anydoc returns empty.
    """
    from liteparse import LiteParse, ParseResult

    parser = LiteParse(ocr_enabled=extract_images, output_format="text")
    result = parser.parse(path)
    text = ""
    if isinstance(result, ParseResult):
        text = getattr(result, "text", None) or getattr(result, "markdown", None) or ""
    elif isinstance(result, str):
        text = result
    else:
        text = str(result)
    return {
        "text": text,
        "metadata": getattr(result, "metadata", {}) if hasattr(result, "metadata") else {},
    }


# ── Plain text fast path ─────────────────────────────────────────────────────

def _read_text(path: str, max_chars: Optional[int] = None) -> str:
    encodings = ["utf-8", "utf-8-sig", "latin-1"]
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="replace") as f:
                text = f.read()
                if max_chars:
                    text = text[:max_chars]
                return text
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Could not read text file: {last_err}")


# ── Main dispatch ────────────────────────────────────────────────────────────

def read(path: str, max_chars: Optional[int] = None, extract_images: bool = True, max_pages: Optional[int] = None) -> str:
    """Extract text from a document.

    Dispatch:
      1. Plain text → direct file read (fast path)
      2. Office formats + text PDFs → anydoc (Markdown output)
      3. Images → LiteParse (OCR)
      4. PDFs that anydoc returns empty → LiteParse (OCR fallback for scanned PDFs)
    """
    suffix = Path(path).suffix.lower()

    # 1. Plain text fast path
    if suffix in TEXT_SUFFIXES:
        return _read_text(path, max_chars)

    # 2. Images → LiteParse OCR directly
    if suffix in IMAGE_SUFFIXES:
        data = _run_liteparse(path, extract_images=extract_images)
        text = data.get("text") or ""
        if max_chars:
            text = text[:max_chars]
        return text

    # 3. Office formats + PDFs → anydoc first
    if suffix in ANYDOC_SUFFIXES or suffix not in TEXT_SUFFIXES:
        text = ""
        anydoc_error = None
        try:
            text = _run_anydoc(path)
        except (RuntimeError, ImportError) as e:
            anydoc_error = str(e)

        # 4. If anydoc returned empty text (scanned PDF) or failed, try LiteParse OCR
        if not text.strip():
            try:
                data = _run_liteparse(path, extract_images=extract_images)
                text = data.get("text") or ""
            except (RuntimeError, ImportError) as liteparse_err:
                if anydoc_error:
                    raise RuntimeError(f"anydoc failed: {anydoc_error}; liteparse fallback also failed: {liteparse_err}")
                raise RuntimeError(f"both anydoc and liteparse returned no text. liteparse: {liteparse_err}")

        if max_chars:
            text = text[:max_chars]
        return text

    # Fallback: unknown format, try plain text read
    return _read_text(path, max_chars)


def read_meta(path: str) -> Dict[str, Any]:
    """Extract metadata from a document."""
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return {"path": path, "format": "text"}

    # LiteParse has the richest metadata extraction (office + PDF + images).
    try:
        data = _run_liteparse(path, extract_images=False)
        meta = data.get("metadata") or {}
        meta["path"] = path
        return meta
    except Exception:
        # LiteParse unavailable (e.g. its LibreOffice fallback missing for office
        # formats). Fall back to filesystem-truth metadata rather than failing:
        # callers get valid basics instead of a tool error.
        import os

        st = os.stat(path)
        return {
            "path": path,
            "format": suffix.lstrip("."),
            "size_bytes": st.st_size,
            "mtime": st.st_mtime,
        }


# ── Hermes plugin registration ──

def register(registry):
    if registry is None:
        return

    def doc_read(path: str, max_chars: int = 1_000_000, extract_images: bool = True):
        try:
            text = read(path, max_chars=max_chars, extract_images=extract_images)
            return {
                "success": True,
                "path": path,
                "text": text,
                "length": len(text),
                "message": f"Read {len(text)} chars from {path}",
            }
        except Exception as e:
            return {"success": False, "path": path, "error": f"{type(e).__name__}: {e}"}

    def doc_read_meta(path: str):
        try:
            meta = read_meta(path)
            return {"success": True, "path": path, "metadata": meta}
        except Exception as e:
            return {"success": False, "path": path, "error": f"{type(e).__name__}: {e}"}

    registry.register_tool(
        name="doc_read",
        toolset="doc",
        schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the document.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return.",
                    "default": 1_000_000,
                },
                "extract_images": {
                    "type": "boolean",
                    "description": "Extract text from images via OCR (LiteParse + Tesseract).",
                    "default": True,
                },
            },
            "required": ["path"],
        },
        handler=lambda args, **kw: json.dumps(doc_read(
            args["path"],
            max_chars=args.get("max_chars", 1_000_000),
            extract_images=args.get("extract_images", True),
        )),
        description="Read and extract text from documents. Uses anydoc for office formats (DOCX, XLSX, PPTX, ODT, RTF, EPUB, PDF → Markdown) and LiteParse for OCR (scanned PDFs, images). Plain text files read directly.",
    )
    registry.register_tool(
        name="doc_read_meta",
        toolset="doc",
        schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the document.",
                },
            },
            "required": ["path"],
        },
        handler=lambda args, **kw: json.dumps(doc_read_meta(args["path"])),
        description="Read document metadata (PDF info, image EXIF, etc.) via LiteParse.",
    )
