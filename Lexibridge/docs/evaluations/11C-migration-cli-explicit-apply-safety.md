# Task 11C: Migration CLI Explicit Apply Safety

- Status: `MIGRATION_CLI_EXPLICIT_APPLY_SAFETY_CLOSED`
- Baseline commit: `a1aaa8b3eb6ed15d7161ae3dfdfe608e4a7b2384`
- Branch: `fix/migration-cli-explicit-apply-11c`
- Database schema changed: `False`
- Migration/seed order changed: `False`

## Original Defect

`scripts/migrate_db.py --help` executed the existing migration and seed path instead of displaying help. The script loaded `backend/app.py` at module import time, had no argument parser, and called migration work from `main()` regardless of `sys.argv`.

That meant `--help`, unknown arguments, and no arguments could run:

```text
db.create_all()
ensure_schema_columns()
seed users/courses/plans
model/provider registry seed
demo knowledge seed
```

## Final CLI Contract

| Command | Exit Code | App Import | DB Access | Migration | Seed |
|---|---:|---:|---:|---:|---:|
| `python scripts/migrate_db.py --help` | 0 | no | no | no | no |
| `python scripts/migrate_db.py` | 2 | no | no | no | no |
| `python scripts/migrate_db.py --unknown` | 2 | no | no | no | no |
| `python scripts/migrate_db.py --apply --unknown` | 2 | no | no | no | no |
| `python scripts/migrate_db.py --apply` | 0 | yes | isolated target DB | yes | yes |

The argument parser is built before any backend app import. The Flask app, SQLAlchemy models, and migration helpers are imported only inside the `--apply` execution path.

## Caller Audit

| Caller | Current decision | Reason |
|---|---|---|
| `scripts/dev_check.py` | add `--apply` | Explicit database initialization step; `build_check_env()` points to a temporary SQLite database and temp upload paths |
| `scripts/run_backend.sh` | add `--apply` | Startup script intentionally migrates before launching the backend |
| `scripts/run_browser_e2e.py` | add `--apply` | Browser E2E setup creates an isolated SQLite database before seeding |
| `scripts/pilot_readiness_check.py` | add `--apply` | Fresh database migration phase uses readiness temp DB environment |
| Migration/database tests | add `--apply` | Tests explicitly verify migration/upgrade/seed behavior against pytest temporary databases |
| `scripts/build_final_release.py` | unchanged | Only compiles `scripts/migrate_db.py`; it does not execute migration |
| `scripts/package_release.sh` | unchanged | Only compiles/scans release artifacts; it does not execute migration |
| Historical reports and runbooks | unchanged | Textual historical instructions/evidence are not executable callers in this task |
| `tests/test_migrate_db_cli.py` | intentionally variable | Dedicated CLI contract tests exercise help, refusal, bad args, and apply |

## Migration Semantics

| Behavior | Kept unchanged | Test evidence | Static evidence | Not verified |
|---|---:|---|---|---:|
| `db.create_all()` remains first in apply path | yes | `tests/test_migrate_db_cli.py`, `tests/test_migrations.py` | `scripts/migrate_db.py::run_migration` | no |
| `ensure_schema_columns()` still follows create_all | yes | migration and upgrade tests | `scripts/migrate_db.py::run_migration` | no |
| user seed behavior | yes | apply test confirms seed rows are created | unchanged loop body | no |
| course and membership seed behavior | yes | apply test and migration tests | unchanged loop body | no |
| plan seed behavior | yes | apply test confirms seed summary | unchanged loop body | no |
| model/provider registry seed behavior | yes | apply test confirms provider table exists | unchanged calls | no |
| demo knowledge seed behavior | yes | apply output and demo seed tests | unchanged call | no |
| exception propagation | yes | no broad exception handler added | `main()` returns after `run_migration()` and does not swallow exceptions | no |

## Dev Check

`scripts/dev_check.py` now invokes:

```text
python scripts/migrate_db.py --apply
```

Its runtime environment is isolated by `build_check_env()`:

```text
DATABASE_URL = sqlite:///<DEV_CHECK_TEMP>/lexibridge_dev_check.db
UPLOAD_FOLDER = <DEV_CHECK_TEMP>/uploads
PYTHONPYCACHEPREFIX = <DEV_CHECK_TEMP>/pycache
AI_PROVIDER = none
OCR_PROVIDER = none
FORMULA_OCR_PROVIDER = none
```

The real dev check was run successfully. It executed release safety, full pytest, isolated migration apply, and backend `/api/test` smoke check.

## Release Safety

`scripts/check_release_safety.py` now includes a small static rule for executable `scripts/` and `tests/` files. It rejects migration CLI calls that reference `scripts/migrate_db.py` without nearby `--apply`, except for the dedicated CLI safety tests and historical accident-report generator.

## Database Protection

- Incident database: `backend/lexibridge.db`
- Incident SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- Accepted as normal baseline: `False`
- This task did not run `--apply` against the incident database.
- CLI tests and dev check used temporary SQLite databases.

## Test Results

| Command | Result |
|---|---|
| `backend/.venv-macos/bin/python -m pytest tests/test_migrate_db_cli.py -q` | `5 passed` |
| Migration/dev_check/release-safety focused suite | `40 passed` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python scripts/dev_check.py` | `All local pre-release checks passed.` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python -m pytest -q` | `1213 passed, 6 warnings` |
| `backend/.venv-macos/bin/python scripts/check_release_safety.py` | `Release safety check passed.` |

## Privacy And Network

- Provider requests: `0`
- External document API requests: `0`
- Document egress: `0`
- Private data usage: `0`
- Model downloads: `0`
- External network requests: `0`

Existing tests may bind local loopback ports for HTTP E2E. No external Provider or document API is required.

## Remaining Limitations

- This task does not replace the additive migration system with Alembic.
- This task does not change migration or seed business content.
- Historical documentation still contains pre-11C command examples as historical records; operational callers were updated.

## Final State

`MIGRATION_CLI_EXPLICIT_APPLY_SAFETY_CLOSED`
