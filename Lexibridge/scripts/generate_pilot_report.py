#!/usr/bin/env python3
"""Generate a privacy-preserving LexiBridge AI pilot report."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def load_app():
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("lexibridge_pilot_report_app", BACKEND / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def generate(course_id=None, output=None):
    appmod = load_app()
    with appmod.app.app_context():
        course = appmod.db.session.get(appmod.Course, int(course_id)) if course_id else None
        feedbacks = appmod.Feedback.query.filter_by(course_id=course.id).all() if course else appmod.Feedback.query.all()
        cards = appmod.TerminologyCard.query.filter_by(course_id=course.id).all() if course else appmod.TerminologyCard.query.all()
        jobs = appmod.BackgroundJob.query.filter_by(course_id=course.id).all() if course else appmod.BackgroundJob.query.all()
        backlog = appmod.IterationBacklogItem.query.filter_by(course_id=course.id).all() if course else appmod.IterationBacklogItem.query.all()
        latest_eval = appmod.EvaluationRun.query.order_by(appmod.EvaluationRun.id.desc()).first()
        usage_summary = {
            "documents": appmod.Document.query.filter_by(course_id=course.id).count() if course else appmod.Document.query.count(),
            "evaluation_runs": appmod.EvaluationRun.query.count(),
            "active_students": len({fb.user_id for fb in feedbacks if fb.user_role == "student"}),
            "active_teachers": len({fb.user_id for fb in feedbacks if fb.user_role == "teacher"}),
            "searches": appmod.UsageRecord.query.filter_by(action_type="knowledge_search").count(),
            "favorites": appmod.StudentTermRecord.query.filter_by(is_favorite=True).count(),
            "mastered": appmod.StudentTermRecord.query.filter_by(is_mastered=True).count(),
            "exports": appmod.UsageRecord.query.filter_by(action_type="pdf_export").count(),
        }
        markdown = appmod.generate_pilot_report_markdown(course, feedbacks, cards, jobs, latest_eval, backlog, usage_summary)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    return markdown


def main():
    parser = argparse.ArgumentParser(description="Generate a LexiBridge AI pilot report.")
    parser.add_argument("--course-id", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generate(args.course_id, args.output)
    print(f"Pilot report generated: {args.output}")


if __name__ == "__main__":
    main()
