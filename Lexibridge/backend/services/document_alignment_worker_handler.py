"""Formal BackgroundJob handler for one already-claimed document workflow lease."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

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
    ProcessDocumentAlignmentWorkflowCommand,
)
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_FAILED,
    ROOT_STATUS_READY_FOR_REVIEW,
    WORKFLOW_VERSION_V1,
)
from services.formal_background_job_execution import (
    LEASE_OUTCOME_ACCEPTED,
    LEASE_OUTCOME_PERSISTENCE_ERROR,
    FormalJobExecutionLease,
)


OUTCOME_COMPLETED = "completed"
OUTCOME_REQUEUED = "requeued"
OUTCOME_FAILED = "failed"
OUTCOME_NO_JOB_AVAILABLE = "no_job_available"
OUTCOME_OWNERSHIP_LOST = "ownership_lost"
OUTCOME_INVALID_JOB_PAYLOAD = "invalid_job_payload"
OUTCOME_INVALID_WORKFLOW_VERSION = "invalid_workflow_version"
OUTCOME_RETRY_EXHAUSTED = "retry_exhausted"
OUTCOME_PERSISTENCE_ERROR = "persistence_error"

ERROR_PAYLOAD_INVALID = "FORMAL_DOCUMENT_JOB_PAYLOAD_INVALID"
ERROR_JOB_MISMATCH = "DOCUMENT_ALIGNMENT_JOB_MISMATCH"
ERROR_WORKFLOW_VERSION_MISMATCH = "DOCUMENT_ALIGNMENT_WORKFLOW_VERSION_MISMATCH"
ERROR_JOB_FINALIZATION_FAILED = "DOCUMENT_ALIGNMENT_JOB_FINALIZATION_FAILED"
ERROR_PROCESSING_OUTCOME_INVALID = "DOCUMENT_ALIGNMENT_PROCESSING_OUTCOME_INVALID"
ERROR_INTERNAL_WORKER = "DOCUMENT_ALIGNMENT_INTERNAL_WORKER_FAILED"

_TERMINAL_ROOT_STATUSES = frozenset({
    ROOT_STATUS_READY_FOR_REVIEW,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_FAILED,
})
_TERMINAL_ORCHESTRATOR_OUTCOMES = frozenset({
    OUTCOME_READY_FOR_REVIEW,
    OUTCOME_COMPLETED_WITH_WARNINGS,
    OUTCOME_BLOCKED,
    ORCHESTRATOR_OUTCOME_FAILED,
    OUTCOME_ALREADY_TERMINAL,
})
_RETRYABLE_ORCHESTRATOR_OUTCOMES = frozenset({
    OUTCOME_RETRYABLE_INTERRUPTION,
    ORCHESTRATOR_OUTCOME_PERSISTENCE_ERROR,
})
_OWNERSHIP_LOSS_ORCHESTRATOR_OUTCOMES = frozenset({
    OUTCOME_STALE_ATTEMPT,
    OUTCOME_LEASE_EXPIRED,
})
_SAFE_MARKERS = (
    "LEXIBRIDGE_SENTINEL_SECRET",
    "Authorization:",
    "Cookie:",
    "Bearer ",
    "sk-",
)


def _required_text(value: Any, field_name: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _safe_error(value: Any, fallback: str = "Formal document alignment worker failed safely.") -> str:
    text = str(value or "").strip()
    if not text or any(marker in text for marker in _SAFE_MARKERS):
        return fallback if value else ""
    return text[:500]


@dataclass(frozen=True)
class FormalDocumentAlignmentJobPayload:
    workflow_run_uid: str
    workflow_version: str

    def __post_init__(self):
        object.__setattr__(
            self,
            "workflow_run_uid",
            _required_text(self.workflow_run_uid, "workflow_run_uid", 64),
        )
        object.__setattr__(
            self,
            "workflow_version",
            _required_text(self.workflow_version, "workflow_version", 80),
        )


@dataclass(frozen=True)
class FormalDocumentAlignmentJobSnapshot:
    job_uid: str
    job_type: str
    status: str
    input_payload: Any = field(repr=False)
    attempt_count: int = 0
    max_attempts: int = FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1


@dataclass(frozen=True)
class FormalDocumentAlignmentRunSnapshot:
    run_uid: str
    workflow_version: str
    status: str
    stage: str
    error_code: str = ""


@dataclass(frozen=True)
class FormalJobOwnershipCollaborator:
    validate: Callable[[FormalJobExecutionLease], Any]
    heartbeat: Callable[[FormalJobExecutionLease], Any]
    complete: Callable[[FormalJobExecutionLease], Any]
    requeue: Callable[[FormalJobExecutionLease, str, str], Any]
    fail: Callable[[FormalJobExecutionLease, str, str], Any]


@dataclass(frozen=True)
class FormalProcessingCollaborator:
    execute: Callable[[ProcessDocumentAlignmentWorkflowCommand], Any]
    finalize_failure: Callable[[ProcessDocumentAlignmentWorkflowCommand, str, str], Any]


@dataclass(frozen=True)
class DocumentAlignmentWorkerHandlerDependencies:
    load_job: Callable[[str], FormalDocumentAlignmentJobSnapshot | None]
    load_run: Callable[[str], FormalDocumentAlignmentRunSnapshot | None]
    ownership: FormalJobOwnershipCollaborator
    processing: FormalProcessingCollaborator


@dataclass(frozen=True)
class RunFormalDocumentAlignmentJobResult:
    outcome: str
    job_uid: str = ""
    workflow_run_uid: str = ""
    job_status: str = ""
    run_status: str = ""
    run_stage: str = ""
    execution_attempt: int = 0
    orchestrator_outcome: str = ""
    requeued: bool = False
    completed: bool = False
    failed: bool = False
    retry_exhausted: bool = False
    ownership_lost: bool = False
    retryable: bool = False
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self):
        object.__setattr__(self, "outcome", _required_text(self.outcome, "outcome", 80))
        object.__setattr__(self, "error_code", str(self.error_code or "")[:120])
        object.__setattr__(self, "error_message", _safe_error(self.error_message))


def load_formal_document_alignment_job_payload(value: Any) -> FormalDocumentAlignmentJobPayload:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{ERROR_PAYLOAD_INVALID}: payload must be a JSON object.") from exc
    if not isinstance(value, dict) or set(value) != {"workflow_run_uid", "workflow_version"}:
        raise ValueError(f"{ERROR_PAYLOAD_INVALID}: payload fields are invalid.")
    try:
        return FormalDocumentAlignmentJobPayload(
            workflow_run_uid=value.get("workflow_run_uid"),
            workflow_version=value.get("workflow_version"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{ERROR_PAYLOAD_INVALID}: payload values are invalid.") from exc


def _result(lease: FormalJobExecutionLease, outcome: str, **values):
    return RunFormalDocumentAlignmentJobResult(
        outcome=outcome,
        job_uid=lease.job_uid,
        execution_attempt=lease.execution_attempt,
        **values,
    )


def _ownership_result(lease, operation, *, workflow_run_uid="", orchestrator_outcome=""):
    if getattr(operation, "outcome", "") == LEASE_OUTCOME_ACCEPTED:
        return None
    persistence_error = getattr(operation, "outcome", "") == LEASE_OUTCOME_PERSISTENCE_ERROR
    return _result(
        lease,
        OUTCOME_PERSISTENCE_ERROR if persistence_error else OUTCOME_OWNERSHIP_LOST,
        workflow_run_uid=workflow_run_uid,
        job_status=str(getattr(operation, "status", "") or ""),
        orchestrator_outcome=orchestrator_outcome,
        ownership_lost=not persistence_error,
        retryable=persistence_error,
        error_code=str(getattr(operation, "error_code", "") or ERROR_JOB_FINALIZATION_FAILED),
        error_message=str(getattr(operation, "error_message", "") or "Formal job ownership was lost."),
    )


def _fail_invalid_job(lease, dependencies, *, outcome, code, message, workflow_run_uid="", run=None):
    failed = dependencies.ownership.fail(lease, code, message)
    ownership_failure = _ownership_result(
        lease,
        failed,
        workflow_run_uid=workflow_run_uid,
    )
    if ownership_failure is not None:
        return ownership_failure
    return _result(
        lease,
        outcome,
        workflow_run_uid=workflow_run_uid,
        job_status="failed",
        run_status=run.status if run else "",
        run_stage=run.stage if run else "",
        failed=True,
        error_code=code,
        error_message=message,
    )


def run_claimed_formal_document_alignment_job(
    lease: FormalJobExecutionLease,
    dependencies: DocumentAlignmentWorkerHandlerDependencies,
) -> RunFormalDocumentAlignmentJobResult:
    ownership_failure = _ownership_result(lease, dependencies.ownership.validate(lease))
    if ownership_failure is not None:
        return ownership_failure
    ownership_failure = _ownership_result(lease, dependencies.ownership.heartbeat(lease))
    if ownership_failure is not None:
        return ownership_failure

    job = dependencies.load_job(lease.job_uid)
    if job is None or job.job_uid != lease.job_uid or job.job_type != FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE:
        return _fail_invalid_job(
            lease,
            dependencies,
            outcome=OUTCOME_INVALID_JOB_PAYLOAD,
            code=ERROR_JOB_MISMATCH,
            message="Formal job identity does not match the claimed lease.",
        )
    try:
        payload = load_formal_document_alignment_job_payload(job.input_payload)
    except ValueError:
        return _fail_invalid_job(
            lease,
            dependencies,
            outcome=OUTCOME_INVALID_JOB_PAYLOAD,
            code=ERROR_PAYLOAD_INVALID,
            message="Formal document alignment job payload is invalid.",
        )
    run = dependencies.load_run(payload.workflow_run_uid)
    if run is None or run.run_uid != payload.workflow_run_uid:
        return _fail_invalid_job(
            lease,
            dependencies,
            outcome=OUTCOME_INVALID_JOB_PAYLOAD,
            workflow_run_uid=payload.workflow_run_uid,
            code=ERROR_JOB_MISMATCH,
            message="Formal job does not match an available workflow run.",
        )
    if payload.workflow_version != WORKFLOW_VERSION_V1 or payload.workflow_version != run.workflow_version:
        return _fail_invalid_job(
            lease,
            dependencies,
            outcome=OUTCOME_INVALID_WORKFLOW_VERSION,
            workflow_run_uid=payload.workflow_run_uid,
            run=run,
            code=ERROR_WORKFLOW_VERSION_MISMATCH,
            message="Formal document alignment workflow version does not match.",
        )

    command = ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=payload.workflow_run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )
    processing = dependencies.processing.execute(command)
    if getattr(processing, "outcome", "") in _OWNERSHIP_LOSS_ORCHESTRATOR_OUTCOMES:
        return _result(
            lease,
            OUTCOME_OWNERSHIP_LOST,
            workflow_run_uid=payload.workflow_run_uid,
            job_status=job.status,
            run_status=str(getattr(processing, "run_status", "") or run.status),
            run_stage=str(getattr(processing, "run_stage", "") or run.stage),
            orchestrator_outcome=processing.outcome,
            ownership_lost=True,
            error_code=str(getattr(processing, "error_code", "") or ERROR_JOB_FINALIZATION_FAILED),
            error_message=str(getattr(processing, "error_message", "") or "Formal processing ownership ended."),
        )
    current_run = dependencies.load_run(payload.workflow_run_uid)
    if (
        getattr(processing, "outcome", "") == OUTCOME_ALREADY_TERMINAL
        and current_run is not None
        and current_run.status == ROOT_STATUS_FAILED
        and current_run.stage == ROOT_STAGE_TERMINAL
        and current_run.error_code == "DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED"
    ):
        failed = dependencies.ownership.fail(
            lease,
            "DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
            "Formal document alignment worker retry budget was exhausted.",
        )
        ownership_failure = _ownership_result(
            lease,
            failed,
            workflow_run_uid=payload.workflow_run_uid,
            orchestrator_outcome=processing.outcome,
        )
        if ownership_failure is not None:
            return ownership_failure
        return _result(
            lease,
            OUTCOME_RETRY_EXHAUSTED,
            workflow_run_uid=payload.workflow_run_uid,
            job_status="failed",
            run_status=current_run.status,
            run_stage=current_run.stage,
            orchestrator_outcome=processing.outcome,
            failed=True,
            retry_exhausted=True,
            error_code="DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
            error_message="Formal document alignment worker retry budget was exhausted.",
        )
    if (
        getattr(processing, "outcome", "") in _TERMINAL_ORCHESTRATOR_OUTCOMES
        and current_run is not None
        and current_run.status in _TERMINAL_ROOT_STATUSES
        and current_run.stage == ROOT_STAGE_TERMINAL
    ):
        completed = dependencies.ownership.complete(lease)
        ownership_failure = _ownership_result(
            lease,
            completed,
            workflow_run_uid=payload.workflow_run_uid,
            orchestrator_outcome=processing.outcome,
        )
        if ownership_failure is not None:
            return ownership_failure
        return _result(
            lease,
            OUTCOME_COMPLETED,
            workflow_run_uid=payload.workflow_run_uid,
            job_status="completed",
            run_status=current_run.status,
            run_stage=current_run.stage,
            orchestrator_outcome=processing.outcome,
            completed=True,
        )
    if getattr(processing, "outcome", "") in _RETRYABLE_ORCHESTRATOR_OUTCOMES:
        code = str(getattr(processing, "error_code", "") or "DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED")
        message = str(getattr(processing, "error_message", "") or "Formal processing was interrupted safely.")
        retry_exhausted = int(job.attempt_count or 0) + 1 >= max(1, int(job.max_attempts or 1))
        if retry_exhausted:
            finalized = dependencies.processing.finalize_failure(
                command,
                "DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
                "Formal document alignment worker retry budget was exhausted.",
            )
            finalized_run = dependencies.load_run(payload.workflow_run_uid)
            if (
                getattr(finalized, "outcome", "") not in {ORCHESTRATOR_OUTCOME_FAILED, OUTCOME_ALREADY_TERMINAL}
                or finalized_run is None
                or finalized_run.status != ROOT_STATUS_FAILED
                or finalized_run.stage != ROOT_STAGE_TERMINAL
            ):
                return _result(
                    lease,
                    OUTCOME_PERSISTENCE_ERROR,
                    workflow_run_uid=payload.workflow_run_uid,
                    job_status=job.status,
                    run_status=finalized_run.status if finalized_run else "",
                    run_stage=finalized_run.stage if finalized_run else "",
                    orchestrator_outcome=processing.outcome,
                    retryable=True,
                    error_code=ERROR_JOB_FINALIZATION_FAILED,
                    error_message="Retry exhaustion could not safely finalize the workflow run.",
                )
            failed = dependencies.ownership.fail(
                lease,
                "DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
                "Formal document alignment worker retry budget was exhausted.",
            )
            ownership_failure = _ownership_result(
                lease,
                failed,
                workflow_run_uid=payload.workflow_run_uid,
                orchestrator_outcome=processing.outcome,
            )
            if ownership_failure is not None:
                return ownership_failure
            return _result(
                lease,
                OUTCOME_RETRY_EXHAUSTED,
                workflow_run_uid=payload.workflow_run_uid,
                job_status="failed",
                run_status=finalized_run.status,
                run_stage=finalized_run.stage,
                orchestrator_outcome=processing.outcome,
                failed=True,
                retry_exhausted=True,
                error_code="DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
                error_message="Formal document alignment worker retry budget was exhausted.",
            )
        requeued = dependencies.ownership.requeue(lease, code, message)
        ownership_failure = _ownership_result(
            lease,
            requeued,
            workflow_run_uid=payload.workflow_run_uid,
            orchestrator_outcome=processing.outcome,
        )
        if ownership_failure is not None:
            return ownership_failure
        return _result(
            lease,
            OUTCOME_REQUEUED,
            workflow_run_uid=payload.workflow_run_uid,
            job_status="retrying",
            run_status=current_run.status if current_run else run.status,
            run_stage=current_run.stage if current_run else run.stage,
            orchestrator_outcome=processing.outcome,
            requeued=True,
            retryable=True,
            error_code=code,
            error_message=message,
        )
    invalid_message = "Formal workflow returned an unsupported processing outcome."
    finalized = dependencies.processing.finalize_failure(
        command,
        ERROR_PROCESSING_OUTCOME_INVALID,
        invalid_message,
    )
    finalized_run = dependencies.load_run(payload.workflow_run_uid)
    if (
        getattr(finalized, "outcome", "") not in {ORCHESTRATOR_OUTCOME_FAILED, OUTCOME_ALREADY_TERMINAL}
        or finalized_run is None
        or finalized_run.status != ROOT_STATUS_FAILED
        or finalized_run.stage != ROOT_STAGE_TERMINAL
    ):
        return _result(
            lease,
            OUTCOME_PERSISTENCE_ERROR,
            workflow_run_uid=payload.workflow_run_uid,
            job_status=job.status,
            run_status=finalized_run.status if finalized_run else "",
            run_stage=finalized_run.stage if finalized_run else "",
            orchestrator_outcome=str(getattr(processing, "outcome", "") or ""),
            retryable=True,
            error_code=ERROR_JOB_FINALIZATION_FAILED,
            error_message="Unsupported processing outcome could not safely finalize the workflow run.",
        )
    failed = dependencies.ownership.fail(
        lease,
        ERROR_PROCESSING_OUTCOME_INVALID,
        invalid_message,
    )
    ownership_failure = _ownership_result(
        lease,
        failed,
        workflow_run_uid=payload.workflow_run_uid,
        orchestrator_outcome=str(getattr(processing, "outcome", "") or ""),
    )
    if ownership_failure is not None:
        return ownership_failure
    return _result(
        lease,
        OUTCOME_FAILED,
        workflow_run_uid=payload.workflow_run_uid,
        job_status="failed",
        run_status=finalized_run.status,
        run_stage=finalized_run.stage,
        orchestrator_outcome=str(getattr(processing, "outcome", "") or ""),
        failed=True,
        error_code=ERROR_PROCESSING_OUTCOME_INVALID,
        error_message=invalid_message,
    )
