#!/usr/bin/env python3
"""Export a privacy-preserving feedback summary CSV."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def load_app():
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("lexibridge_feedback_export_app", BACKEND / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


FIELDS = [
    "feedback_id",
    "feedback_type",
    "severity",
    "status",
    "course_id",
    "terminology_card_id",
    "english_term",
    "chinese_term",
    "classification",
    "root_cause",
    "resolution_action",
    "created_at",
    "resolved_at",
]


def export_feedback(course_id=None, output="feedback_summary.csv"):
    appmod = load_app()
    with appmod.app.app_context():
        query = appmod.Feedback.query
        if course_id:
            query = query.filter_by(course_id=int(course_id))
        rows = query.order_by(appmod.Feedback.id.asc()).all()
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for feedback in rows:
                writer.writerow({
                    "feedback_id": feedback.id,
                    "feedback_type": feedback.feedback_type,
                    "severity": feedback.severity,
                    "status": feedback.status,
                    "course_id": feedback.course_id,
                    "terminology_card_id": feedback.terminology_card_id or feedback.term_id,
                    "english_term": feedback.english_term,
                    "chinese_term": feedback.chinese_term,
                    "classification": feedback.classification,
                    "root_cause": feedback.root_cause,
                    "resolution_action": feedback.resolution_action,
                    "created_at": feedback.created_at,
                    "resolved_at": feedback.resolved_at,
                })
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Export LexiBridge AI feedback summary CSV.")
    parser.add_argument("--course-id", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    path = export_feedback(args.course_id, args.output)
    print(f"Feedback summary exported: {path}")


if __name__ == "__main__":
    main()
