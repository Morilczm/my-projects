#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app, db, ensure_schema_columns, RetrievalExperimentRun  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    with app.app_context():
        db.create_all()
        ensure_schema_columns()
        run = db.session.get(RetrievalExperimentRun, args.experiment_id)
        if run is None:
            raise SystemExit("Retrieval experiment not found.")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(run.report_markdown or "", encoding="utf-8")
        print(f"Retrieval experiment report exported: {output}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
