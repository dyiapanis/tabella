"""Small correctness fixes: text decoding, one output-dir rule, Typst mapping.

Each of these was a real defect, not tidying:
  - _read_text looped over encodings with errors="replace", which never raises —
    so the loop ran once and a binary file came back as U+FFFD instead of an
    error;
  - get_output_dir and utils._get_output_dir were two copies of one rule;
  - .typ fell through as the literal "typ", which passes the format-name check
    and then fails inside pandoc.
"""

import os
import shutil
from pathlib import Path

import pytest

import tabella
from tabella import utils
from tabella.convert import _infer_format, doc_convert
from tabella.read import _read_text


def test_binary_file_is_refused_not_mangled(tmp_path):
    blob = tmp_path / "image.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    with pytest.raises(RuntimeError, match="binary"):
        _read_text(str(blob))


def test_windows_1252_text_still_reads(tmp_path):
    f = tmp_path / "legacy.txt"
    f.write_bytes("caf\xe9 na\xefve".encode("cp1252"))
    assert _read_text(str(f)).startswith("caf")


def test_utf8_bom_is_stripped(tmp_path):
    f = tmp_path / "bom.txt"
    f.write_bytes(b"\xef\xbb\xbfhello")
    assert _read_text(str(f)) == "hello"


def test_output_dir_has_one_rule(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCS_OUTPUT_DIR", str(tmp_path / "docs"))
    assert tabella.get_output_dir() == utils._get_output_dir()
    assert (tmp_path / "docs").is_dir(), "get_output_dir must create the directory"


def test_typ_maps_to_typst():
    assert _infer_format("typ") == "typst"


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
def test_typst_converts(tmp_path):
    src = tmp_path / "note.typ"
    src.write_text("= Heading\n\nSome prose.\n", encoding="utf-8")
    out = doc_convert(str(src), to_format="docx", output_path=str(tmp_path / "note.docx"))
    assert out["success"], out
    assert out["from_format"] == "typst"
