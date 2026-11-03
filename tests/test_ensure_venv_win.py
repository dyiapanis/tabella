"""Seam tests for tabella.bootstrap.ensure_venv platform handling.

Shared module serving BOTH servers (mcp_server.py + scripts/mcp_http_server.py).
Proves, without a Windows box:
  1. DOCS_VENV_PYTHON override short-circuits.
  2. POSIX fast path returns the venv interpreter; the bootstrap runs
     scripts/setup.sh with the docs root as its argument.
  3. os.name=="nt": Scripts\\python.exe layout, venv + pip commands mirroring
     setup.sh (--require-hashes -r requirements-pinned.txt), success and
     failure paths both behave.

The nt seam swaps the module's ``os`` for a namespace (NOT global os.name —
that flips the shared pathlib factory to WindowsPath, uninstantiable on
Linux). Path separators in expectations are built with the same Path
arithmetic, so they match this platform; the real backslash layout is proven
by CI on windows-latest.
"""
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabella import bootstrap  # noqa: E402


class _Result:
    def __init__(self, returncode=0, stderr=""):
        self.returncode, self.stderr, self.stdout = returncode, stderr, ""


def test_override_short_circuits(monkeypatch, tmp_path):
    fake = tmp_path / "wpython.exe"
    fake.write_text("")
    monkeypatch.setenv("DOCS_VENV_PYTHON", str(fake))
    assert bootstrap.ensure_venv() == str(fake)


@pytest.mark.skipif(os.name == "nt", reason="POSIX path layout")
def test_posix_fast_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("DOCS_VENV_PYTHON", raising=False)
    venv = tmp_path / "data" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    (venv / ".tabella-deps-ok").write_text("")  # completed install
    monkeypatch.setattr(
        bootstrap.subprocess, "run",
        lambda *a, **k: pytest.fail("bootstrap ran on a ready venv"),
    )
    assert bootstrap.ensure_venv() == str(venv / "bin" / "python")


@pytest.mark.skipif(os.name == "nt", reason="POSIX bootstrap path")
def test_posix_bootstrap_runs_setup_sh(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("DOCS_VENV_PYTHON", raising=False)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _Result(0)

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    out = bootstrap.ensure_venv()
    assert calls and calls[0][0] == "bash", calls
    assert calls[0][1].endswith("scripts/setup.sh"), calls
    assert calls[0][2] == str(tmp_path / "data"), calls
    assert out == str(tmp_path / "data" / "venv" / "bin" / "python")


def test_windows_layout_and_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("DOCS_VENV_PYTHON", raising=False)
    venv_dir = tmp_path / "data" / "venv"
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[1:3] == ["-m", "venv"]:  # `python -m venv` leaves an interpreter
            (venv_dir / "Scripts").mkdir(parents=True, exist_ok=True)
            (venv_dir / "Scripts" / "python.exe").write_text("")
        return _Result(0)

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="nt", environ=os.environ))
    out = bootstrap.ensure_venv()

    want_python = str(venv_dir / "Scripts" / "python.exe")
    assert out == want_python, out
    assert calls[0] == [sys.executable, "-m", "venv", str(venv_dir)], calls
    assert "--upgrade" in calls[1] and "pip" in calls[1], calls  # setup.sh parity
    assert calls[-1][:3] == [want_python, "-m", "pip"], calls
    assert "--require-hashes" in calls[-1]
    assert calls[-1][-1].endswith("requirements-pinned.txt")


def test_windows_create_failure_is_graceful(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("DOCS_VENV_PYTHON", raising=False)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _Result(1, "no venv for you")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="nt", environ=os.environ))
    out = bootstrap.ensure_venv()

    assert out == str(tmp_path / "data" / "venv" / "Scripts" / "python.exe")
    assert len(calls) == 1, calls
    assert not (tmp_path / "data" / "venv" / ".tabella-deps-ok").exists()
