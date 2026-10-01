#!/usr/bin/env python3
"""Run an isolated non-production legacy freeze, drain, and restore rehearsal."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def load_isolated_app(temp_dir):
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(temp_dir) / 'rehearsal.db'}"
    os.environ["UPLOAD_FOLDER"] = str(Path(temp_dir) / "uploads")
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ["AI_PROVIDER"] = "none"
    os.environ["ALLOW_MOCK_AI"] = "true"
    os.environ["LEGACY_ALIGNMENT_RUNTIME_STATE"] = "active"
    os.environ["LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED"] = "true"
    spec = importlib.util.spec_from_file_location(
        "lexibridge_legacy_shutdown_rehearsal",
        BACKEND / "app.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_job(app_module, user, course, *, term, status="queued", owner=""):
    metadata = app_module.default_legacy_alignment_provider_metadata()
    run = app_module.AlignmentRun(
        course_id=course.id,
        triggered_by=user.id,
        provider=metadata["provider"],
        model_name=metadata["model_name"],
        ai_provider=metadata["provider"],
        ai_provider_mode=metadata.get("provider_mode", ""),
        ai_model=metadata["model_name"],
        prompt_key="term_alignment",
        prompt_version="v1",
        retrieval_version=app_module.RETRIEVAL_VERSION,
        term_count=1,
        status="running" if status == "running" else "queued",
        started_at="2026-01-01 00:00:00" if status == "running" else "",
    )
    app_module.db.session.add(run)
    app_module.db.session.flush()
    job = app_module.create_background_job(
        app_module.LEGACY_ALIGNMENT_JOB_TYPE,
        user,
        course_id=course.id,
        alignment_run_id=run.id,
        scope_type="course",
        input_data={
            "english_term": term,
            "courseware_sentence": f"{term} is used only in the isolated shutdown rehearsal.",
            "scope_type": "course",
            "course_id": course.id,
            "provider": metadata["provider"],
            "provider_mode": metadata.get("provider_mode", ""),
            "model_name": metadata["model_name"],
        },
    )
    if status == "running":
        job.status = "running"
        job.attempt_count = 1
        job.locked_by = owner
        job.locked_at = "2026-01-01 00:00:00"
        job.started_at = "2026-01-01 00:00:00"
    app_module.db.session.commit()
    return run, job


def run_rehearsal(app_module):
    service = app_module.legacy_alignment_freeze_service
    with app_module.app.app_context():
        app_module.db.create_all()
        app_module.ensure_schema_columns()
        user = app_module.User(
            username="legacy_rehearsal_operator",
            email="legacy-rehearsal@lexibridge.local",
            password_hash="non-login-rehearsal-account",
            role="admin",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(user)
        app_module.db.session.flush()
        course = app_module.Course(
            name="Legacy Shutdown Rehearsal",
            course_code="LEGACY-REHEARSAL",
            teacher_id=user.id,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(course)
        app_module.db.session.commit()

        queued_run, queued_job = _create_legacy_job(
            app_module,
            user,
            course,
            term="Queued Legacy Rehearsal Term",
        )
        stale_run, stale_job = _create_legacy_job(
            app_module,
            user,
            course,
            term="Stale Legacy Rehearsal Term",
            status="running",
            owner="rehearsal-stopped-worker",
        )
        token = app_module.create_auth_token(user)
        client = app_module.app.test_client()

        app_module.LEGACY_ALIGNMENT_RUNTIME_STATE = service.RUNTIME_STATE_FREEZE
        app_module.LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED = False
        before_frozen_http = {
            "runs": app_module.AlignmentRun.query.count(),
            "jobs": app_module.BackgroundJob.query.filter_by(
                job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE
            ).count(),
        }
        frozen_http = client.post(
            "/api/alignment/run",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "english_term": "Frozen Legacy Rehearsal Term",
                "course_id": course.id,
                "scope_type": "course",
            },
        )
        after_frozen_http = {
            "runs": app_module.AlignmentRun.query.count(),
            "jobs": app_module.BackgroundJob.query.filter_by(
                job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE
            ).count(),
        }
        creation_blocked = False
        try:
            app_module.create_background_job(
                app_module.LEGACY_ALIGNMENT_JOB_TYPE,
                user,
                course_id=course.id,
                input_data={"english_term": "must-not-be-created"},
            )
        except service.LegacyAlignmentAdmissionError:
            app_module.db.session.rollback()
            creation_blocked = True

        frozen_snapshot = app_module.legacy_alignment_queue_snapshot()
        frozen_claim = app_module.claim_next_legacy_alignment_job("rehearsal-frozen-worker")

        safe_failure = service.safe_fail_running_job(
            app_module.db.session,
            app_module.legacy_alignment_runtime_models(),
            job_id=stale_job.id,
            expected_locked_by="rehearsal-stopped-worker",
            stale_before="2026-01-02 00:00:00",
            actor_name="legacy-rehearsal-operator",
            now_fn=app_module.current_time_text,
            apply=True,
        )

        app_module.LEGACY_ALIGNMENT_RUNTIME_STATE = service.RUNTIME_STATE_DRAINING
        drained_job = app_module.run_legacy_alignment_worker_once("rehearsal-drain-worker")
        drained_snapshot = app_module.legacy_alignment_queue_snapshot()
        drained_run_count = app_module.AlignmentRun.query.count()

        app_module.LEGACY_ALIGNMENT_RUNTIME_STATE = service.RUNTIME_STATE_DISABLED
        disabled_claim = app_module.claim_next_legacy_alignment_job("rehearsal-disabled-worker")

        app_module.LEGACY_ALIGNMENT_RUNTIME_STATE = service.RUNTIME_STATE_ACTIVE
        app_module.LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED = True
        restored = app_module.legacy_alignment_creation_is_allowed()
        rollback_http = client.post(
            "/api/alignment/run",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "english_term": "Restored Legacy Rehearsal Term",
                "course_id": course.id,
                "scope_type": "course",
            },
        )
        formal_contract = {
            "workflow_version": app_module.WORKFLOW_VERSION_V1,
            "job_type": app_module.FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        }

        checks = {
            "freeze_blocked_creation": creation_blocked,
            "freeze_http_returned_migration_response": frozen_http.status_code == 503
            and frozen_http.get_json().get("error_code") == "LEGACY_ALIGNMENT_ADMISSION_DISABLED",
            "freeze_http_created_no_legacy_records": before_frozen_http == after_frozen_http,
            "freeze_paused_legacy_claim": frozen_claim is None,
            "freeze_observed_queued": frozen_snapshot["counts"]["queued"] == 1,
            "freeze_observed_running": frozen_snapshot["counts"]["running"] == 1,
            "safe_failure_applied": safe_failure["status"] == "applied",
            "drain_completed_queued_job": bool(
                drained_job and drained_job.id == queued_job.id and drained_job.status == "completed"
            ),
            "drain_active_total_zero": drained_snapshot["active_total"] == 0,
            "disabled_paused_legacy_claim": disabled_claim is None,
            "active_mode_restored": restored,
            "rollback_http_creation_restored": rollback_http.status_code == 200,
            "formal_contract_unchanged": formal_contract
            == {
                "workflow_version": "formal-document-alignment-v1",
                "job_type": "formal_document_alignment_workflow_v1",
            },
            "safe_failure_audited": app_module.AuditRecord.query.filter_by(
                event_type="legacy_alignment_shutdown_safe_failure"
            ).count()
            == 1,
            "safe_failure_event_recorded": app_module.BackgroundJobEvent.query.filter_by(
                job_id=stale_job.id,
                event_type="shutdown_safe_failure",
            ).count()
            == 1,
            "queued_run_reused": app_module.AlignmentRun.query.filter_by(id=queued_run.id).count() == 1,
            "drain_did_not_create_replacement_run": drained_run_count == 2,
            "stale_run_failed": app_module.db.session.get(app_module.AlignmentRun, stale_run.id).status
            == "failed",
        }
        return {
            "verdict": "PASS" if all(checks.values()) else "FAIL",
            "environment": "isolated_temporary_sqlite",
            "checks": checks,
            "freeze_snapshot": frozen_snapshot,
            "drained_snapshot": drained_snapshot,
            "formal_contract": formal_contract,
            "rollback_http_status": rollback_http.status_code,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="lexibridge-legacy-rehearsal-") as temp_dir:
        result = run_rehearsal(load_isolated_app(temp_dir))
    rendered = json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True)
    Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
