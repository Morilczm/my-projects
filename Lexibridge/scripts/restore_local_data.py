#!/usr/bin/env python3
"""Restore a local LexiBridge backup into a target directory."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path


def restore_backup(backup, target, force=False):
    backup = Path(backup).expanduser().resolve()
    target = Path(target).expanduser().resolve()
    if not backup.exists():
        raise FileNotFoundError(f"Backup not found: {backup}")
    if target.exists() and any(target.iterdir()) and not force:
        raise FileExistsError(f"Target is not empty: {target}. Use --force to overwrite.")
    if target.exists() and force:
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup) as zipf:
        if "backup_manifest.json" not in zipf.namelist():
            raise ValueError("backup_manifest.json missing")
        manifest = json.loads(zipf.read("backup_manifest.json").decode("utf-8"))
        zipf.extractall(target)
    db_files = list((target / "database").glob("*")) if (target / "database").exists() else []
    return {
        "target": str(target),
        "database_files": [str(path) for path in db_files],
        "manifest": manifest,
    }


def main():
    parser = argparse.ArgumentParser(description="Restore LexiBridge AI local backup.")
    parser.add_argument("--backup", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = restore_backup(args.backup, args.target, args.force)
    print("Restore completed:")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
