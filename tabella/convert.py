"""documents.convert — Document format conversion via pandoc + LaTeX.

Supports: markdown → PDF/DOCX/HTML/ODT/EPUB and any pandoc-supported format pair.
Output directory is configurable via DOCS_OUTPUT_DIR (defaults to ~/Documents).
Merged from the doc_convert plugin.
"""

import re
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .utils import _get_output_dir, _is_in_output_dir, _resolve_output_dir

logger = logging.getLogger(__name__)


def _check_deps(needs_tex: bool = False) -> Optional[str]:
    """Return error string if pandoc — or, for pdf targets, LaTeX — is missing."""
    if not shutil.which("pandoc"):
        return "pandoc is not installed. Install it (e.g. `sudo apt install pandoc`)."
    if needs_tex and not shutil.which("pdflatex") and not shutil.which("xelatex"):
        return "No LaTeX engine found. Install texlive (e.g. `sudo apt install texlive-xetex`)."
    return None


def _pdf_engine() -> str:
    """Return preferred LaTeX engine."""
    if shutil.which("xelatex"):
        return "xelatex"
    return "pdflatex"


# ── tool ──
def doc_convert(
    input_path: str,
    to_format: str,
    from_format: str = None,
    output_path: str = None,
    extra_args: list = None,
    category: str = None,
) -> dict:
    """Convert a document from one format to another using pandoc.

    Args:
        input_path: Absolute path to the source document.
        to_format: Target format (e.g. "pdf", "docx", "html", "odt", "epub").
        from_format: Optional source format hint (e.g. "markdown", "html").
                     When omitted, pandoc infers from file extension.
        output_path: Optional absolute path for the output file.
                     When omitted, writes to the user's documents directory.
        extra_args:  Optional extra pandoc CLI flags (e.g. ["--toc", "-V", "geometry:margin=1in"]).
        category:    Optional subfolder under ~/documents/ (e.g. "reports", "invoices").

    Returns:
        {"success": bool, "output_path": str, "from_format": str, "to_format": str,
         "pdf_engine": str | None, "message": str}
    """
    src = Path(input_path).expanduser().resolve()
    if not src.exists():
        return {"success": False, "error": f"Source file not found: {src}"}

    # Determine formats
    src_fmt = from_format or _infer_format(src.suffix.lstrip(".").lower())
    tgt_fmt = to_format.lower()
    _check_format(src_fmt, "from_format")
    _check_format(tgt_fmt, "to_format")

    # pandoc is always required; a TeX engine only for pdf output
    dep_err = _check_deps(tgt_fmt == "pdf")
    if dep_err:
        return {"success": False, "error": dep_err}

    # Determine output path
    if output_path:
        out_file = Path(output_path).expanduser().resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = _resolve_output_dir(category)
        stem = src.stem
        out_file = out_dir / f"{stem}.{tgt_fmt}"

    # Warn if output is outside the configured output directory
    if not _is_in_output_dir(out_file):
        logger.warning(
            "doc_convert: output file %s is outside the configured output directory. "
            "Files saved here may not be synced.",
            out_file,
        )

    # Build pandoc command
    cmd = ["pandoc", str(src), "-o", str(out_file), "-f", src_fmt, "-t", tgt_fmt]
    if tgt_fmt == "pdf":
        engine = _pdf_engine()
        cmd.extend(["--pdf-engine", engine])
    if extra_args:
        # strict allowlist — pandoc can execute arbitrary code via --filter/
        # --lua-filter/--pdf-engine, so only formatting flags are honored
        # (catalog review #2026-10-16, finding 1).
        allowed = {"--toc", "--number-sections"}
        for a in extra_args:
            if a in allowed:
                cmd.append(a)
            elif re.match(r"^-V\S*=", a):
                cmd.append(a)
            else:
                raise ValueError(
                    f"unsupported pandoc argument {a!r}: extra_args allows only "
                    "--toc, --number-sections and -V <key>=<value>"
                )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"pandoc failed (exit {result.returncode}): {result.stderr.strip()}",
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "pandoc timed out after 5 minutes."}
    except Exception as e:
        return {"success": False, "error": f"pandoc error: {e}"}

    if not out_file.exists():
        return {"success": False, "error": f"Output file was not created: {out_file}"}

    return {
        "success": True,
        "output_path": str(out_file),
        "from_format": src_fmt,
        "to_format": tgt_fmt,
        "pdf_engine": _pdf_engine() if tgt_fmt == "pdf" else None,
        "message": f"MEDIA:{out_file}\n\nConverted {src.name} → {tgt_fmt}: {out_file}",
    }


def _infer_format(ext: str) -> str:
    """Map common extensions to pandoc format names."""
    mapping = {
        "md": "markdown",
        "markdown": "markdown",
        "txt": "plain",
        "html": "html",
        "htm": "html",
        "docx": "docx",
        "odt": "odt",
        "pdf": "pdf",
        "tex": "latex",
        "rst": "rst",
        "epub": "epub",
    }
    return mapping.get(ext, ext)


# Pandoc treats a format name ending in ".lua" as a path to a custom Lua
# reader/writer and executes it with the full Lua stdlib (os.execute) —
# same code-exec class as --lua-filter via a different argument. Restrict
# format names to pandoc's built-in name grammar (catalog finding 2026-10-17).
_FORMAT_RE = re.compile(r"^[a-z0-9_]+([+-][a-z0-9_]+)*$")


def _check_format(name: str, which: str) -> None:
    """Reject anything that isn't a built-in pandoc format name."""
    if not _FORMAT_RE.match(name):
        raise ValueError(
            f"unsupported {which} {name!r}: must be a built-in pandoc format "
            "(alphanumeric/underscore, optional +ext/-ext modifiers)"
        )


def _handle_doc_convert(args: dict, **kwargs) -> str:
    """Handler wrapper for doc_convert tool."""
    result = doc_convert(**args)
    if isinstance(result, dict):
        return json.dumps(result)
    return result


# ── Hermes plugin registration ──
def register(registry):
    registry.register_tool(
        name="doc_convert",
        toolset="doc-convert",
        schema={
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Absolute path to the source document.",
                },
                "to_format": {
                    "type": "string",
                    "description": "Target format: pdf, docx, html, odt, epub, etc.",
                },
                "from_format": {
                    "type": "string",
                    "description": "Optional source format hint (e.g. markdown, html). Pandoc infers from extension if omitted.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional absolute output path. Defaults to user's documents directory.",
                },
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional extra pandoc CLI flags.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional subfolder under documents/ (e.g. 'reports').",
                },
            },
            "required": ["input_path", "to_format"],
        },
        handler=_handle_doc_convert,
        description="Convert documents between formats (PDF, DOCX, HTML, ODT, EPUB, etc.) using pandoc + LaTeX.",
    )
