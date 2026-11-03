"""A stdio client must see the real version and its own protocol back.

Guards the two drift bugs that shipped: the handshake hardcoded 2024-11-05 in
one transport while the other said 2025-06-18, and both hardcoded a version
number that had to be bumped by hand in five places.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import tabella

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server.py"


@pytest.mark.skipif(not SERVER.exists(), reason="server not present")
def test_initialize_reports_version_and_echoes_protocol():
    env = dict(os.environ, TABELL_REEXEC="1")  # already running in a venv
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}},
    }
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    line = proc.stdout.strip().splitlines()[0]
    info = json.loads(line)["result"]
    assert info["serverInfo"]["version"] == tabella.__version__
    assert info["protocolVersion"] == "2025-03-26", "the client's version must be echoed"
