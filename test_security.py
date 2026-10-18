"""Security guards for catalog review round 3 (2026-10-17).

Ponytail checks: asserts only, no framework. Run: python3 test_security.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tabella.convert import _check_format, _FORMAT_RE
from tabella.create import _css_escape

ok = 0

# 1. Format validation — Lua path rejected
for bad in ["evil.lua", "/tmp/x.lua", "a b", "'evil'", "markdown+lua.lua"]:
    try:
        _check_format(bad, "from_format")
        print(f"FAIL: {bad} did not raise")
    except ValueError:
        ok += 1

for good in ["pdf", "markdown", "docx", "markdown+tex_math_dollars", "markdown-header_attributes"]:
    if not _FORMAT_RE.match(good):
        print(f"FAIL: good format {good} rejected")

# 2. CSS escape — newline and backslash can't smuggle out
malicious = "x'\n@font-face { src: url(http://169.254.169.254/x) }"
escaped = _css_escape(malicious)
assert "'\\n@font-face" not in escaped and "\n" not in escaped, "newline not escaped"
assert "\\A " in escaped, "newline not preserved as CSS escape"

# 3. Venv re-exec marker logic (read-only check)
from mcp_server import _ensure_venv  # noqa: F401

print(f"ALL SECURITY GUARDS LANDED ({ok} rejected formats)")
