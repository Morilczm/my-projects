#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app, db, ensure_schema_columns, run_retrieval_experiment  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", type=int)
    parser.add_argument("--evaluation-set-id", type=int)
    parser.add_argument("--kb-version-id", type=int)
    args = parser.parse_args(argv)
    with app.app_context():
        db.create_all()
        ensure_schema_columns()
        result = run_retrieval_experiment(
            course_id=args.course_id,
            evaluation_set_id=args.evaluation_set_id,
            kb_version_id=args.kb_version_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
