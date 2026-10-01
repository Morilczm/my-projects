#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app, db, ensure_schema_columns, build_vector_index_for_kb_version  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-version-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--embedding-provider", default=None)
    parser.add_argument("--vector-index-backend", default=None)
    args = parser.parse_args(argv)
    with app.app_context():
        db.create_all()
        ensure_schema_columns()
        result = build_vector_index_for_kb_version(
            args.kb_version_id,
            apply=bool(args.apply and not args.dry_run),
            embedding_provider_name=args.embedding_provider,
            vector_backend_name=args.vector_index_backend,
        )
        print("Vector Index Build:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
