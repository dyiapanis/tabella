r"""Seam test for _ensure_venv platform handling (direct-run, no framework).

Proves, without a Windows box:
  1. DOCS_VENV_PYTHON override short-circuits.
  2. POSIX fast path unchanged (bin/python).
  3. os.name=="nt": Scripts\python.exe layout, venv+pip bootstrap commands
     mirror setup.sh (--require-hashes -r requirements-pinned.txt), success
     and failure paths both behave.

The nt seam swaps mcp_server.os for a namespace (NOT global os.name — that
flips the shared pathlib factory to WindowsPath, uninstantiable on Linux).
Path separators in expectations are built with the same Path arithmetic, so
they match this platform; the real backslash layout is proven by CI on
windows-latest.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_server as M  # noqa: E402


def check(name, cond, detail=""):
    if not cond:
        print(f"FAIL {name}: {detail}")
        sys.exit(1)
    print(f"PASS {name}")


# 1. override short-circuits
with tempfile.TemporaryDirectory() as td:
    fake = Path(td) / "wpython.exe"
    fake.write_text("")
    os.environ["DOCS_VENV_PYTHON"] = str(fake)
    check("override", M._ensure_venv() == str(fake))
    del os.environ["DOCS_VENV_PYTHON"]

# 2. POSIX fast path: existing venv dir with bin/python returns that path
with tempfile.TemporaryDirectory() as td:
    os.environ["PLUGIN_DATA"] = str(Path(td) / "data")
    venv = Path(td) / "data" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    check("posix fast path", M._ensure_venv() == str(venv / "bin" / "python"))
    del os.environ["PLUGIN_DATA"]

# 3. Windows seam
with tempfile.TemporaryDirectory() as td:
    os.environ["PLUGIN_DATA"] = str(Path(td) / "data")
    venv_dir = Path(td) / "data" / "venv"
    calls = []
    real_run = subprocess.run
    real_os = M.os

    class R:
        def __init__(self, returncode=0, stderr=""):
            self.returncode, self.stderr = returncode, stderr

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return R(0) if len(calls) == 1 else R(1, "boom")  # first ok, second fails

    M.os = SimpleNamespace(name="nt", environ=os.environ)
    subprocess.run = fake_run
    try:
        out = M._ensure_venv()
    finally:
        M.os, subprocess.run = real_os, real_run

    want_python = str(venv_dir / "Scripts" / "python.exe")
    check("nt layout", out == want_python, f"got {out}")
    check("nt venv cmd", calls and calls[0] == [sys.executable, "-m", "venv", str(venv_dir)],
          f"got {calls}")
    check("nt pip cmd", len(calls) == 2 and calls[1][:3] == [want_python, "-m", "pip"]
          and "--require-hashes" in calls[1] and "requirements-pinned.txt" in calls[1][-1],
          f"got {calls}")

    # failure at venv-creation stage: single call, still returns the path
    calls.clear()

    def fake_run2(cmd, **kw):
        calls.append(cmd)
        return R(1, "no venv for you")

    M.os = SimpleNamespace(name="nt", environ=os.environ)
    subprocess.run = fake_run2
    try:
        out = M._ensure_venv()
    finally:
        M.os, subprocess.run = real_os, real_run
    check("nt create-fail graceful", out == want_python and len(calls) == 1)
    del os.environ["PLUGIN_DATA"]

print("ensure_venv seam: ALL PASS")