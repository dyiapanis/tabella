#!/usr/bin/env bash
# tabella bootstrap script — creates a venv and installs dependencies.
#
# Called by mcp_server.py on first startup when the docs venv is missing.
# Can also be run manually:
#
#   bash scripts/setup.sh [DATA_DIR]
#
# If PLUGIN_DATA env var is set (by the v1 client), the venv is created there.
# Otherwise defaults to ~/.venvs/docs.
set -euo pipefail

DATA_DIR="${1:-${PLUGIN_DATA:-$HOME/.venvs/docs}}"
VENV_DIR="$DATA_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"

echo "tabella: setting up docs venv at $VENV_DIR"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# Install Python dependencies — exact versions pinned with sha256 hashes
# (all 25 transitive packages locked; see requirements-pinned.txt). The lock
# was generated with the ranges below and installs are reproducible: a fresh
# venv from this file resolves byte-identically.
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet --require-hashes \
    -r "$(dirname "$0")/../requirements-pinned.txt"

echo "tabella: venv ready at $VENV_PYTHON"