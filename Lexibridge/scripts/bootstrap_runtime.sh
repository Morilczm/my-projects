#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BOOTSTRAP_PYTHON="${LEXIBRIDGE_BOOTSTRAP_PYTHON:-}"
if [ -z "$BOOTSTRAP_PYTHON" ]; then
  BOOTSTRAP_PYTHON="$(command -v python3 || true)"
fi
if [ -z "$BOOTSTRAP_PYTHON" ]; then
  echo "Python 3 is required to bootstrap LexiBridge." >&2
  exit 2
fi

RUNTIME_VENV="${LEXIBRIDGE_RUNTIME_VENV:-}"
if [ -z "$RUNTIME_VENV" ]; then
  RUNTIME_VENV="$($BOOTSTRAP_PYTHON scripts/runtime_environment.py --print-venv)"
fi

case "$RUNTIME_VENV" in
  "$ROOT_DIR"|"$ROOT_DIR"/*)
    echo "Refusing to create the canonical runtime inside the repository: $RUNTIME_VENV" >&2
    echo "Set LEXIBRIDGE_RUNTIME_VENV to a path outside Desktop/repository storage." >&2
    exit 2
    ;;
esac

if [ ! -x "$RUNTIME_VENV/bin/python" ]; then
  "$BOOTSTRAP_PYTHON" -m venv "$RUNTIME_VENV"
fi

RUNTIME_PYTHON="$RUNTIME_VENV/bin/python"
PIP_CERT_PATH="${LEXIBRIDGE_PIP_CERT:-}"
if [ -z "$PIP_CERT_PATH" ] && [ "$(uname -s)" = "Darwin" ] && [ -r /etc/ssl/cert.pem ]; then
  PIP_CERT_PATH=/etc/ssl/cert.pem
fi
PIP_TLS_ARGS=()
if [ -n "$PIP_CERT_PATH" ]; then
  PIP_TLS_ARGS=(--cert "$PIP_CERT_PATH")
fi

"$RUNTIME_PYTHON" -m pip install --disable-pip-version-check \
  "${PIP_TLS_ARGS[@]}" \
  -r backend/requirements-runtime.lock.txt \
  -r backend/requirements-dev.lock.txt

LEXIBRIDGE_RUNTIME_VENV="$RUNTIME_VENV" \
  "$BOOTSTRAP_PYTHON" scripts/runtime_environment.py --diagnose

echo "LexiBridge runtime ready: $RUNTIME_VENV"
