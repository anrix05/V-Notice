#!/usr/bin/env bash
# V Notice - Raspberry Pi / Linux Server Startup Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${APP_DIR}"
echo "Starting V Notice Smart Digital Notice Board..."
if [ -f "${APP_DIR}/venv/bin/python" ]; then
    "${APP_DIR}/venv/bin/python" app.py
else
    python3 app.py
fi
