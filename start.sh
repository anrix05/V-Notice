#!/usr/bin/env bash
# V Notice - Raspberry Pi Startup Script
cd "$(dirname "$0")"
echo "Starting V Notice Smart Digital Notice Board..."
python3 app.py
