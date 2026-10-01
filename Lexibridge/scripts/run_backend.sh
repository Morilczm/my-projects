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

SERVER_MODE="${LEXIBRIDGE_SERVER_MODE:-pilot}"
if [ "$SERVER_MODE" != "pilot" ] && [ "$SERVER_MODE" != "development" ]; then
  echo "Unsupported LEXIBRIDGE_SERVER_MODE=$SERVER_MODE (expected pilot or development)." >&2
  exit 2
fi

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-5000}"
GUNICORN_WORKERS="${LEXIBRIDGE_GUNICORN_WORKERS:-1}"
GUNICORN_THREADS="${LEXIBRIDGE_GUNICORN_THREADS:-4}"
GUNICORN_TIMEOUT="${LEXIBRIDGE_GUNICORN_TIMEOUT_SECONDS:-120}"
EFFECTIVE_DATABASE_URL="${DATABASE_URL:-sqlite:}"

if [ "$SERVER_MODE" = "pilot" ] && [[ "$EFFECTIVE_DATABASE_URL" == sqlite:* ]] && [ "$GUNICORN_WORKERS" != "1" ]; then
  echo "SQLite controlled-pilot runtime requires LEXIBRIDGE_GUNICORN_WORKERS=1." >&2
  exit 2
fi

"$PYTHON_BIN" scripts/migrate_db.py --apply

if [ "$SERVER_MODE" = "development" ]; then
  exec "$PYTHON_BIN" backend/app.py
fi

ACCESS_LOG_FORMAT='{"event":"http_access","method":"%(m)s","path":"%(U)s","status":%(s)s,"duration_us":%(D)s}'

exec "$PYTHON_BIN" -m gunicorn \
  --chdir backend \
  --bind "$BACKEND_HOST:$BACKEND_PORT" \
  --workers "$GUNICORN_WORKERS" \
  --worker-class gthread \
  --threads "$GUNICORN_THREADS" \
  --timeout "$GUNICORN_TIMEOUT" \
  --access-logfile - \
  --error-logfile - \
  --capture-output \
  --access-logformat "$ACCESS_LOG_FORMAT" \
  wsgi:application
