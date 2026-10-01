#!/usr/bin/env python3
import argparse
import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

spec = importlib.util.spec_from_file_location("lexibridge_file_storage_migration_app", BACKEND / "app.py")
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)


def migrate_document(document, apply=False, move=False):
    if getattr(document, "storage_key", ""):
        return "skipped"
    legacy_path = Path(appmod.UPLOAD_FOLDER) / document.saved_filename
    if not legacy_path.exists():
        return "missing"
    if not apply:
        return "dry_run"
    meta = appmod.storage_service().save_file(
        str(legacy_path),
        purpose="uploaded_document",
        owner_user_id=document.owner_user_id,
        course_id=document.course_id,
        document_id=document.id,
        original_filename=document.saved_filename or document.filename,
    )
    obj = appmod.create_storage_object_from_metadata(meta, visibility=appmod.visibility_for_scope(document.scope_type))
    document.storage_object_id = obj.id
    document.storage_backend = meta["storage_backend"]
    document.storage_key = meta["storage_key"]
    document.content_type = meta["content_type"]
    document.size_bytes = meta["size_bytes"]
    document.sha256 = meta["sha256"]
    document.file_sha256 = meta["sha256"]
    if move:
        legacy_path.unlink(missing_ok=True)
    return "migrated"


def migrate_formula(block, apply=False, move=False):
    if getattr(block, "image_storage_key", ""):
        return "skipped"
    if not block.image_path or not Path(block.image_path).exists():
        return "missing"
    if not apply:
        return "dry_run"
    meta = appmod.storage_service().save_file(
        block.image_path,
        purpose="derived_formula_image",
        owner_user_id=block.owner_user_id,
        course_id=block.course_id,
        document_id=block.document_id,
        original_filename=Path(block.image_path).name,
    )
    obj = appmod.create_storage_object_from_metadata(meta, visibility=appmod.visibility_for_scope(block.scope_type))
    block.image_storage_object_id = obj.id
    block.image_storage_key = meta["storage_key"]
    block.image_content_type = meta["content_type"]
    block.image_sha256 = meta["sha256"]
    if move:
        Path(block.image_path).unlink(missing_ok=True)
    return "migrated"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--move", action="store_true")
    args = parser.parse_args(argv)
    apply = bool(args.apply)
    summary = {"documents": {}, "formula_blocks": {}}
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        for document in appmod.Document.query.all():
            status = migrate_document(document, apply=apply, move=args.move)
            summary["documents"][status] = summary["documents"].get(status, 0) + 1
        for block in appmod.FormulaBlock.query.all():
            status = migrate_formula(block, apply=apply, move=args.move)
            summary["formula_blocks"][status] = summary["formula_blocks"].get(status, 0) + 1
        if apply:
            appmod.db.session.commit()
    print(("Storage migration apply" if apply else "Storage migration dry-run") + f": {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
