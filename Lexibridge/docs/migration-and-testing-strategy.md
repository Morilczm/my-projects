# Migration And Testing Strategy

## Current Database Strategy

LexiBridge AI Local MVP uses SQLite to keep the course-demo setup simple and portable.

The current migration approach is intentionally lightweight:

- `db.create_all()` creates missing tables.
- `ensure_schema_columns()` adds missing SQLite columns for existing local databases.
- `scripts/migrate_db.py` runs both, then seeds users, courses, plans, knowledge sources, and model registry defaults.

This is acceptable for the Local MVP, but it is not a production migration system.

## Required Local Migration Properties

`scripts/migrate_db.py` must:

- Work on an empty SQLite database.
- Work on an older partial schema.
- Be safe to run repeatedly.
- Preserve existing users, courses, documents, cards, and evaluation data.
- Create or backfill PR-1 through PR-6 tables and columns.

Core PR-5 tables checked by tests:

- `formula_block`
- `alignment_run`
- `evaluation_set`
- `evaluation_item`
- `evaluation_run`
- `personal_access_audit`
- `terminology_card`

PR-6 background job tables:

- `background_job`
- `background_job_event`

## Test Command

```bash
backend/.venv-macos/bin/python -m pytest tests/test_migrations.py
```

The migration tests cover empty database migration, old schema migration, idempotency, required tables/fields, and data preservation.

## Future v1.0 Migration Plan

Before production, replace the local schema helper with Flask-Migrate / Alembic:

1. Freeze current SQLite schema as baseline.
2. Create Alembic revision `0001_baseline`.
3. Add explicit upgrade/downgrade scripts for every schema change.
4. Add migration checks to CI.
5. Back up SQLite data.
6. Export data into PostgreSQL-compatible formats.
7. Import to PostgreSQL.
8. Verify row counts, foreign keys, and evidence snapshots.
9. Enable production-only migrations against a staging database first.

## SQLite To PostgreSQL Notes

The current schema uses text JSON fields for local portability. A PostgreSQL migration should consider:

- JSONB for snapshots and score breakdowns.
- Native timestamp columns.
- Foreign key constraints.
- Indexes for `scope_type`, `course_id`, `owner_user_id`, `knowledge_base_type`, `visibility`.
- pgvector or external vector DB integration after a stable migration baseline exists.

## Testing Layers

PR-5 testing layers:

- API contract: `tests/test_api_contract.py`
- Authentication: `tests/test_auth.py`
- RBAC and course permissions: `tests/test_permissions.py`
- Upload security: `tests/test_upload_security.py`
- Personal privacy: `tests/test_personal_privacy.py`
- Migrations: `tests/test_migrations.py`
- Background jobs: `tests/test_jobs.py`, `tests/test_job_api.py`, `tests/test_worker.py`

Full local check:

```bash
backend/.venv-macos/bin/python -m pytest
```
