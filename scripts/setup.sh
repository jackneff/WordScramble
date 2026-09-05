#!/usr/bin/env bash
# Create the virtual environment and install dependencies.
#
#   ./scripts/setup.sh          # app + test dependencies
#   ./scripts/setup.sh --prod   # app dependencies only
set -euo pipefail

cd "$(dirname "$0")/.."

DEV=1
[[ "${1:-}" == "--prod" ]] && DEV=0

if [[ ! -d .venv ]]; then
    echo "Creating virtual environment in .venv ..."
    python3 -m venv .venv
else
    echo "Using the existing .venv"
fi

echo "Installing dependencies ..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt --quiet
[[ $DEV -eq 1 ]] && .venv/bin/python -m pip install -r requirements-dev.txt --quiet

if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Created .env from .env.example - fine as-is for local development."
fi

cat <<'DONE'

Setup complete.
  ./scripts/run.sh     start the dev server
  ./scripts/test.sh    run the test suite
DONE
