#!/usr/bin/env bash
# Run the test suite. Extra arguments are passed through to pytest.
#
#   ./scripts/test.sh
#   ./scripts/test.sh -k scoring -v
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/python ]]; then
    echo "No .venv found. Run ./scripts/setup.sh first." >&2
    exit 1
fi

exec .venv/bin/python -m pytest "$@"
