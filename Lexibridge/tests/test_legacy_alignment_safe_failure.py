import json

import pytest


def _running_pair(app_module, suffix):
    run = app_module.AlignmentRun(
        triggered_by=1,
        provider="mock",
        model_name="mock",
        status="running",
        started_at="2026-01-01 00:00:00",
    )
    app_module.db.session.add(run)
    app_module.db.session.flush()
    job = app_module.BackgroundJob(
        job_uid=f"safe-failure-{suffix}",
        job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE,
        status="running",
        priority=1,
        created_by=1,
        alignment_run_id=run.id,
        input_json='{"secret":"must-not-appear"}',
        result_json="{}",
        attempt_count=1,
        max_attempts=3,
        locked_by="stopped-worker",
        locked_at="2026-01-01 00:00:00",
        started_at="2026-01-01 00:00:00",
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )
    app_module.db.session.add(job)
    app_module.db.session.commit()
    return run, job


def _cleanup(app_module, run_id, job_id):
    job = app_module.db.session.get(app_module.BackgroundJob, job_id)
    target_uid = str(job.job_uid or job_id) if job is not None else str(job_id)
    app_module.AuditRecord.query.filter_by(
        event_type="legacy_alignment_shutdown_safe_failure",
        target_uid=target_uid,
    ).delete(synchronize_session=False)
    app_module.BackgroundJobEvent.query.filter_by(job_id=job_id).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter_by(id=job_id).delete(synchronize_session=False)
    app_module.AlignmentRun.query.filter_by(id=run_id).delete(synchronize_session=False)
    app_module.db.session.commit()


def test_safe_failure_defaults_to_dry_run_and_performs_no_writes(app_module):
    service = app_module.legacy_alignment_freeze_service
    with app_module.app.app_context():
        run, job = _running_pair(app_module, "dry-run")
        run_id, job_id = run.id, job.id
        before_audits = app_module.AuditRecord.query.count()
        before_events = app_module.BackgroundJobEvent.query.filter_by(job_id=job_id).count()
        try:
            result = service.safe_fail_running_job(
                app_module.db.session,
                app_module.legacy_alignment_runtime_models(),
                job_id=job_id,
                expected_locked_by="stopped-worker",
                stale_before="2026-01-02 00:00:00",
                actor_name="pytest-operator",
                now_fn=app_module.current_time_text,
            )
            assert result["status"] == "dry_run"
            app_module.db.session.expire_all()
            assert app_module.db.session.get(app_module.BackgroundJob, job_id).status == "running"
            assert app_module.db.session.get(app_module.AlignmentRun, run_id).status == "running"
            assert app_module.AuditRecord.query.count() == before_audits
            assert app_module.BackgroundJobEvent.query.filter_by(job_id=job_id).count() == before_events
        finally:
            _cleanup(app_module, run_id, job_id)


def test_safe_failure_atomically_fails_job_and_run_with_safe_audit(app_module):
    service = app_module.legacy_alignment_freeze_service
    with app_module.app.app_context():
        run, job = _running_pair(app_module, "apply")
        run_id, job_id = run.id, job.id
        try:
            result = service.safe_fail_running_job(
                app_module.db.session,
                app_module.legacy_alignment_runtime_models(),
                job_id=job_id,
                expected_locked_by="stopped-worker",
                stale_before="2026-01-02 00:00:00",
                actor_name="pytest-operator",
                now_fn=app_module.current_time_text,
                apply=True,
            )
            assert result["status"] == "applied"
            stored_job = app_module.db.session.get(app_module.BackgroundJob, job_id)
            stored_run = app_module.db.session.get(app_module.AlignmentRun, run_id)
            assert stored_job.status == "failed"
            assert stored_run.status == "failed"
            assert stored_job.error_code == "LEGACY_ALIGNMENT_SHUTDOWN_SAFE_FAILURE"
            event = app_module.BackgroundJobEvent.query.filter_by(
                job_id=job_id,
                event_type="shutdown_safe_failure",
            ).one()
            audit = app_module.AuditRecord.query.filter_by(
                event_type="legacy_alignment_shutdown_safe_failure",
                target_uid=job.job_uid,
            ).one()
            rendered = json.dumps(
                {
                    "event": event.message,
                    "audit": audit.input_payload,
                    "before": audit.before_snapshot,
                    "after": audit.after_snapshot,
                }
            )
            assert "must-not-appear" not in rendered
            assert "secret" not in rendered
        finally:
            _cleanup(app_module, run_id, job_id)


def test_safe_failure_rejects_owner_or_stale_cutoff_mismatch(app_module):
    service = app_module.legacy_alignment_freeze_service
    with app_module.app.app_context():
        run, job = _running_pair(app_module, "fence")
        run_id, job_id = run.id, job.id
        try:
            with pytest.raises(service.LegacyAlignmentSafeFailureError, match="owner fence"):
                service.safe_fail_running_job(
                    app_module.db.session,
                    app_module.legacy_alignment_runtime_models(),
                    job_id=job_id,
                    expected_locked_by="other-worker",
                    stale_before="2026-01-02 00:00:00",
                    actor_name="pytest-operator",
                    now_fn=app_module.current_time_text,
                    apply=True,
                )
            with pytest.raises(service.LegacyAlignmentSafeFailureError, match="newer than"):
                service.safe_fail_running_job(
                    app_module.db.session,
                    app_module.legacy_alignment_runtime_models(),
                    job_id=job_id,
                    expected_locked_by="stopped-worker",
                    stale_before="2025-12-31 00:00:00",
                    actor_name="pytest-operator",
                    now_fn=app_module.current_time_text,
                    apply=True,
                )
            app_module.db.session.expire_all()
            assert app_module.db.session.get(app_module.BackgroundJob, job_id).status == "running"
            assert app_module.db.session.get(app_module.AlignmentRun, run_id).status == "running"
        finally:
            app_module.db.session.rollback()
            _cleanup(app_module, run_id, job_id)
