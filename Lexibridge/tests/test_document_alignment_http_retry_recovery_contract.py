import pytest

from formal_document_alignment_retry_support import (
    claim,
    cleanup_retry_state,
    logical_counts,
    run_claimed_with_retryable_verification,
    start_http_run,
)
from services.document_alignment_worker_handler import run_claimed_formal_document_alignment_job
from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_retry_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_retry_state(app_module)


@pytest.mark.parametrize("round_index", range(5))
def test_real_http_admission_retryable_requeue_next_claim_and_resume(
    client,
    app_module,
    teacher_token,
    round_index,
):
    with app_module.app.app_context():
        _, run_uid, job_uid = start_http_run(
            client,
            app_module,
            teacher_token,
            key=f"retry-contract-round-{round_index}",
        )
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()
        assert job.max_attempts == FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1

        first_lease = claim(app_module, "retry-worker-a", expected_job_uid=job_uid)
        first = run_claimed_with_retryable_verification(app_module, first_lease)
        app_module.db.session.expire_all()
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        assert first.outcome == "requeued"
        assert job.status == "retrying"
        assert job.attempt_count == 1
        assert job.execution_attempt == 1
        assert run.status == "processing"

        second_lease = claim(app_module, "retry-worker-b", expected_job_uid=job_uid)
        second = run_claimed_formal_document_alignment_job(
            second_lease,
            app_module._formal_worker_handler_dependencies(second_lease),
        )
        app_module.db.session.expire_all()
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        counts = logical_counts(app_module, run_uid)

        assert second.outcome == "completed"
        assert second_lease.execution_attempt == 2
        assert job.status == "completed"
        assert job.attempt_count == 1
        assert run.status == "ready_for_review"
        assert counts == {
            "items": 2,
            "needs_review": 2,
            "preflights": 0,
            "verifications": 0,
            "usage": 0,
            "failed_audits": 0,
        }
