#!/usr/bin/env python3
"""Create a local KnowledgeBaseVersion."""

from __future__ import annotations

import argparse
import importlib.util
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
    parser.add_argument("--course-id", type=int)
    parser.add_argument("--scope-type", default="course", choices=["course", "personal", "global"])
    parser.add_argument("--owner-user-id", type=int)
    parser.add_argument("--description", default="CLI-created KB version")
    args = parser.parse_args(argv)
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        version = appmod.create_knowledge_base_version(
            course_id=args.course_id,
            scope_type=args.scope_type,
            owner_user_id=args.owner_user_id,
            description=args.description,
            created_by=0,
        )
        appmod.db.session.commit()
        print(f"KnowledgeBaseVersion ID: {version.id}")
        print(f"name: {version.version_name}")
        print(f"status: {version.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
