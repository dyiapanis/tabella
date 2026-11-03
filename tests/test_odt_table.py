"""ODT tables must carry their cell values, not just the grid.

2.0.2 built every cell as `P(text="")`: a table with headers and rows came back
as an empty grid behind `{"success": true}` — silent data loss.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabella.create import create_document  # noqa: E402


def _cells(path):
    from odf.opendocument import load
    from odf.table import TableCell
    from odf import teletype

    return [teletype.extractText(c) for c in load(path).getElementsByType(TableCell)]


def test_odt_table_keeps_headers_and_rows():
    pytest.importorskip("odf.table")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.odt")
        r = create_document(
            format="odt",
            output_path=p,
            content={"sections": [{
                "type": "table",
                "headers": ["name", "qty"],
                "rows": [["widget", 3], ["gadget", 7]],
            }]},
        )
        assert r["success"], r
        assert _cells(p) == ["name", "qty", "widget", "3", "gadget", "7"]


def test_odt_table_without_headers_still_carries_rows():
    pytest.importorskip("odf.table")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t2.odt")
        r = create_document(
            format="odt",
            output_path=p,
            content={"sections": [{"type": "table", "rows": [["only", "row"]]}]},
        )
        assert r["success"], r
        assert _cells(p) == ["only", "row"]


def test_odt_table_width_follows_the_widest_row():
    """Ragged input must not drop cells: an earlier short row can't set the width."""
    pytest.importorskip("odf.table")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ragged.odt")
        r = create_document(
            format="odt",
            output_path=p,
            content={"sections": [{"type": "table", "rows": [["a", "b"], ["c", "d", "kept"]]}]},
        )
        assert r["success"], r
        assert _cells(p) == ["a", "b", "", "c", "d", "kept"]


def test_odt_table_width_follows_rows_when_headers_are_narrower():
    pytest.importorskip("odf.table")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ragged2.odt")
        r = create_document(
            format="odt",
            output_path=p,
            content={"sections": [{
                "type": "table", "headers": ["h1"], "rows": [["x", "y", "kept"]],
            }]},
        )
        assert r["success"], r
        assert _cells(p) == ["h1", "", "", "x", "y", "kept"]


def test_odt_table_none_cell_is_blank_not_the_string_none():
    pytest.importorskip("odf.table")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "none.odt")
        r = create_document(
            format="odt",
            output_path=p,
            content={"sections": [{"type": "table", "rows": [[None, "v"]]}]},
        )
        assert r["success"], r
        assert _cells(p) == ["", "v"]
