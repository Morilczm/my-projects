from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from services.document_alignment_processing_orchestrator import (
    OUTCOME_ALREADY_TERMINAL,
    OUTCOME_BLOCKED,
    OUTCOME_COMPLETED_WITH_WARNINGS,
    OUTCOME_FAILED as ORCHESTRATOR_OUTCOME_FAILED,
    OUTCOME_LEASE_EXPIRED,
    OUTCOME_PERSISTENCE_ERROR as ORCHESTRATOR_OUTCOME_PERSISTENCE_ERROR,
    OUTCOME_READY_FOR_REVIEW,
    OUTCOME_RETRYABLE_INTERRUPTION,
    OUTCOME_STALE_ATTEMPT,
    ProcessDocumentAlignmentWorkflowResult,
)
from services.document_alignment_worker_handler import (
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_INVALID_JOB_PAYLOAD,
    OUTCOME_OWNERSHIP_LOST,
    OUTCOME_PERSISTENCE_ERROR,
    OUTCOME_REQUEUED,
    OUTCOME_RETRY_EXHAUSTED,
    DocumentAlignmentWorkerHandlerDependencies,
    FormalDocumentAlignmentJobSnapshot,
    FormalDocumentAlignmentRunSnapshot,
    FormalJobOwnershipCollaborator,
    FormalProcessingCollaborator,
    run_claimed_formal_document_alignment_job,
)
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_FAILED,
    ROOT_STATUS_PROCESSING,
    ROOT_STATUS_READY_FOR_REVIEW,
    WORKFLOW_VERSION_V1,
)
from services.formal_background_job_execution import (
    LEASE_OUTCOME_ACCEPTED,
    LEASE_OUTCOME_LEASE_EXPIRED,
    LEASE_OUTCOME_PERSISTENCE_ERROR,
    LEASE_OUTCOME_STALE_ATTEMPT,
    LEASE_OUTCOME_TERMINAL_IMMUTABLE,
    FormalJobExecutionLease,
    FormalJobLeaseOperationResult,
)


NOW = datetime(2026, 7, 19, 1, 30, 0)


def _lease():
    return FormalJobExecutionLease(
        job_uid="mapping-job",
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        worker_id="mapping-worker",
        execution_attempt=2,
        lease_token="mapping-token",
        claimed_at=NOW,
        heartbeat_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
        status="running",
    )


def _operation(outcome=LEASE_OUTCOME_ACCEPTED, status="running", code="", message=""):
    return FormalJobLeaseOperationResult(
        outcome=outcome,
        job_uid="mapping-job",
        execution_attempt=2,
        status=status,
        error_code=code,
        error_message=message,
    )


def _processing(outcome, run_status=ROOT_STATUS_PROCESSING, run_stage="verification", retryable=False):
    return ProcessDocumentAlignmentWorkflowResult(
        outcome=outcome,
        workflow_run_uid="mapping-run",
        job_uid="mapping-job",
        run_status=run_status,
        run_stage=run_stage,
        retryable=retryable,
        error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED" if retryable else "",
        error_message="Safe processing interruption." if retryable else "",
    )


