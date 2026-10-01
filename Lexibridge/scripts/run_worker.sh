#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

RESOLVER_PYTHON="${LEXIBRIDGE_BOOTSTRAP_PYTHON:-$(command -v python3 || true)}"
if [ -z "$RESOLVER_PYTHON" ]; then
  echo "Python 3 is required to resolve the LexiBridge runtime." >&2
  exit 2
fi
PYTHON_BIN="$($RESOLVER_PYTHON scripts/runtime_environment.py --resolve-python)"
exec "$PYTHON_BIN" scripts/run_worker.py "$@"
