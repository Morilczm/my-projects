# Database Migration Plan

LexiBridge AI Local MVP keeps SQLite for local development and course demo use. PR-11 prepares the boundary for PostgreSQL without forcing every developer to install PostgreSQL.

## Current Local MVP

- SQLite remains supported.
- `scripts/migrate_db.py` and `ensure_schema_columns()` remain local compatibility helpers.
- `db.create_all()` is acceptable for local pilot setup only.

## Risks Of Current Local Migration

- Hand-written `ALTER TABLE` migrations have no downgrade path.
- SQLite does not enforce the same constraints and types as PostgreSQL.
- Indexes and foreign keys need a formal Alembic migration before staging.

## Target Roadmap

### v1.0 Local Pilot

- SQLite.
- LocalStorageBackend.
- JSONL export/import dry-run.
- Schema audit and readiness checks.

### v1.5 Staging

- Introduce Flask-Migrate / Alembic.
- Create PostgreSQL schema from reviewed migrations.
- Run SQLite export and PostgreSQL import dry-run.
- Run storage migration dry-run.

### v2.0 Production

- PostgreSQL.
- Alembic migrations only.
- Object storage for uploads/derived files.
- Backup, restore, and integrity drill before launch.

## SQLite -> PostgreSQL Steps

1. Backup SQLite database and uploads.
2. Run `python scripts/schema_audit.py`.
3. Run `python scripts/check_database_readiness.py`.
4. Export data:
   ```bash
   python scripts/export_sqlite_data.py --db backend/lexibridge.db --output exports/sqlite_export_YYYYMMDD
   ```
5. Create PostgreSQL schema with Alembic in staging.
6. Dry-run import:
   ```bash
   python scripts/import_postgres_data.py --input exports/sqlite_export_YYYYMMDD --database-url postgresql://...
   ```
7. Apply only after staging review.
8. Run integrity checks, pytest, and evaluation regression.
9. Switch `DATABASE_URL` and `DATABASE_ENGINE=postgresql`.
10. Keep rollback: original SQLite backup + uploads backup.
