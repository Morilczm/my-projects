#!/usr/bin/env python3
"""Restore a verified LexiBridge pilot backup to new SQLite/uploads targets."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_pilot_backup import CORE_TABLES, load_manifest, sha256_file, verify_backup  # noqa: E402


def target_exists(path: Path) -> bool:
    if path.is_file():
        return True
    if path.is_dir() and any(path.iterdir()):
        return True
    return False


def sqlite_integrity(database_path: Path) -> str:
    with sqlite3.connect(database_path) as conn:
        return str(conn.execute("pragma integrity_check").fetchone()[0])


def check_core_tables(database_path: Path) -> list[str]:
    with sqlite3.connect(database_path) as conn:
        existing = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            ).fetchall()
        }
    return [name for name in CORE_TABLES if name not in existing]


def restore_backup(backup: Path, database_target: Path, uploads_target: Path, *, force: bool = False) -> dict:
    backup = backup.expanduser().resolve()
    database_target = database_target.expanduser().resolve()
    uploads_target = uploads_target.expanduser().resolve()
    verification = verify_backup(backup)
    manifest = load_manifest(backup)

    if not force:
        existing = [str(path) for path in (database_target, uploads_target) if target_exists(path)]
        if existing:
            raise FileExistsError("restore targets already exist; pass --force to overwrite: " + ", ".join(existing))

    if database_target.exists():
        database_target.unlink()
    if uploads_target.exists():
        if uploads_target.is_dir():
            shutil.rmtree(uploads_target)
        else:
            uploads_target.unlink()

    database_target.parent.mkdir(parents=True, exist_ok=True)
    uploads_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup / manifest["database"]["path"], database_target)
    uploads_source = backup / manifest["uploads"]["path"]
    if uploads_source.exists():
        shutil.copytree(uploads_source, uploads_target)
    else:
        uploads_target.mkdir(parents=True, exist_ok=True)

    restored_hash = sha256_file(database_target)
    if restored_hash != manifest["database"]["sha256"]:
        raise ValueError("restored database sha256 mismatch")
    integrity = sqlite_integrity(database_target)
    if integrity.lower() != "ok":
        raise ValueError(f"restored SQLite integrity_check failed: {integrity}")
    missing_tables = check_core_tables(database_target)
    if missing_tables:
        raise ValueError("restored database missing core tables: " + ", ".join(missing_tables))

    return {
        "status": "success",
        "backup_id": manifest["backup_id"],
        "database_target": str(database_target),
        "uploads_target": str(uploads_target),
        "database_sha256": restored_hash,
        "sqlite_integrity": integrity,
        "core_table_counts": verification["core_table_counts"],
        "uploads_file_count": verification["uploads_file_count"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore a LexiBridge pilot backup.")
    parser.add_argument("--backup", required=True, help="Backup directory containing backup_manifest.json.")
    parser.add_argument("--database-target", required=True, help="Destination SQLite database path.")
    parser.add_argument("--uploads-target", required=True, help="Destination uploads directory path.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing restore targets.")
    args = parser.parse_args(argv)
    try:
        result = restore_backup(
            Path(args.backup),
            Path(args.database_target),
            Path(args.uploads_target),
            force=args.force,
        )
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
