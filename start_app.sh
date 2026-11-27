#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export REDIS_PORT="${REDIS_PORT:-6379}"

if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
fi

if [ ! -f "config.py" ]; then
    "$PYTHON_BIN" generate_config.py
fi

if [ -z "${SECRET_KEY:-}" ]; then
    if [ -f ".env" ] && grep -qE '^SECRET_KEY=.+' .env; then
        set -a
        # shellcheck disable=SC1091
        source .env
        set +a
    fi
fi

if [ -z "${SECRET_KEY:-}" ]; then
    echo "ERROR: SECRET_KEY is not set in environment or .env. Generate one before starting." >&2
    exit 1
fi

"$PYTHON_BIN" app.py > app_run.log 2>&1 &
echo "TrendPulse started (PID $!), logging to app_run.log"