def _dependencies(
    processing,
    *,
    run_status=ROOT_STATUS_PROCESSING,
    run_stage="verification",
    run_error_code="",
    attempt_count=0,
    max_attempts=3,
    payload=None,
    operation_overrides=None,
    calls=None,
):
    calls = calls if calls is not None else []
    operation_overrides = operation_overrides or {}

    def operation(name, default_status):
        def execute(*args):
            calls.append(name)
            return operation_overrides.get(name, _operation(status=default_status))

        return execute

    return DocumentAlignmentWorkerHandlerDependencies(
        load_job=lambda _: FormalDocumentAlignmentJobSnapshot(
            job_uid="mapping-job",
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            status="running",
            input_payload=payload or {
                "workflow_run_uid": "mapping-run",
                "workflow_version": WORKFLOW_VERSION_V1,
            },
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        ),
        load_run=lambda _: FormalDocumentAlignmentRunSnapshot(
            run_uid="mapping-run",
            workflow_version=WORKFLOW_VERSION_V1,
            status=run_status,
            stage=run_stage,
            error_code=run_error_code,
        ),
        ownership=FormalJobOwnershipCollaborator(
            validate=operation("validate", "running"),
            heartbeat=operation("heartbeat", "running"),
            complete=operation("complete", "completed"),
            requeue=operation("requeue", "retrying"),
            fail=operation("fail", "failed"),
        ),
        processing=FormalProcessingCollaborator(
            execute=lambda _: calls.append("process") or processing,
            finalize_failure=lambda *args: calls.append("finalize_failure") or _processing(
                ORCHESTRATOR_OUTCOME_FAILED,
                ROOT_STATUS_FAILED,
                ROOT_STAGE_TERMINAL,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("orchestrator_outcome", "root_status"),
    (
        (OUTCOME_READY_FOR_REVIEW, ROOT_STATUS_READY_FOR_REVIEW),
        (OUTCOME_COMPLETED_WITH_WARNINGS, ROOT_STATUS_COMPLETED_WITH_WARNINGS),
        (OUTCOME_BLOCKED, ROOT_STATUS_BLOCKED),
        (ORCHESTRATOR_OUTCOME_FAILED, ROOT_STATUS_FAILED),
        (OUTCOME_ALREADY_TERMINAL, ROOT_STATUS_READY_FOR_REVIEW),
    ),
)
def test_business_terminal_root_completes_transport_job(orchestrator_outcome, root_status):
    calls = []
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            _processing(orchestrator_outcome, root_status, ROOT_STAGE_TERMINAL),
            run_status=root_status,
            run_stage=ROOT_STAGE_TERMINAL,
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_COMPLETED
    assert result.completed is True
    assert calls == ["validate", "heartbeat", "process", "complete"]


@pytest.mark.parametrize(
    "orchestrator_outcome",
    (OUTCOME_RETRYABLE_INTERRUPTION, ORCHESTRATOR_OUTCOME_PERSISTENCE_ERROR),
)
def test_retryable_processing_result_requeues_once(orchestrator_outcome):
    calls = []
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            _processing(orchestrator_outcome, retryable=True),
            attempt_count=0,
            max_attempts=3,
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_REQUEUED
    assert result.requeued is True
    assert result.retryable is True
    assert calls == ["validate", "heartbeat", "process", "requeue"]


def test_retry_exhaustion_finalizes_root_before_failing_job():
    calls = []
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            _processing(OUTCOME_RETRYABLE_INTERRUPTION, retryable=True),
            attempt_count=2,
            max_attempts=3,
            run_status=ROOT_STATUS_FAILED,
            run_stage=ROOT_STAGE_TERMINAL,
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_RETRY_EXHAUSTED
    assert result.retry_exhausted is True
    assert result.failed is True
    assert calls == ["validate", "heartbeat", "process", "finalize_failure", "fail"]


def test_reclaimed_attempt_finishes_retry_exhausted_job_as_failed_not_completed():
    calls = []
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            _processing(OUTCOME_ALREADY_TERMINAL, ROOT_STATUS_FAILED, ROOT_STAGE_TERMINAL),
            run_status=ROOT_STATUS_FAILED,
            run_stage=ROOT_STAGE_TERMINAL,
            run_error_code="DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_RETRY_EXHAUSTED
    assert result.failed is True
    assert result.completed is False
    assert calls == ["validate", "heartbeat", "process", "fail"]


def test_invalid_payload_fails_job_without_running_orchestrator():
    calls = []
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            _processing(OUTCOME_READY_FOR_REVIEW),
            payload={"workflow_run_uid": "mapping-run", "credential": "secret"},
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_INVALID_JOB_PAYLOAD
    assert result.failed is True
    assert calls == ["validate", "heartbeat", "fail"]


@pytest.mark.parametrize(
    ("orchestrator_outcome", "expected_code"),
    (
        (OUTCOME_STALE_ATTEMPT, "DOCUMENT_ALIGNMENT_STALE_EXECUTION_ATTEMPT"),
        (OUTCOME_LEASE_EXPIRED, "DOCUMENT_ALIGNMENT_LEASE_EXPIRED"),
    ),
)
def test_orchestrator_ownership_loss_does_not_finalize_job(orchestrator_outcome, expected_code):
    calls = []
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            ProcessDocumentAlignmentWorkflowResult(
                outcome=orchestrator_outcome,
                workflow_run_uid="mapping-run",
                job_uid="mapping-job",
                error_code=expected_code,
                error_message="Ownership ended.",
            ),
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_OWNERSHIP_LOST
    assert result.ownership_lost is True
    assert calls == ["validate", "heartbeat", "process"]


@pytest.mark.parametrize("operation_name", ("complete", "requeue", "fail"))
def test_job_finalization_cas_failure_never_uses_old_lease_again(operation_name):
    calls = []
    if operation_name == "complete":
        processing = _processing(OUTCOME_READY_FOR_REVIEW, ROOT_STATUS_READY_FOR_REVIEW, ROOT_STAGE_TERMINAL)
        run_status = ROOT_STATUS_READY_FOR_REVIEW
        run_stage = ROOT_STAGE_TERMINAL
        attempts = (0, 3)
    elif operation_name == "requeue":
        processing = _processing(OUTCOME_RETRYABLE_INTERRUPTION, retryable=True)
        run_status = ROOT_STATUS_PROCESSING
        run_stage = "verification"
        attempts = (0, 3)
    else:
        processing = _processing(OUTCOME_READY_FOR_REVIEW)
        run_status = ROOT_STATUS_PROCESSING
        run_stage = "verification"
        attempts = (0, 3)
    payload = None if operation_name != "fail" else {"invalid": True}
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            processing,
            run_status=run_status,
            run_stage=run_stage,
            attempt_count=attempts[0],
            max_attempts=attempts[1],
            payload=payload,
            operation_overrides={
                operation_name: _operation(
                    LEASE_OUTCOME_STALE_ATTEMPT,
                    "running",
                    "FORMAL_JOB_STALE_EXECUTION_ATTEMPT",
                    "Old attempt cannot finalize.",
                )
            },
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_OWNERSHIP_LOST
    assert calls.count(operation_name) == 1


@pytest.mark.parametrize(
    "ownership_outcome",
    (LEASE_OUTCOME_LEASE_EXPIRED, LEASE_OUTCOME_STALE_ATTEMPT, LEASE_OUTCOME_TERMINAL_IMMUTABLE),
)
def test_entry_ownership_rejection_performs_no_processing_or_finalization(ownership_outcome):
    calls = []
    result = run_claimed_formal_document_alignment_job(
        _lease(),
        _dependencies(
            _processing(OUTCOME_READY_FOR_REVIEW),
            operation_overrides={"validate": _operation(ownership_outcome, "running")},
            calls=calls,
        ),
    )
    assert result.outcome == OUTCOME_OWNERSHIP_LOST
    assert calls == ["validate"]
