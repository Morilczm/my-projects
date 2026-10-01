#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

bash scripts/bootstrap_runtime.sh

RESOLVER_PYTHON="${LEXIBRIDGE_BOOTSTRAP_PYTHON:-$(command -v python3 || true)}"
PYTHON_BIN="$($RESOLVER_PYTHON scripts/runtime_environment.py --resolve-python)"

PIP_CERT_PATH="${LEXIBRIDGE_PIP_CERT:-}"
if [ -z "$PIP_CERT_PATH" ] && [ "$(uname -s)" = "Darwin" ] && [ -r /etc/ssl/cert.pem ]; then
  PIP_CERT_PATH=/etc/ssl/cert.pem
fi
PIP_TLS_ARGS=()
if [ -n "$PIP_CERT_PATH" ]; then
  PIP_TLS_ARGS=(--cert "$PIP_CERT_PATH")
fi

"$PYTHON_BIN" -m pip install --disable-pip-version-check \
  "${PIP_TLS_ARGS[@]}" \
  -r requirements-e2e.txt

NODE_CA_PATH="${LEXIBRIDGE_NODE_EXTRA_CA_CERTS:-$PIP_CERT_PATH}"
if [ -n "$NODE_CA_PATH" ]; then
  NODE_EXTRA_CA_CERTS="$NODE_CA_PATH" "$PYTHON_BIN" -m playwright install chromium
else
  "$PYTHON_BIN" -m playwright install chromium
fi

echo "LexiBridge Browser E2E runtime ready."
