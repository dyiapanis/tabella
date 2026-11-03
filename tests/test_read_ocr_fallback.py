"""doc_read on an image-only PDF must reach the OCR lane, not raise.

anydoc signals a missing text layer by *raising* NeedsOcrError (MRO:
NeedsOcrError -> ConvertError -> Exception, so not a RuntimeError), where the
fallback was gated on empty text and caught only RuntimeError/ImportError.
Net effect: the fallback was unreachable for exactly the input it exists for.

Runs the real pipeline — PIL makes the page, Tesseract reads it — because a
mocked empty return is what let this ship.
"""

from pathlib import Path

import pytest

pytest.importorskip("PIL")
pytest.importorskip("anydoc")
pytest.importorskip("liteparse")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402


def _page(tmp_path: Path):
    img = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64
        )
    except OSError:
        font = ImageFont.load_default(size=64)
    draw.text((60, 120), "SCANNED HELLO 42", fill="black", font=font)
    return img


def test_image_only_pdf_falls_back_to_ocr(tmp_path):
    png, pdf = tmp_path / "scan.png", tmp_path / "scan.pdf"
    img = _page(tmp_path)
    img.save(png)
    img.save(pdf, "PDF", resolution=150.0)

    from tabella.read import read

    from_png = " ".join(read(str(png)).split())
    from_pdf = " ".join(read(str(pdf)).split())

    assert "HELLO" in from_png.upper(), f"OCR lane itself is broken: {from_png!r}"
    assert from_pdf, "image-only PDF returned no text"
    assert from_pdf == from_png, f"PDF and PNG disagree: {from_pdf!r} vs {from_png!r}"
