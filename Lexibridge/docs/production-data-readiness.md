# Production Data Readiness

LexiBridge AI is local pilot-ready, not production data-ready.

## Current State

- SQLite supported.
- LocalStorageBackend supported.
- StorageObject metadata added.
- JSONL SQLite export added.
- PostgreSQL import dry-run added.
- Storage migration dry-run/apply added.
- Schema audit and integrity checks added.

## Required Before Production

- PostgreSQL schema managed by Alembic.
- Object storage configured and tested.
- Backup and restore drill.
- Storage integrity check with zero missing objects.
- Database readiness check with no orphan records.
- Evaluation regression after migration.
- No production use of default test accounts or mock payment/email.

## Current Audit Result

Latest local run:

```text
Schema Audit Result: WARN
Tables checked: 35
Issues: 13

Database Readiness: WARN
Duplicate terminology cards detected: 3
Orphan records: 0
Missing personal owner records: 0

Storage Integrity: PASS
Missing objects: 0
Hash mismatch: 0
```
