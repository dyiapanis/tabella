r"""Seam test for tabella.bootstrap.ensure_venv platform handling (direct-run).

Shared module serving BOTH servers (mcp_server.py + scripts/mcp_http_server.py).
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
from tabella import bootstrap as B  # noqa: E402


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
    check("override", B.ensure_venv() == str(fake))
    del os.environ["DOCS_VENV_PYTHON"]

# 2. POSIX fast path: existing venv dir with bin/python returns that path
with tempfile.TemporaryDirectory() as td:
    os.environ["PLUGIN_DATA"] = str(Path(td) / "data")
    venv = Path(td) / "data" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    check("posix fast path", B.ensure_venv() == str(venv / "bin" / "python"))
    del os.environ["PLUGIN_DATA"]

# 2b. POSIX bootstrap seam: bash + setup.sh with the data_dir arg
with tempfile.TemporaryDirectory() as td:
    os.environ["PLUGIN_DATA"] = str(Path(td) / "data")
    calls = []
    real_run = subprocess.run

    def fake_run_ok(cmd, **kw):
        calls.append(cmd)
        return R0(0)

    class R0:
        def __init__(self, returncode=0, stderr=""):
            self.returncode, self.stderr = returncode, stderr

    subprocess.run = fake_run_ok
    try:
        out = B.ensure_venv()
    finally:
        subprocess.run = real_run
    want = str(Path(td) / "data" / "venv" / "bin" / "python")
    check("posix bash cmd", calls and calls[0][0] == "bash"
          and calls[0][1].endswith("scripts/setup.sh")
          and calls[0][2] == str(Path(td) / "data"), f"got {calls}")
    check("posix returns venv python", out == want, f"got {out}")
    del os.environ["PLUGIN_DATA"]

# 3. Windows seam
with tempfile.TemporaryDirectory() as td:
    os.environ["PLUGIN_DATA"] = str(Path(td) / "data")
    venv_dir = Path(td) / "data" / "venv"
    calls = []
    real_run = subprocess.run
    real_os = B.os

    class R2:
        def __init__(self, returncode=0, stderr=""):
            self.returncode, self.stderr = returncode, stderr

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return R2(0) if len(calls) == 1 else R2(1, "boom")  # first ok, second fails

    B.os = SimpleNamespace(name="nt", environ=os.environ)
    subprocess.run = fake_run
    try:
        out = B.ensure_venv()
    finally:
        B.os, subprocess.run = real_os, real_run

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
        return R2(1, "no venv for you")

    B.os = SimpleNamespace(name="nt", environ=os.environ)
    subprocess.run = fake_run2
    try:
        out = B.ensure_venv()
    finally:
        B.os, subprocess.run = real_os, real_run
    check("nt create-fail graceful", out == want_python and len(calls) == 1)
    del os.environ["PLUGIN_DATA"]

print("ensure_venv seam: ALL PASS")