# Backup And Recovery

The Local MVP supports zip-based backup and restore for SQLite and uploads.

## Backup

```bash
python scripts/backup_local_data.py --output backups/lexibridge_backup_YYYYMMDD_HHMMSS.zip
```

Backed up by default:

- SQLite database file.
- `uploads/`.
- `backup_manifest.json`.

Not backed up by default:

- `.env`
- `.git`
- virtual environments
- caches

To include `.env`, pass `--include-env`. This prints a warning because secrets may be exposed.

## Restore

```bash
python scripts/restore_local_data.py --backup backups/example.zip --target ./restore_test
```

The restore script refuses to overwrite a non-empty target unless `--force` is used.

## Future PostgreSQL Plan

Production should use database-native backup:

```bash
pg_dump --format=custom --file lexibridge.dump "$DATABASE_URL"
pg_restore --clean --if-exists --dbname "$DATABASE_URL" lexibridge.dump
```

Production restore must be tested before launch and after schema changes.
