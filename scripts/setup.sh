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

# Install Python dependencies
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet \
    "python-docx>=1.0,<2.0" \
    "openpyxl>=3.1,<4.0" \
    "python-pptx>=0.6,<2.0" \
    "weasyprint>=60.0,<70.0" \
    "odfpy>=1.4,<2.0" \
    "Pillow>=10.0,<13.0" \
    "lxml>=5.0,<7.0" \
    "PyMuPDF>=1.24,<2.0" \
    "firecrawl-anydoc>=0.1.1,<0.3.0" \
    "liteparse>=2.0.0,<3.0.0"

echo "tabella: venv ready at $VENV_PYTHON"