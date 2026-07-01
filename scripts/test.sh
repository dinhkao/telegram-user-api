#!/usr/bin/env bash
# Run the test suite. One command, from anywhere.
#   ./scripts/test.sh                 # all tests
#   ./scripts/test.sh tests/test_order_store.py -v   # one file, verbose
#   ./scripts/test.sh -k task_status  # filter by name
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"

if ! "$PY" -c "import pytest" 2>/dev/null; then
    echo "pytest not installed. Installing dev deps..."
    "$PY" -m pip install -q -r "$ROOT/requirements-dev.txt"
fi

cd "$ROOT"
exec "$PY" -m pytest "$@"
