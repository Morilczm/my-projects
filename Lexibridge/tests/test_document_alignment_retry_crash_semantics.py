import pytest

from formal_document_alignment_retry_support import (
    claim,
    cleanup_retry_state,
    logical_counts,
    process_until_first_item_then_crash,
    reclaim_after_expiry,
    start_http_run,
)
from services.document_alignment_worker_handler import run_claimed_formal_document_alignment_job
from services.formal_background_job_execution import complete_formal_background_job


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_retry_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_retry_state(app_module)


def test_claim_crash_and_partial_processing_crash_do_not_consume_retry_budget(
    client,
    app_module,
    teacher_token,
):
    with app_module.app.app_context():
        _, run_uid, job_uid = start_http_run(client, app_module, teacher_token, key="crash")
        first_lease = claim(app_module, "crash-worker-a", expected_job_uid=job_uid)
        second_lease = reclaim_after_expiry(app_module, first_lease, "crash-worker-b")
        app_module.db.session.expire_all()
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()
        assert second_lease.execution_attempt == 2
        assert job.attempt_count == 0
        assert complete_formal_background_job(
            first_lease,
            app_module._formal_job_execution_dependencies(),
        ).outcome == "stale_attempt"

        interrupted = process_until_first_item_then_crash(app_module, second_lease)
        before = logical_counts(app_module, run_uid)
        app_module.db.session.expire_all()
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()
        assert interrupted.outcome == "retryable_interruption"
        assert job.status == "running"
        assert job.attempt_count == 0
        assert before["needs_review"] == 1

        third_lease = reclaim_after_expiry(app_module, second_lease, "crash-worker-c")
        completed = run_claimed_formal_document_alignment_job(
            third_lease,
            app_module._formal_worker_handler_dependencies(third_lease),
        )
        after = logical_counts(app_module, run_uid)
        app_module.db.session.expire_all()
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()

        assert completed.outcome == "completed"
        assert third_lease.execution_attempt == 3
        assert job.attempt_count == 0
        assert after["needs_review"] == 2
        assert after["preflights"] == after["verifications"] == after["usage"] == 0
