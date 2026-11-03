"""doc_convert must read PDFs, not hand them to a pandoc that cannot.

pandoc converts *to* PDF only. A PDF input used to fail with "Unknown input
format pdf"; the route now extracts text through the read lane (text layer, or
OCR for a scan) and converts the extracted markdown, so .pdf joins the input
column honestly.
"""

import shutil

import pytest

pytest.importorskip("PIL")
pytest.importorskip("docx")

from pathlib import Path  # noqa: E402

from tabella.convert import doc_convert  # noqa: E402

needs_pandoc = pytest.mark.skipif(
    shutil.which("pandoc") is None, reason="pandoc not installed"
)


def _assert_docx_text(path: Path, needle: str) -> None:
    from docx import Document

    text = "\n".join(p.text for p in Document(str(path)).paragraphs)
    assert needle.lower() in text.lower(), f"{needle!r} missing from {path}: {text[:200]!r}"


@needs_pandoc
def test_image_only_pdf_converts_to_docx(tmp_path):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64
        )
    except OSError:
        font = ImageFont.load_default(size=64)
    draw.text((60, 120), "SCANNED HELLO 42", fill="black", font=font)
    pdf = tmp_path / "scan.pdf"
    img.save(pdf, "PDF", resolution=150.0)

    out = doc_convert(str(pdf), to_format="docx", output_path=str(tmp_path / "scan.docx"))

    assert out["success"], out
    assert out["from_format"] == "pdf"
    assert out["extracted_text"] is True
    _assert_docx_text(Path(out["output_path"]), "SCANNED HELLO 42")


@needs_pandoc
def test_plain_text_is_readable_as_markdown(tmp_path):
    # pandoc has no "plain" *reader*; .txt must not be handed to it as one.
    src = tmp_path / "notes.txt"
    src.write_text("# Heading\n\nSome prose.", encoding="utf-8")

    out = doc_convert(str(src), to_format="docx", output_path=str(tmp_path / "notes.docx"))

    assert out["success"], out
    assert out["from_format"] == "markdown"
    _assert_docx_text(Path(out["output_path"]), "Some prose")


def test_hostile_extra_arg_is_rejected_before_the_dependency_check(monkeypatch, tmp_path):
    """A bad flag must raise as invalid, not come back as "pandoc is missing".

    The allowlist used to run after _check_deps(), so on a pandoc-less host an
    untrusted --lua-filter looked like a harmless dependency error.
    """
    src = tmp_path / "x.md"
    src.write_text("# hi", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(ValueError, match="unsupported pandoc argument"):
        doc_convert(str(src), to_format="docx", extra_args=["--lua-filter=evil.lua"])
