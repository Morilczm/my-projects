from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_running_legacy_job_is_not_reclaimed_by_isolated_claimers(app_module):
    with app_module.app.app_context():
        now = app_module.current_time_text()
        run = app_module.AlignmentRun(
            triggered_by=1,
            provider="mock-rule-v1",
            model_name="mock-rule-v1:v1",
            status="running",
            started_at="2026-07-01 00:00:00",
        )
        app_module.db.session.add(run)
        app_module.db.session.flush()
        running = app_module.BackgroundJob(
            job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE,
            status="running",
            priority=1,
            created_by=1,
            alignment_run_id=run.id,
            input_json="{}",
            result_json="{}",
            attempt_count=1,
            max_attempts=3,
            locked_by="stopped-legacy-worker",
            locked_at="2026-07-01 00:00:00",
            heartbeat_at="",
            lease_expires_at="",
            created_at=now,
            updated_at=now,
        )
        queued = app_module.BackgroundJob(
            job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE,
            status="queued",
            priority=-10000,
            created_by=1,
            input_json="{}",
            result_json="{}",
            attempt_count=0,
            max_attempts=3,
            created_at=now,
            updated_at=now,
        )
        app_module.db.session.add_all([running, queued])
        app_module.db.session.commit()
        job_id = running.id
        queued_job_id = queued.id
        run_id = run.id

        try:
            claimed = app_module.claim_next_legacy_alignment_job("replacement-legacy-worker")
            assert claimed.id == queued_job_id
            app_module.db.session.expire_all()
            stored_job = app_module.db.session.get(app_module.BackgroundJob, job_id)
            stored_run = app_module.db.session.get(app_module.AlignmentRun, run_id)
            assert stored_job.status == "running"
            assert stored_job.locked_by == "stopped-legacy-worker"
            assert stored_job.attempt_count == 1
            assert stored_run.status == "running"
        finally:
            app_module.BackgroundJobEvent.query.filter(
                app_module.BackgroundJobEvent.job_id.in_([job_id, queued_job_id])
            ).delete(
                synchronize_session=False
            )
            app_module.db.session.delete(app_module.db.session.get(app_module.BackgroundJob, job_id))
            app_module.db.session.delete(
                app_module.db.session.get(app_module.BackgroundJob, queued_job_id)
            )
            app_module.db.session.delete(app_module.db.session.get(app_module.AlignmentRun, run_id))
            app_module.db.session.commit()


def test_shutdown_plan_selects_bounded_drain_then_safe_failure_with_rollback():
    plan = (ROOT / "docs" / "legacy_running_job_shutdown_plan.md").read_text(
        encoding="utf-8"
    )
    normalized_plan = " ".join(plan.split())
    for expected in (
        "Recommended Disposition",
        "bounded drain",
        "safe failure",
        "Do not migrate",
        "Do not blindly requeue",
        "Rollback",
        "queued = 0",
        "running = 0",
        "retrying = 0",
    ):
        assert expected in normalized_plan
