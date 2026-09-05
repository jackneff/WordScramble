#!/usr/bin/env bash
# Start the development server with auto-reload.
#
#   ./scripts/run.sh
#   PORT=8000 ./scripts/run.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/python ]]; then
    echo "No .venv found. Run ./scripts/setup.sh first." >&2
    exit 1
fi

# Debug mode gives auto-reload and tracebacks. Local only - never in production.
export FLASK_DEBUG=1
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-5000}"

echo "Word Scramble -> http://${HOST}:${PORT}  (Ctrl+C to stop)"
exec .venv/bin/python app.py
