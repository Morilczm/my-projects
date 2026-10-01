# Controlled Runtime Stabilization

## Decision

LexiBridge's controlled local/private pilot uses a repository-external Python
runtime, an exactly pinned dependency set, a Gunicorn WSGI server, and
payload-free loopback observation. The Flask development server is no longer
the default start path.

This is deployment hardening for a bounded pilot. It is not a claim of
internet-scale production readiness, multi-host supervision, or PostgreSQL
concurrency.

## Runtime Resolution

`scripts/runtime_environment.py` resolves interpreters in this order:

1. explicit `LEXIBRIDGE_PYTHON`;
2. the external `LEXIBRIDGE_RUNTIME_VENV` or platform default;
3. `backend/.venv` compatibility environment;
4. legacy `backend/.venv-macos` compatibility environment;
5. the resolver interpreter.

Each candidate must execute and import every required runtime distribution.
An existing file is not considered a healthy environment merely because its
`bin/python` path exists. Diagnostics contain only paths, booleans, stable
reason labels, and package versions; they do not inspect credentials.

On macOS the default is under Application Support, outside the Desktop
repository. `scripts/bootstrap_runtime.sh` refuses to create the canonical
runtime inside the repository. It keeps TLS verification enabled and uses the
readable system CA bundle when the command-line Python lacks an installed CA
chain.

## Dependency Contract

- `backend/requirements-runtime.lock.txt`: application and Gunicorn runtime;
- `backend/requirements-dev.lock.txt`: pytest-only support;
- `requirements-e2e.txt`: exact Playwright runtime plus the dev lock;
- optional layout and multilingual model runtimes remain separate.

All active entries use exact versions. Parser/model experimentation must not
silently add heavyweight model dependencies to the base runtime.
`scripts/bootstrap_e2e.sh` installs the exact Browser E2E lock and Chromium
separately, retaining verified CA handling for both pip and Playwright/Node.

## Server Contract

`scripts/run_backend.sh` performs explicit schema application and defaults to:

```text
Gunicorn -> backend/wsgi.py -> existing backend/app.py application
```

The current SQLite pilot defaults to one Gunicorn process with bounded gthread
concurrency. Operators may select the Flask development server only through
`LEXIBRIDGE_SERVER_MODE=development`. Access logs omit query strings and bodies;
their bounded fields are method, URL path, status, and duration. Client-supplied
request identifiers are not copied into the JSON log.

`scripts/run_worker.sh` and `scripts/run_python.sh` reuse the same interpreter
resolver, so the backend, worker, migrations, tests, and operational scripts do
not drift across Python environments.

## Observation Contract

`scripts/collect_runtime_probe.py` accepts only loopback HTTP `/api/test` and
writes one JSONL record containing status, latency, stable error code, endpoint
path, target label, and timestamp. It never stores response bodies, request
bodies, credentials, authorization headers, course materials, query text, or
student data.

`scripts/runtime_observation_report.py` calculates duration and active days only
from retained samples inside the declared window. It also verifies that the
window has actually elapsed. It returns `RUNTIME_OBSERVATION_PENDING` until real
evidence satisfies every configured gate. Repository tests prove aggregation
behavior but do not count as elapsed pilot observation.

## Remaining Boundaries

- A real observation window is operational evidence and is not fabricated by
  this change.
- Gunicorn master-process supervision and restart-on-host-reboot remain an
  operator/deployment concern.
- SQLite remains limited to the controlled small pilot.
- The large `backend/app.py`, additive schema migration, and frontend monolith
  are separate refactoring tasks.
