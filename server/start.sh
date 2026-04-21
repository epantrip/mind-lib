#!/bin/bash
# Mind Library — Linux/macOS Startup Script
# Usage:
#   ./start.sh          Development mode (Flask built-in server)
#   ./start.sh --prod   Production mode (Gunicorn)
#   ./start.sh --gunicorn-flags "-w 4 --reload"  Custom flags

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "Mind Library v2.2.0 — Startup Script"
echo "================================================"

# Load .env file if it exists
if [ -f .env ]; then
    echo "[*] Loading .env configuration..."
    set -a
    source .env
    set +a
fi

# Check dependencies
if ! python3 -c "import flask" 2>/dev/null; then
    echo "[!] Flask not installed, installing dependencies..."
    pip3 install -r requirements.txt
fi

# Production mode
if [ "$1" == "--prod" ] || [ "$1" == "prod" ]; then
    echo "[*] Production mode: using Gunicorn"
    if ! command -v gunicorn &>/dev/null; then
        echo "[!] gunicorn not installed, installing..."
        pip3 install gunicorn
    fi
    exec gunicorn -c gunicorn.conf.py mind_server_v2.1:app
else
    # Development mode
    echo "[*] Development mode: using Flask built-in server"
    echo "[*] Tip: for production use ./start.sh --prod"
    exec python3 mind_server_v2.1.py
fi