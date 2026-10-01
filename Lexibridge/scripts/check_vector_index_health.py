#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app, db, ensure_schema_columns, vector_index_health  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-version-id", type=int)
    parser.add_argument("--vector-index-backend", default=None)
    args = parser.parse_args(argv)
    with app.app_context():
        db.create_all()
        ensure_schema_columns()
        result = vector_index_health(args.kb_version_id, vector_backend_name=args.vector_index_backend)
        print("Vector Index Health:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
