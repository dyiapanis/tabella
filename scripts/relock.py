#!/usr/bin/env python3
"""Regenerate requirements-pinned.txt from pyproject's [all] extra.

    python3 scripts/relock.py            # rewrite the lock
    python3 scripts/relock.py --check    # exit 1 if the lock is stale

Pins come from uv resolving the `all` extra at the Python floor, then every
PyPI file hash for each pinned version is written — so the single lock file
installs with --require-hashes on Linux, macOS and Windows (uv's own
--generate-hashes output only carries the wheels for the platform it ran on).

uv is a dev tool here; the install path still uses pip.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

PYTHON_VERSION = "3.11"  # floor from requires-python: pins must install upward too
PYPI = "https://pypi.org/pypi/{name}/{version}/json"
ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements-pinned.txt"


def _pins() -> list[tuple[str, str]]:
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    direct = "\n".join(extras["all"]) + "\n"
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "extras.in"
        req.write_text(direct)
        out = subprocess.run(
            ["uv", "pip", "compile", "--quiet", "--generate-hashes",
             "--python-version", PYTHON_VERSION,
             "--python-platform", "x86_64-unknown-linux-gnu",
             str(req), "-o", str(Path(tmp) / "lock.txt")],
            capture_output=True, text=True,
        )
        if out.returncode != 0:
            sys.exit(f"uv pip compile failed:\n{out.stderr}")
        text = (Path(tmp) / "lock.txt").read_text()
    pins = []
    for line in text.splitlines():
        if "==" in line and not line.startswith((" ", "#", "-")):
            name, _, rest = line.partition("==")
            pins.append((name.strip(), rest.split()[0].strip().rstrip("\\")))
    return sorted(pins, key=lambda p: p[0].lower())


def _hashes(name: str, version: str) -> list[str]:
    with urllib.request.urlopen(PYPI.format(name=name, version=version), timeout=30) as r:
        files = json.load(r)["urls"]
    return sorted({f["digests"]["sha256"] for f in files if f["digests"].get("sha256")})


def render() -> str:
    lines = []
    for name, version in _pins():
        hashes = _hashes(name, version)
        if not hashes:
            sys.exit(f"{name}=={version}: PyPI returned no sha256 digests")
        lines.append(f"{name}=={version} " + " ".join(f"--hash=sha256:{h}" for h in hashes))
    return "\n".join(lines) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        if LOCK.read_text() != content:
            print("requirements-pinned.txt is stale — run scripts/relock.py")
            return 1
        print("requirements-pinned.txt is current")
        return 0
    LOCK.write_text(content)
    print(f"wrote {LOCK} ({len(content.splitlines())} pins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
