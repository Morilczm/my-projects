#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-non-empty", action="store_true")
    parser.add_argument("--upsert", action="store_true")
    args = parser.parse_args(argv)
    input_dir = Path(args.input)
    metadata_path = input_dir / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit("metadata.json missing from export directory")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not args.database_url.startswith("postgresql"):
        raise SystemExit("--database-url must be postgresql://...")
    if not args.apply:
        print("PostgreSQL import dry-run")
        print(json.dumps({
            "input": str(input_dir),
            "target": args.database_url.split("@")[-1],
            "table_counts": metadata.get("table_counts", {}),
            "apply": False,
        }, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit("Apply mode is intentionally not implemented in Local MVP. Use Alembic + audited importer in staging.")


if __name__ == "__main__":
    raise SystemExit(main())
