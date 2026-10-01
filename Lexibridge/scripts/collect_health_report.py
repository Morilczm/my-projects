#!/usr/bin/env python3
"""Collect a local health report for deployment-readiness review."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def load_app():
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("lexibridge_health_app", BACKEND / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def dir_size(path):
    path = Path(path).expanduser()
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def sqlite_path_from_uri(uri):
    if not uri.startswith("sqlite:///"):
        return None
    return Path(uri.replace("sqlite:///", "", 1)).expanduser()


def mb(value):
    return round(value / (1024 * 1024), 4)


def collect_report():
    appmod = load_app()
    with appmod.app.app_context():
        db_uri = appmod.app.config["SQLALCHEMY_DATABASE_URI"]
        db_path = sqlite_path_from_uri(db_uri)
        latest_eval = appmod.EvaluationRun.query.order_by(appmod.EvaluationRun.id.desc()).first()
        upload_dir = Path(appmod.UPLOAD_FOLDER)
        derived_dir = upload_dir / "derived"
        jobs = {
            "queued": appmod.BackgroundJob.query.filter_by(status="queued").count(),
            "running": appmod.BackgroundJob.query.filter_by(status="running").count(),
            "failed": appmod.BackgroundJob.query.filter_by(status="failed").count(),
            "completed": appmod.BackgroundJob.query.filter_by(status="completed").count(),
        }
        report = {
            "status": "ok",
            "database": {
                "type": "sqlite" if db_uri.startswith("sqlite") else db_uri.split(":", 1)[0],
                "path": str(db_path) if db_path else "",
                "size_mb": mb(db_path.stat().st_size) if db_path and db_path.exists() else 0,
            },
            "counts": {
                "users": appmod.User.query.count(),
                "courses": appmod.Course.query.count(),
                "documents": appmod.Document.query.count(),
                "knowledge_chunks": appmod.KnowledgeChunk.query.count(),
                "terminology_cards": appmod.TerminologyCard.query.count(),
                "background_jobs": appmod.BackgroundJob.query.count(),
                "evaluation_runs": appmod.EvaluationRun.query.count(),
            },
            "jobs": jobs,
            "failures": {
                "ocr_failed": appmod.Document.query.filter(appmod.Document.ocr_status.in_(["ocr_failed", "ocr_unavailable"])).count(),
                "formula_ocr_failed": appmod.FormulaBlock.query.filter(appmod.FormulaBlock.status.in_(["formula_ocr_failed", "needs_formula_ocr_engine"])).count(),
                "ai_provider_failed": appmod.SystemLog.query.filter(appmod.SystemLog.module.like("%ai%"), appmod.SystemLog.level == "error").count(),
            },
            "quality": {
                "auto_approved": appmod.TerminologyCard.query.filter_by(status="auto_approved").count(),
                "pending_quality_control": appmod.TerminologyCard.query.filter_by(status="pending_quality_control").count(),
                "needs_more_evidence": appmod.TerminologyCard.query.filter_by(status="needs_more_evidence").count(),
            },
            "evaluation": {
                "latest_run_id": latest_eval.id if latest_eval else None,
                "alignment_accuracy": latest_eval.alignment_accuracy if latest_eval else None,
                "no_evidence_forced_alignment_rate": latest_eval.no_evidence_forced_alignment_rate if latest_eval else None,
            },
            "storage": {
                "uploads_size_mb": mb(dir_size(upload_dir)),
                "derived_uploads_size_mb": mb(dir_size(derived_dir)),
            },
        }
    return report


def main():
    print(json.dumps(collect_report(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
