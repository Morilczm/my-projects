#!/usr/bin/env python3
"""Run local retrieval regression against EvaluationItem cases."""

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
        result = appmod.run_retrieval_regression_for_course(args.course_id, args.kb_version_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"completed", "failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
