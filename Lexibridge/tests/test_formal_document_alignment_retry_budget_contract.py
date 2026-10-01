from dataclasses import replace
from datetime import datetime, timedelta

from services.document_alignment_processing_orchestrator import (
    ProcessDocumentAlignmentWorkflowResult,
)
from services.document_alignment_worker_handler import run_claimed_formal_document_alignment_job
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_REQUEUES_V1,
)
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
    complete_formal_background_job,
    heartbeat_formal_background_job,
    requeue_formal_background_job,
)
from test_formal_background_job_execution import _formal_job
from test_document_alignment_worker_result_mapping import (
    _dependencies as worker_dependencies,
    _lease as worker_lease,
    _processing as worker_processing,
)


NOW = datetime(2026, 7, 19, 8, 0, 0)


def _dependencies(app_module, now=NOW, token="retry-budget-token"):
    return FormalBackgroundJobExecutionDependencies(
        session=app_module.db.session,
        job_model=app_module.BackgroundJob,
        current_time_factory=lambda: now,
        lease_token_factory=lambda: token,
    )


def test_v1_retry_budget_constants_express_three_counted_failures_and_two_requeues():
    assert FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1 == 3
    assert FORMAL_DOCUMENT_ALIGNMENT_MAX_REQUEUES_V1 == 2
    assert FORMAL_DOCUMENT_ALIGNMENT_MAX_REQUEUES_V1 == FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1 - 1


def test_claim_heartbeat_requeue_next_claim_and_complete_use_separate_counters(app_module):
    with app_module.app.app_context():
        app_module.BackgroundJob.query.filter_by(job_type="formal_document_alignment_workflow_v1").delete()
        job = _formal_job(app_module, max_attempts=FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1)
        app_module.db.session.add(job)
        app_module.db.session.commit()

        first = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease
        heartbeat = heartbeat_formal_background_job(
            first,
            _dependencies(app_module, NOW + timedelta(seconds=1)),
        )
        requeued = requeue_formal_background_job(
            first,
            _dependencies(app_module, NOW + timedelta(seconds=2)),
            "DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
            "Safe retry.",
        )
        second = claim_next_formal_background_job(
            "worker-b",
            _dependencies(app_module, NOW + timedelta(seconds=3), "second-token"),
        ).lease
        completed = complete_formal_background_job(
            second,
            _dependencies(app_module, NOW + timedelta(seconds=4), "unused"),
        )
        app_module.db.session.expire_all()
        stored = app_module.BackgroundJob.query.filter_by(job_uid=first.job_uid).one()

        assert first.execution_attempt == 1
        assert heartbeat.outcome == "accepted"
        assert requeued.outcome == "accepted"
        assert second.execution_attempt == 2
        assert completed.outcome == "accepted"
        assert stored.attempt_count == 1
        assert stored.execution_attempt == 2
        assert stored.max_attempts == 3
        app_module.db.session.delete(stored)
        app_module.db.session.commit()


def test_unknown_processing_outcome_cannot_requeue_only_because_retryable_is_true():
    calls = []
    result = run_claimed_formal_document_alignment_job(
        worker_lease(),
        worker_dependencies(
            worker_processing("invalid_run_state", retryable=True),
            run_status="failed",
            run_stage="terminal",
            calls=calls,
        ),
    )

    assert result.outcome == "failed"
    assert result.failed is True
    assert result.retryable is False
    assert calls == ["validate", "heartbeat", "process", "finalize_failure", "fail"]


def test_retry_error_sanitizes_secret_and_keeps_session_reusable(app_module):
    sentinel = "LEXIBRIDGE_SENTINEL_SECRET_9C5F2"
    with app_module.app.app_context():
        app_module.BackgroundJob.query.filter_by(job_type="formal_document_alignment_workflow_v1").delete()
        job = _formal_job(app_module, max_attempts=FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1)
        app_module.db.session.add(job)
        app_module.db.session.commit()
        lease = claim_next_formal_background_job("secret-worker", _dependencies(app_module)).lease

        result = requeue_formal_background_job(
            lease,
            _dependencies(app_module, NOW + timedelta(seconds=1)),
            "DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
            f"Authorization: Bearer {sentinel}",
        )
        app_module.db.session.expire_all()
        stored = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()

        assert result.outcome == "accepted"
        assert sentinel not in result.error_message
        assert sentinel not in stored.error_message
        assert app_module.BackgroundJob.query.count() >= 1
        app_module.db.session.delete(stored)
        app_module.db.session.commit()
