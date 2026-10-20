"""Shared docs-venv bootstrap for the stdio and HTTP servers.

Returns the path to the docs venv Python, bootstrapping if needed.

Checks DOCS_VENV_PYTHON first. If unset or the venv doesn't exist, one is
created in PLUGIN_DATA (provided by the v1 client) or ~/.venvs/docs.

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


def ensure_venv() -> str:
    # If DOCS_VENV_PYTHON is set and exists, use it
    venv_python = os.environ.get("DOCS_VENV_PYTHON")
    if venv_python and Path(venv_python).exists():
        return venv_python

    # Determine where to create the venv
    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        venv_dir = Path(plugin_data) / "venv"
    else:
        venv_dir = Path.home() / ".venvs" / "docs"

    if os.name == "nt":
        venv_python = str(venv_dir / "Scripts" / "python.exe")
    else:
        venv_python = str(venv_dir / "bin" / "python")

    if venv_dir.exists() and Path(venv_python).exists():
        return venv_python

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
            result = subprocess.run(
                [venv_python, "-m", "pip", "install", "--quiet", "--require-hashes",
                 "-r", str(pinned)],
                capture_output=True, text=True, timeout=600,
            )
        if result.returncode != 0:
            sys.stderr.write(f"tabella: bootstrap failed: {result.stderr[:500]}\n")
        else:
            sys.stderr.write("tabella: venv ready\n")
        return venv_python

    # POSIX bootstrap: run the setup script
    setup_script = plugin_root / "scripts" / "setup.sh"
    if not setup_script.exists():
        sys.stderr.write(f"tabella: setup script not found at {setup_script}\n")
        return venv_python  # let tool calls fail with a helpful error

    sys.stderr.write("tabella: bootstrapping docs venv (first run)...\n")
    data_dir = str(venv_dir.parent) if plugin_data else str(venv_dir)
    result = subprocess.run(
        ["bash", str(setup_script), data_dir],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        sys.stderr.write(f"tabella: bootstrap failed: {result.stderr[:500]}\n")
    else:
        sys.stderr.write("tabella: venv ready\n")

    return venv_python