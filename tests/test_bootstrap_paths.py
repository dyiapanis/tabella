"""The bootstrap must hand back the interpreter scripts/setup.sh actually builds.

Shipped 2.0.2 returned `~/.venvs/docs/bin/python` while setup.sh created
`~/.venvs/docs/venv/bin/python`: the bootstrap reported success, nothing
re-exec'd, and every tool call failed to import on a clean host. These tests
pin the *contract* (the returned interpreter is the one the bootstrap command
creates) rather than a literal path, so the two can't drift apart again.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabella import bootstrap  # noqa: E402


@pytest.fixture
def cold(monkeypatch, tmp_path):
    """No PLUGIN_DATA, no override, empty HOME; subprocess faked as a no-op."""
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    monkeypatch.delenv("DOCS_VENV_PYTHON", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    return tmp_path, calls


@pytest.mark.skipif(os.name == "nt", reason="POSIX bootstrap runs scripts/setup.sh")
def test_returned_python_is_the_one_setup_sh_builds(cold):
    home, calls = cold
    got = bootstrap.ensure_venv()
    assert calls, "bootstrap never invoked setup.sh"
    cmd = calls[-1]
    assert cmd[0] == "bash", cmd
    data_dir = Path(cmd[2])
    assert data_dir == home / ".venvs" / "docs", data_dir
    assert Path(got) == data_dir / "venv" / "bin" / "python", got


@pytest.mark.skipif(os.name == "nt", reason="POSIX path layout")
def test_fallback_paths(cold):
    home, _ = cold
    assert bootstrap.docs_root() == home / ".venvs" / "docs"
    assert bootstrap.venv_python_path() == str(
        home / ".venvs" / "docs" / "venv" / "bin" / "python"
    )


def test_plugin_data_root_owns_the_venv(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("DOCS_VENV_PYTHON", raising=False)
    assert bootstrap.docs_root() == tmp_path / "data"
    leaf = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    assert Path(bootstrap.venv_python_path()) == tmp_path / "data" / "venv" / Path(*leaf)


@pytest.mark.skipif(os.name == "nt", reason="POSIX path layout")
def test_existing_venv_short_circuits(monkeypatch, tmp_path):
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    monkeypatch.delenv("DOCS_VENV_PYTHON", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    py = tmp_path / ".venvs" / "docs" / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    monkeypatch.setattr(
        bootstrap.subprocess, "run",
        lambda *a, **k: pytest.fail("bootstrap ran despite an existing venv"),
    )
    assert bootstrap.ensure_venv() == str(py)


def test_docs_venv_override_wins(monkeypatch, tmp_path):
    py = tmp_path / "custom" / "python"
    py.parent.mkdir()
    py.write_text("")
    monkeypatch.setenv("DOCS_VENV_PYTHON", str(py))
    assert bootstrap.ensure_venv() == str(py)
