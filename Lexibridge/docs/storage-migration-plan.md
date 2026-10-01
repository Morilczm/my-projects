# Storage Migration Plan

PR-11 keeps legacy local paths readable while adding `storage_key`.

## Compatibility Rule

```text
if storage_key exists:
    read via StorageService
elif legacy saved_filename/image_path exists:
    read local path
else:
    return file not found
```

## Dry Run

```bash
python scripts/migrate_local_files_to_storage.py --dry-run
```

Dry-run scans `Document.saved_filename` and `FormulaBlock.image_path` but does not modify the database.

## Apply

```bash
python scripts/migrate_local_files_to_storage.py --apply
```

Apply creates `StorageObject` rows and fills:

- `Document.storage_object_id`
- `Document.storage_key`
- `FormulaBlock.image_storage_object_id`
- `FormulaBlock.image_storage_key`

Legacy files are not deleted by default.

## Move Mode

`--move` removes legacy files after successful storage copy. Do not use it before a verified backup.

## Integrity Check

```bash
python scripts/storage_integrity_check.py
```

Checks missing objects, size mismatch, hash mismatch, privacy visibility warnings, course visibility warnings, and orphan storage files.
