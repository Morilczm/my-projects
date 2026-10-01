#!/usr/bin/env python3
"""Export a KB version manifest."""

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
    parser.add_argument("--kb-version-id", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        version = appmod.db.session.get(appmod.KnowledgeBaseVersion, args.kb_version_id)
        if version is None:
            print("KB version not found", file=sys.stderr)
            return 1
        manifest = appmod.build_kb_version_manifest(version)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"KB manifest exported: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
