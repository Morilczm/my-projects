#!/usr/bin/env python3
"""Create a local pilot backup for SQLite data and uploads.

The backup format is intentionally simple: a directory containing a SQLite
copy, an uploads tree, and a manifest with hashes and row-count summaries.
It never includes .env files or provider secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORE_TABLES = [
    "user",
    "knowledge_source",
    "knowledge_chunk",
    "concept_alignment_card",
    "concept_card_review_record",
    "student_course_membership",
    "course_student_visibility_policy",
    "student_concept_card_state",
    "feedback",
    "audit_record",
]
SECRET_NAME_PARTS = ("env", "secret", "token", "apikey", "api_key", "credential")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except OSError:
        return ""


def is_inside_project(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def table_summary(database_path: Path) -> dict[str, int]:
    summary: dict[str, int] = {}
    with sqlite3.connect(database_path) as conn:
        names = [
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
            ).fetchall()
        ]
        for name in names:
            try:
                summary[name] = int(conn.execute(f'select count(*) from "{name}"').fetchone()[0])
            except sqlite3.DatabaseError:
                summary[name] = -1
    return summary


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(str(source))
    try:
        destination_conn = sqlite3.connect(str(destination))
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
    finally:
        source_conn.close()


def should_skip_upload(relative_path: Path) -> bool:
    name = relative_path.name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    return any(part in name for part in SECRET_NAME_PARTS)


def copy_uploads(source: Path, destination: Path) -> tuple[list[dict[str, Any]], list[str]]:
    destination.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not source.exists():
        warnings.append("uploads_missing")
        return files, warnings

    for item in sorted(source.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        if should_skip_upload(relative):
            if "skipped_sensitive_upload_file" not in warnings:
                warnings.append("skipped_sensitive_upload_file")
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        files.append(
            {
                "relative_path": relative.as_posix(),
                "sha256": sha256_file(target),
                "size_bytes": target.stat().st_size,
            }
        )
    return files, warnings


def build_backup(database: Path, uploads: Path, output: Path) -> dict[str, Any]:
    database = database.expanduser().resolve()
    uploads = uploads.expanduser().resolve()
    output = output.expanduser().resolve()
    if not database.exists():
        raise FileNotFoundError(f"SQLite database not found: {database}")

    warnings: list[str] = []
    if is_inside_project(output):
        warnings.append("backup_output_inside_project_tree")
    if output.exists() and any(output.iterdir()):
        output = output / f"pilot-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=False)

    backup_id = f"pilot-backup-{uuid.uuid4().hex}"
    db_target = output / "database.sqlite"
    uploads_target = output / "uploads"
    sqlite_backup(database, db_target)
    upload_files, upload_warnings = copy_uploads(uploads, uploads_target)
    warnings.extend(upload_warnings)

    upload_total_size = sum(int(item["size_bytes"]) for item in upload_files)
    manifest = {
        "manifest_version": "pilot-backup-v1",
        "backup_id": backup_id,
        "created_at": utc_now(),
        "git_commit": git_commit(),
        "source_summary": {
            "database_name": database.name,
            "uploads_name": uploads.name,
        },
        "database": {
            "path": "database.sqlite",
            "sha256": sha256_file(db_target),
            "size_bytes": db_target.stat().st_size,
            "tables": table_summary(db_target),
            "core_tables": CORE_TABLES,
        },
        "uploads": {
            "path": "uploads",
            "file_count": len(upload_files),
            "total_size_bytes": upload_total_size,
            "files": upload_files,
        },
        "warnings": warnings,
    }
    manifest_path = output / "backup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    manifest["backup_path"] = str(output)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a LexiBridge pilot backup.")
    parser.add_argument("--database", required=True, help="SQLite database path.")
    parser.add_argument("--uploads", required=True, help="Uploads directory path.")
    parser.add_argument("--output", required=True, help="Backup output directory.")
    args = parser.parse_args(argv)

    try:
        manifest = build_backup(Path(args.database), Path(args.uploads), Path(args.output))
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if manifest.get("warnings"):
        print("WARNINGS: " + ", ".join(manifest["warnings"]), file=sys.stderr)
    print(json.dumps({
        "status": "success",
        "backup_id": manifest["backup_id"],
        "backup_path": manifest["backup_path"],
        "manifest_path": manifest["manifest_path"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
