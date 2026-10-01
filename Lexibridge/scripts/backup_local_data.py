#!/usr/bin/env python3
"""Create a local backup zip for SQLite data and uploads."""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sqlite_path_from_env(database_url=None):
    database_url = database_url or os.environ.get("DATABASE_URL", "")
    if database_url.startswith("sqlite:///"):
        return Path(database_url.replace("sqlite:///", "", 1)).expanduser()
    return Path.home() / "LexiBridge-AI-data" / "lexibridge.db"


def file_count_and_size(path):
    path = Path(path)
    if not path.exists():
        return 0, 0
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def add_tree(zipf, source, arc_prefix):
    source = Path(source)
    if not source.exists():
        return
    for item in source.rglob("*"):
        if item.is_file():
            parts = item.parts
            if any(part in {".git", "__pycache__", ".pytest_cache", "venv", ".venv", ".venv-macos"} for part in parts):
                continue
            zipf.write(item, Path(arc_prefix) / item.relative_to(source))


def create_backup(output, database=None, uploads=None, include_env=False, include_demo_data=False):
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    database_path = Path(database).expanduser() if database else sqlite_path_from_env()
    uploads_path = Path(uploads).expanduser() if uploads else Path(os.environ.get("UPLOAD_FOLDER", ROOT / "backend" / "uploads"))
    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {database_path}")
    upload_count, upload_size = file_count_and_size(uploads_path)
    manifest = {
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "app_version": "Local MVP v0.8",
        "database_path": str(database_path),
        "upload_file_count": upload_count,
        "upload_total_size": upload_size,
        "included_env": bool(include_env),
        "included_demo_data": bool(include_demo_data),
    }
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zipf.write(database_path, Path("database") / database_path.name)
        add_tree(zipf, uploads_path, "uploads")
        if include_demo_data:
            add_tree(zipf, ROOT / "demo_data", "demo_data")
        if include_env and (ROOT / ".env").exists():
            print("WARNING: including .env may expose secrets.")
            zipf.write(ROOT / ".env", ".env")
    return output, manifest


def main():
    parser = argparse.ArgumentParser(description="Back up local LexiBridge AI data.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--database")
    parser.add_argument("--uploads")
    parser.add_argument("--include-env", action="store_true")
    parser.add_argument("--include-demo-data", action="store_true")
    args = parser.parse_args()
    path, manifest = create_backup(args.output, args.database, args.uploads, args.include_env, args.include_demo_data)
    print(f"Backup created: {path}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
