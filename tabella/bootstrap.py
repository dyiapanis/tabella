"""Shared docs-venv bootstrap for the stdio and HTTP servers.

`docs_root` is the directory that owns the venv; the venv itself always lives
at `<docs_root>/venv`, which is exactly what scripts/setup.sh builds. Keep
those two in step: the interpreter returned here is the one setup.sh created,
and `tests/test_bootstrap_paths.py` asserts that instead of hard-coding a path
that can drift again.

Checks DOCS_VENV_PYTHON first. Otherwise the root is PLUGIN_DATA (provided by
the v1 client) or ~/.venvs/docs.

Platform notes:
- POSIX runs scripts/setup.sh via bash.
- Windows has no bash on a stock box — the venv is built with the stdlib
  venv module + the venv's own pip, mirroring setup.sh
  (--require-hashes -r requirements-pinned.txt).
- The venv layout differs: bin/python vs Scripts/python.exe.
"""

import os
import subprocess
import sys
from pathlib import Path


def docs_root() -> Path:
    """Directory that owns the docs venv (the argument setup.sh takes)."""
    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        return Path(plugin_data)
    return Path.home() / ".venvs" / "docs"


def venv_python_path() -> str:
    """Interpreter inside the docs venv — `<docs_root>/venv`, as setup.sh builds it."""
    venv_dir = docs_root() / "venv"
    if os.name == "nt":
        return str(venv_dir / "Scripts" / "python.exe")
    return str(venv_dir / "bin" / "python")


def resolve_venv_python() -> str:
    """Interpreter to use, honouring an explicit DOCS_VENV_PYTHON override."""
    explicit = os.environ.get("DOCS_VENV_PYTHON")
    if explicit and Path(explicit).exists():
        return explicit
    return venv_python_path()


def _venv_ready(venv_python: str) -> bool:
    """Is this a *usable* docs venv, not just a leftover interpreter?

    Existence alone is not enough: an interrupted first-run install leaves
    bin/python behind with none of the packages, and every later start then
    accepts it and fails at import time. A sentinel marks a completed install;
    a venv without one is probed once (cheap) and adopted only if the imports
    work — existing venvs created before the sentinel existed are not
    re-bootstrapped for nothing.
    """
    if not Path(venv_python).exists():
        return False
    marker = Path(venv_python).parent.parent / ".tabella-deps-ok"
    if marker.exists():
        return True
    probe = subprocess.run(
        [venv_python, "-c", "import docx, odf"],
        capture_output=True, text=True, timeout=120,
    )
    if probe.returncode == 0:
        marker.write_text("")
        return True
    return False


def ensure_venv() -> str:
    """Return the docs-venv interpreter, bootstrapping it on first use."""
    explicit = os.environ.get("DOCS_VENV_PYTHON")
    if explicit and Path(explicit).exists():
        return explicit  # the operator named an interpreter: use it as-is

    venv_python = venv_python_path()
    if _venv_ready(venv_python):
        return venv_python

    root = docs_root()
    root.mkdir(parents=True, exist_ok=True)  # ~/.venvs may not exist on a cold host
    venv_dir = root / "venv"
    marker = venv_dir / ".tabella-deps-ok"
    marker.parent.mkdir(parents=True, exist_ok=True)
    plugin_root = Path(__file__).parent.parent.resolve()

    if os.name == "nt":
        # No bash on a stock Windows box — build the venv with the stdlib
        # venv module + the venv's own pip, mirroring scripts/setup.sh.
        pinned = plugin_root / "requirements-pinned.txt"
        sys.stderr.write("tabella: bootstrapping docs venv (first run)...\n")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            subprocess.run(
                [venv_python, "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                capture_output=True, text=True, timeout=600,
            )
            result = subprocess.run(
                [venv_python, "-m", "pip", "install", "--quiet", "--require-hashes",
                 "-r", str(pinned)],
                capture_output=True, text=True, timeout=600,
            )
        if result.returncode != 0:
            sys.stderr.write(f"tabella: bootstrap failed: {result.stderr[:500]}\n")
        else:
            marker.write_text("")
            sys.stderr.write("tabella: venv ready\n")
        return venv_python

    # POSIX bootstrap: run the setup script on the docs root — it creates
    # <docs_root>/venv, which is what venv_python points at.
    setup_script = plugin_root / "scripts" / "setup.sh"
    if not setup_script.exists():
        sys.stderr.write(f"tabella: setup script not found at {setup_script}\n")
        return venv_python  # let tool calls fail with a helpful error

    sys.stderr.write("tabella: bootstrapping docs venv (first run)...\n")
    result = subprocess.run(
        ["bash", str(setup_script), str(root)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        sys.stderr.write(f"tabella: bootstrap failed: {result.stderr[:500]}\n")
    else:
        marker.write_text("")
        sys.stderr.write("tabella: venv ready\n")

    return venv_python
