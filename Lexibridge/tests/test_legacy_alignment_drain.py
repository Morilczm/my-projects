from copy import deepcopy


def _job(app_module, status, index):
    now = app_module.current_time_text()
    return app_module.BackgroundJob(
        job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE,
        status=status,
        priority=index,
        created_by=1,
        input_json='{"private":"not returned"}',
        result_json='{"private":"not returned"}',
        error_message="not returned",
        attempt_count=index,
        max_attempts=3,
        locked_by=f"worker-{index}" if status == "running" else "",
        locked_at="2026-01-01 00:00:00" if status == "running" else "",
        created_at=now,
        updated_at=now,
    )


def test_queue_snapshot_reports_required_states_without_writes_or_private_payload(app_module):
    with app_module.app.app_context():
        baseline = app_module.legacy_alignment_queue_snapshot()
        jobs = [_job(app_module, status, index) for index, status in enumerate(
            ("queued", "running", "retrying", "failed"),
            start=1,
        )]
        app_module.db.session.add_all(jobs)
        app_module.db.session.commit()
        job_ids = [job.id for job in jobs]
        before = {
            job.id: {
                "status": job.status,
                "locked_by": job.locked_by,
                "input_json": job.input_json,
                "result_json": job.result_json,
                "error_message": job.error_message,
            }
            for job in jobs
        }
        try:
            snapshot = app_module.legacy_alignment_queue_snapshot()
            for status in ("queued", "running", "retrying", "failed"):
                assert snapshot["counts"][status] == baseline["counts"][status] + 1
            assert snapshot["active_total"] == baseline["active_total"] + 3
            rendered = str(snapshot)
            assert "not returned" not in rendered
            assert "private" not in rendered
            app_module.db.session.expire_all()
            after = {
                job_id: {
                    "status": app_module.db.session.get(app_module.BackgroundJob, job_id).status,
                    "locked_by": app_module.db.session.get(app_module.BackgroundJob, job_id).locked_by,
                    "input_json": app_module.db.session.get(app_module.BackgroundJob, job_id).input_json,
                    "result_json": app_module.db.session.get(app_module.BackgroundJob, job_id).result_json,
                    "error_message": app_module.db.session.get(app_module.BackgroundJob, job_id).error_message,
                }
                for job_id in job_ids
            }
            assert after == deepcopy(before)
            assert not app_module.db.session.new
            assert not app_module.db.session.dirty
            assert not app_module.db.session.deleted
        finally:
            app_module.BackgroundJobEvent.query.filter(
                app_module.BackgroundJobEvent.job_id.in_(job_ids)
            ).delete(synchronize_session=False)
            app_module.BackgroundJob.query.filter(
                app_module.BackgroundJob.id.in_(job_ids)
            ).delete(synchronize_session=False)
            app_module.db.session.commit()
