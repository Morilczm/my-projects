#!/usr/bin/env python3
"""Rebuild a course KB into a candidate version."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("lexibridge_app", BACKEND / "app.py")
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        documents = appmod.Document.query.filter_by(course_id=args.course_id, scope_type="course").all()
        if not args.apply:
            print(json.dumps({"dry_run": True, "course_id": args.course_id, "document_count": len(documents)}, ensure_ascii=False, indent=2))
            return 0
        parent = appmod.get_published_kb_version(course_id=args.course_id)
        version = appmod.create_knowledge_base_version(args.course_id, "course", None, "rebuild candidate", parent_version_id=parent.id if parent else None)
        reports = []
        for document in documents:
            reports.append(appmod.index_document_into_kb_version(document.id, version.id))
        health = appmod.run_knowledge_health_check(course_id=args.course_id, kb_version_id=version.id)
        version.quality_gate_status = "pass" if health["status"] != "FAIL" else "fail"
        appmod.db.session.commit()
        print(json.dumps({"dry_run": False, "version": appmod.serialize_kb_version(version), "reports": reports, "health": health}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
