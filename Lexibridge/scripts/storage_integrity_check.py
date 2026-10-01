#!/usr/bin/env python3
import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.storage import compute_sha256

spec = importlib.util.spec_from_file_location("lexibridge_storage_integrity_app", BACKEND / "app.py")
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)


def check_object(obj):
    service = appmod.storage_service()
    if not obj.storage_key or not service.exists(obj.storage_key):
        return "missing"
    path = service.absolute_path(obj.storage_key)
    if obj.size_bytes and Path(path).stat().st_size != obj.size_bytes:
        return "size_mismatch"
    if obj.sha256 and compute_sha256(path) != obj.sha256:
        return "hash_mismatch"
    if obj.visibility == "private" and not obj.owner_user_id:
        return "privacy_warning"
    if obj.visibility == "course" and not obj.course_id:
        return "course_warning"
    return "ok"


def main():
    summary = {"ok": 0, "missing": 0, "size_mismatch": 0, "hash_mismatch": 0, "privacy_warning": 0, "course_warning": 0, "orphan_files": 0}
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        for obj in appmod.StorageObject.query.all():
            status = check_object(obj)
            summary[status] = summary.get(status, 0) + 1
        root = Path(os.environ.get("LOCAL_STORAGE_ROOT") or appmod.UPLOAD_FOLDER)
        referenced = {obj.storage_key for obj in appmod.StorageObject.query.all() if obj.storage_key}
        storage_root = root / "storage"
        if storage_root.exists():
            for path in storage_root.rglob("*"):
                if path.is_file():
                    key = str(path.relative_to(root))
                    if key not in referenced:
                        summary["orphan_files"] += 1
    status = "PASS" if all(summary[key] == 0 for key in ["missing", "size_mismatch", "hash_mismatch"]) else "WARN"
    print(f"Storage Integrity: {status}")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
