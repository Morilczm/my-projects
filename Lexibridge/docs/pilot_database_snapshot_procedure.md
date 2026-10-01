# Pilot Database Snapshot Procedure

## Scope

This procedure applies to the `pilot-internal-local` SQLite database. It is
read/copy only with respect to the source database and does not authorize row
updates, job retries, data deletion, or a restore over the live database.

The source identity is:

```text
project-root/backend/lexibridge.db
```

## Snapshot Times

Create and retain a snapshot:

1. immediately before the observation window starts;
2. before and after a controlled Freeze or drain;
3. after any rollback;
4. at the end of each actual pilot operating day;
5. at observation review.

Each snapshot record must contain the UTC timestamp, environment, deployed
commit, operator, database identity, backup ID, manifest path, and queue state.

## Create And Verify

Choose an operator-controlled path outside the repository and run:

```bash
backend/.venv-macos/bin/python scripts/pilot_backup.py \
  --database backend/lexibridge.db \
  --uploads uploads \
  --output <durable-snapshot-path>

backend/.venv-macos/bin/python scripts/verify_pilot_backup.py \
  --backup <durable-snapshot-path>
```

The backup includes the complete SQLite database, so it includes:

- `alignment_run`;
- `background_job`;
- `background_job_event`;
- `document_alignment_workflow_runs`;
- `document_alignment_workflow_items`;
- all other application tables recorded in the manifest.

Do not place `.env`, credentials, API keys, tokens, raw logs, or unapproved
exports in the snapshot directory.

## Observation Snapshot

Capture the Legacy queue separately because the backup manifest's generic
table counts do not classify jobs by type or status:

```bash
backend/.venv-macos/bin/python scripts/legacy_alignment_runtime.py status \
  --json-output <evidence-path>/legacy-queue.json
```

Record Formal run and worker evidence from the same database snapshot and UTC
collection interval. Never infer a zero count from a missing table or failed
query.

## Restore Verification

Restore only to new isolated targets:

```bash
backend/.venv-macos/bin/python scripts/pilot_restore.py \
  --backup <durable-snapshot-path> \
  --database-target <isolated-restore-path>/lexibridge-restored.db \
  --uploads-target <isolated-restore-path>/uploads
```

Require successful manifest verification, matching backup/restore database
hashes, SQLite `integrity_check=ok`, and all required core tables. Run an
application smoke check against the isolated restored database before marking
the snapshot restorable. Never use `--force` against the declared live source.

## Readiness Rehearsal

On 2026-07-22, Task 9C.5O.2 performed a source read, backup, manifest/hash
verification, and isolated restore under `/private/tmp`. Results:

- source database readiness: PASS;
- backup creation: PASS;
- backup verification: PASS;
- restored SQLite integrity: `ok`;
- restored core tables: PASS;
- source database writes by the procedure: none.

The temporary artifact proves the procedure, not durable retention. The
observation owner must create a new snapshot in an approved durable location
at the actual start time.
