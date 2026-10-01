#!/usr/bin/env python3
"""Check local KB health."""

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
    parser.add_argument("--course-id", type=int)
    parser.add_argument("--kb-version-id", type=int)
    args = parser.parse_args(argv)
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        health = appmod.run_knowledge_health_check(course_id=args.course_id, kb_version_id=args.kb_version_id)
        print(f"Knowledge Health: {health['status']}")
        print(json.dumps(health, ensure_ascii=False, indent=2))
    return 0 if health["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
