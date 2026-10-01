#!/usr/bin/env python3
"""Export AI call summary as JSON or CSV."""

from __future__ import annotations

import argparse
import csv
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

from services.ai_cost import summarize_ai_calls  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export AI call summary.")
    parser.add_argument("--output", help="Optional output path. .csv writes rows; otherwise JSON summary.")
    args = parser.parse_args(argv)
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        logs = appmod.AICallLog.query.order_by(appmod.AICallLog.id.desc()).all()
        summary = summarize_ai_calls(logs)
        if args.output and args.output.endswith(".csv"):
            with open(args.output, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "id", "task_type", "provider_name", "provider_mode", "model_name",
                    "prompt_key", "prompt_version", "status", "error_code",
                    "input_token_count", "output_token_count", "estimated_cost", "created_at",
                ])
                writer.writeheader()
                for log in logs:
                    writer.writerow(appmod.serialize_ai_call_log(log))
            print(f"AI call CSV exported: {args.output}")
            return 0
        payload = {"summary": summary, "recent": [appmod.serialize_ai_call_log(log) for log in logs[:50]]}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"AI call summary exported: {args.output}")
        else:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
