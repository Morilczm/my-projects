from dataclasses import replace

import pytest

from formal_document_alignment_retry_support import (
    claim,
    cleanup_retry_state,
    logical_counts,
    run_claimed_with_retryable_verification,
    start_http_run,
)
from services.formal_background_job_execution import complete_formal_background_job
from services.document_alignment_processing_orchestrator import (
    ProcessDocumentAlignmentWorkflowResult,
)
from services.document_alignment_worker_handler import (
    run_claimed_formal_document_alignment_job,
)


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_retry_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_retry_state(app_module)


def test_third_retryable_failure_exhausts_budget_after_root_failure_is_persisted(
    client,
    app_module,
    teacher_token,
):
    with app_module.app.app_context():
        _, run_uid, job_uid = start_http_run(client, app_module, teacher_token, key="exhaustion")

        first_lease = claim(app_module, "exhaust-worker-a", expected_job_uid=job_uid)
        first = run_claimed_with_retryable_verification(app_module, first_lease, complete_first=1)
        second_lease = claim(app_module, "exhaust-worker-b", expected_job_uid=job_uid)
        second = run_claimed_with_retryable_verification(app_module, second_lease)
        third_lease = claim(app_module, "exhaust-worker-c", expected_job_uid=job_uid)
        third = run_claimed_with_retryable_verification(app_module, third_lease)

        app_module.db.session.expire_all()
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()
        counts = logical_counts(app_module, run_uid)

        assert first.outcome == second.outcome == "requeued"
        assert third.outcome == "retry_exhausted"
        assert run.status == "failed"
        assert run.stage == "terminal"
        assert job.status == "failed"
        assert job.attempt_count == 3
        assert job.execution_attempt == 3
        assert counts["needs_review"] == 1
        assert counts["failed_audits"] == 1
        assert complete_formal_background_job(
            third_lease,
            app_module._formal_job_execution_dependencies(),
        ).outcome == "terminal_immutable"
        assert job.locked_by == ""
        assert job.lease_token == ""


def test_unknown_processing_outcome_fails_root_before_job_and_consumes_one_failure(
    client,
    app_module,
    teacher_token,
):
    with app_module.app.app_context():
        _, run_uid, job_uid = start_http_run(client, app_module, teacher_token, key="unknown-outcome")
        lease = claim(app_module, "unknown-outcome-worker", expected_job_uid=job_uid)
        dependencies = app_module._formal_worker_handler_dependencies(lease)
        dependencies = replace(
            dependencies,
            processing=replace(
                dependencies.processing,
                execute=lambda command: ProcessDocumentAlignmentWorkflowResult(
                    outcome="unsupported_processing_outcome",
                    workflow_run_uid=run_uid,
                    job_uid=job_uid,
                    run_status="processing",
                    run_stage="verification",
                    retryable=True,
                    error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
                    error_message="Safe unsupported result.",
                ),
            ),
        )

        result = run_claimed_formal_document_alignment_job(lease, dependencies)
        app_module.db.session.expire_all()
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one()

        assert result.outcome == "failed"
        assert run.status == "failed"
        assert run.stage == "terminal"
        assert run.error_code == "DOCUMENT_ALIGNMENT_PROCESSING_OUTCOME_INVALID"
        assert job.status == "failed"
        assert job.error_code == "DOCUMENT_ALIGNMENT_PROCESSING_OUTCOME_INVALID"
        assert job.attempt_count == 1
        assert app_module.AuditRecord.query.filter_by(
            target_uid=run_uid,
            event_type="document_alignment_failed",
        ).count() == 1
        assert complete_formal_background_job(
            lease,
            app_module._formal_job_execution_dependencies(),
        ).outcome == "terminal_immutable"
        assert job.locked_by == ""
        assert job.lease_token == ""
