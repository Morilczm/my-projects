#!/usr/bin/env python3
"""Verify a LexiBridge pilot backup manifest, hashes, and SQLite integrity."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


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
SECRET_FILE_NAMES = {".env", ".env.local", ".env.production"}
SECRET_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\s+[a-z0-9._-]{12,}|sk-[a-zA-Z0-9]{12,}|cookie)",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(backup: Path) -> dict[str, Any]:
    manifest_path = backup / "backup_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"backup_manifest.json not found in {backup}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def sqlite_integrity(database_path: Path) -> str:
    with sqlite3.connect(database_path) as conn:
        return str(conn.execute("pragma integrity_check").fetchone()[0])


def table_counts(database_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(database_path) as conn:
        existing = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            ).fetchall()
        }
        missing = [name for name in CORE_TABLES if name not in existing]
        if missing:
            raise ValueError(f"missing core tables: {', '.join(missing)}")
        for name in CORE_TABLES:
            counts[name] = int(conn.execute(f'select count(*) from "{name}"').fetchone()[0])
    return counts


def scan_for_secrets(path: Path) -> list[str]:
    findings: list[str] = []
    if path.name in SECRET_FILE_NAMES:
        findings.append(path.relative_to(path.parents[1]).as_posix() if len(path.parents) > 1 else path.name)
        return findings
    if not path.is_file() or path.name == "database.sqlite":
        return findings
    try:
        data = path.read_bytes()[:1024 * 1024]
    except OSError:
        return findings
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return findings
    if SECRET_PATTERN.search(text):
        findings.append(path.name)
    return findings


def verify_backup(backup: Path) -> dict[str, Any]:
    backup = backup.expanduser().resolve()
    manifest = load_manifest(backup)
    if manifest.get("manifest_version") != "pilot-backup-v1":
        raise ValueError("unsupported backup manifest version")

    manifest_text = json.dumps(manifest, ensure_ascii=False)
    if SECRET_PATTERN.search(manifest_text):
        raise ValueError("manifest contains secret-like content")

    database_info = manifest.get("database") or {}
    database_path = backup / str(database_info.get("path") or "database.sqlite")
    if not database_path.exists():
        raise FileNotFoundError("backup database is missing")
    actual_db_hash = sha256_file(database_path)
    if actual_db_hash != database_info.get("sha256"):
        raise ValueError("database sha256 mismatch")
    integrity = sqlite_integrity(database_path)
    if integrity.lower() != "ok":
        raise ValueError(f"sqlite integrity_check failed: {integrity}")

    uploads_info = manifest.get("uploads") or {}
    uploads_root = backup / str(uploads_info.get("path") or "uploads")
    upload_files = uploads_info.get("files") or []
    for item in upload_files:
        relative = Path(str(item.get("relative_path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"invalid upload path in manifest: {relative}")
        target = uploads_root / relative
        if not target.exists():
            raise FileNotFoundError(f"upload file missing: {relative.as_posix()}")
        if sha256_file(target) != item.get("sha256"):
            raise ValueError(f"upload sha256 mismatch: {relative.as_posix()}")

    secret_findings: list[str] = []
    for item in backup.rglob("*"):
        if item.is_file():
            secret_findings.extend(scan_for_secrets(item))
    if secret_findings:
        raise ValueError("secret-like files/content found: " + ", ".join(sorted(set(secret_findings))))

    counts = table_counts(database_path)
    demo_marker_present = False
    with sqlite3.connect(database_path) as conn:
        if "concept_alignment_card" in counts:
            row = conn.execute(
                "select count(*) from concept_alignment_card where course like 'DEMO %'"
            ).fetchone()
            demo_marker_present = bool(row and row[0])

    return {
        "status": "success",
        "backup_id": manifest.get("backup_id"),
        "database_sha256": actual_db_hash,
        "sqlite_integrity": integrity,
        "core_table_counts": counts,
        "uploads_file_count": len(upload_files),
        "demo_marker_present": demo_marker_present,
        "warnings": manifest.get("warnings") or [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a LexiBridge pilot backup.")
    parser.add_argument("--backup", required=True, help="Backup directory containing backup_manifest.json.")
    args = parser.parse_args(argv)
    try:
        result = verify_backup(Path(args.backup))
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
