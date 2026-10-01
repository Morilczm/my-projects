"""Formal document-alignment processing orchestration boundary.

The service is HTTP- and worker-neutral. A future worker owns job claim and
terminal job status; this module only validates an active lease, coordinates
formal workflow collaborators, and returns a typed result.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from services.document_alignment_item_bootstrap import (
    BOOTSTRAP_OUTCOME_CREATED,
    BOOTSTRAP_OUTCOME_LEASE_EXPIRED,
    BOOTSTRAP_OUTCOME_LEASE_NOT_OWNED,
    BOOTSTRAP_OUTCOME_REUSED,
    BOOTSTRAP_OUTCOME_STALE_ATTEMPT,
)
from services.document_alignment_item_preparation import (
    PREPARATION_OUTCOME_CHINESE_CANDIDATE_UNAVAILABLE,
    PREPARATION_OUTCOME_CHUNK_NOT_AVAILABLE,
    PREPARATION_OUTCOME_EVIDENCE_INSUFFICIENT,
    PREPARATION_OUTCOME_PREPARED,
    PREPARATION_OUTCOME_SOURCE_CHANGED,
)
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ITEM_STAGE_EVIDENCE_RETRIEVAL,
    ITEM_STAGE_TERMINAL,
    ITEM_STATUS_BLOCKED,
    ITEM_STATUS_CANDIDATE,
    ITEM_STATUS_DRAFT_CREATED,
    ITEM_STATUS_EVIDENCE_READY,
    ITEM_STATUS_FAILED,
    ITEM_STATUS_NEEDS_REVIEW,
    ITEM_STATUS_VERIFICATION_COMPLETED,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_FAILED,
    ROOT_STATUS_PROCESSING,
    ROOT_STATUS_QUEUED,
    ROOT_STATUS_READY_FOR_REVIEW,
    ROOT_STATUS_VALIDATING,
)
from services.formal_background_job_execution import (
    LEASE_OUTCOME_ACCEPTED,
    LEASE_OUTCOME_LEASE_EXPIRED,
    LEASE_OUTCOME_STALE_ATTEMPT,
)


ROOT_AUDIT_IDENTITY_VERSION = "document-alignment-root-audit-v1"

OUTCOME_READY_FOR_REVIEW = "ready_for_review"
OUTCOME_COMPLETED_WITH_WARNINGS = "completed_with_warnings"
OUTCOME_BLOCKED = "blocked"
OUTCOME_FAILED = "failed"
OUTCOME_ALREADY_TERMINAL = "already_terminal"
OUTCOME_RETRYABLE_INTERRUPTION = "retryable_interruption"
OUTCOME_STALE_ATTEMPT = "stale_attempt"
OUTCOME_LEASE_EXPIRED = "lease_expired"
OUTCOME_INVALID_RUN_STATE = "invalid_run_state"
OUTCOME_SOURCE_CHANGED = "source_changed"
OUTCOME_PERSISTENCE_ERROR = "persistence_error"

_ROOT_ENTRY_STATUSES = frozenset({ROOT_STATUS_QUEUED, ROOT_STATUS_VALIDATING, ROOT_STATUS_PROCESSING})
_ROOT_TERMINAL_STATUSES = frozenset({
    ROOT_STATUS_READY_FOR_REVIEW,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_FAILED,
})
_ITEM_TERMINAL_STATUSES = frozenset({ITEM_STATUS_NEEDS_REVIEW, ITEM_STATUS_BLOCKED, ITEM_STATUS_FAILED})
_ITEM_ADAPTER_STATUSES = frozenset({
    ITEM_STATUS_EVIDENCE_READY,
    ITEM_STATUS_DRAFT_CREATED,
    ITEM_STATUS_VERIFICATION_COMPLETED,
})
_ADAPTER_BUSINESS_OUTCOMES = frozenset({
    "approved_card_protected",
    "insufficient_evidence",
    "chinese_candidate_unavailable",
    "provider_policy_blocked",
    "provider_preflight_blocked",
    "verification_failed",
    "parser_failed",
    "attach_blocked",
})


def _required_text(value: Any, field_name: str, max_length: int = 500) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _safe_error_message(value: Any) -> str:
    text = str(value or "").strip()
    forbidden = (
        "LEXIBRIDGE_SENTINEL_SECRET",
        "Authorization:",
        "Cookie:",
        "Bearer ",
        "sk-",
    )
    if any(marker in text for marker in forbidden):
        return "Document alignment processing failed safely."
    return text[:500]


@dataclass(frozen=True)
class ProcessDocumentAlignmentWorkflowCommand:
    workflow_run_uid: str
    job_uid: str
    worker_id: str
    execution_attempt: int
    lease_token: str = field(repr=False)

    def __post_init__(self):
        for name, limit in (
            ("workflow_run_uid", 64),
            ("job_uid", 64),
            ("worker_id", 120),
            ("lease_token", 128),
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, limit))
        attempt = int(self.execution_attempt or 0)
        if attempt <= 0:
            raise ValueError("execution_attempt must be positive.")
        object.__setattr__(self, "execution_attempt", attempt)


@dataclass(frozen=True)
class ProcessDocumentAlignmentWorkflowResult:
    outcome: str
    workflow_run_uid: str
    job_uid: str
    run_status: str = ""
    run_stage: str = ""
    total_items: int = 0
    ready_for_review_items: int = 0
    blocked_items: int = 0
    failed_items: int = 0
    warning_count: int = 0
    processed_in_this_invocation: int = 0
    reused_items: int = 0
    stopped_at_item_uid: str = ""
    retryable: bool = False
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self):
        object.__setattr__(self, "outcome", _required_text(self.outcome, "outcome", 80))
        object.__setattr__(
            self,
            "workflow_run_uid",
            _required_text(self.workflow_run_uid, "workflow_run_uid", 64),
        )
        object.__setattr__(self, "job_uid", _required_text(self.job_uid, "job_uid", 64))
        for name in (
            "total_items",
            "ready_for_review_items",
            "blocked_items",
            "failed_items",
            "warning_count",
            "processed_in_this_invocation",
            "reused_items",
        ):
            value = int(getattr(self, name) or 0)
            if value < 0:
                raise ValueError(f"{name} must be non-negative.")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "error_code", str(self.error_code or "")[:120])
        object.__setattr__(self, "error_message", _safe_error_message(self.error_message))


@dataclass(frozen=True)
class DocumentAlignmentProcessingModels:
    workflow_run: Any
    workflow_item: Any
    background_job: Any
    audit_record: Any


@dataclass(frozen=True)
class WorkflowBootstrapCollaborator:
    execute: Callable[[ProcessDocumentAlignmentWorkflowCommand], Any]


@dataclass(frozen=True)
class ItemPreparationCollaborator:
    prepare: Callable[[ProcessDocumentAlignmentWorkflowCommand, str], Any]
    validate_scope: Callable[[ProcessDocumentAlignmentWorkflowCommand, str, Any], bool]


@dataclass(frozen=True)
class ItemVerificationCollaborator:
    execute: Callable[[ProcessDocumentAlignmentWorkflowCommand, str, Any], Any]


@dataclass(frozen=True)
class LeaseCollaborator:
    heartbeat: Callable[[ProcessDocumentAlignmentWorkflowCommand], Any]
    fence: Callable[[ProcessDocumentAlignmentWorkflowCommand], Any]


@dataclass(frozen=True)
class DocumentAlignmentProcessingDependencies:
    session: Any
    models: DocumentAlignmentProcessingModels
    bootstrap: WorkflowBootstrapCollaborator
    preparation: ItemPreparationCollaborator
    verification: ItemVerificationCollaborator
    lease: LeaseCollaborator
    current_time_factory: Callable[[], datetime]
    audit_uid_factory: Callable[[], str] = lambda: uuid.uuid4().hex
    integrity_error_type: type[BaseException] = IntegrityError


def build_document_alignment_root_audit_event_identity(
    workflow_run_uid: str,
    workflow_version: str,
    event_type: str,
) -> str:
    payload = {
        "identity_version": ROOT_AUDIT_IDENTITY_VERSION,
        "workflow_run_uid": _required_text(workflow_run_uid, "workflow_run_uid", 64),
        "workflow_version": _required_text(workflow_version, "workflow_version", 80),
        "event_type": _required_text(event_type, "event_type", 120),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{ROOT_AUDIT_IDENTITY_VERSION}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _loads_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _time_text(value: datetime) -> str:
    return value.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _lease_outcome(result: Any) -> tuple[str, str, str, bool]:
    if getattr(result, "outcome", "") == LEASE_OUTCOME_STALE_ATTEMPT:
        return (
            OUTCOME_STALE_ATTEMPT,
            getattr(result, "error_code", "DOCUMENT_ALIGNMENT_STALE_EXECUTION_ATTEMPT"),
            getattr(result, "error_message", "Formal execution attempt is stale."),
            False,
        )
    if getattr(result, "outcome", "") == LEASE_OUTCOME_LEASE_EXPIRED:
        return (
            OUTCOME_LEASE_EXPIRED,
            getattr(result, "error_code", "DOCUMENT_ALIGNMENT_LEASE_EXPIRED"),
            getattr(result, "error_message", "Formal job lease expired."),
            False,
        )
    return (
        OUTCOME_RETRYABLE_INTERRUPTION,
        getattr(result, "error_code", "DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED"),
        getattr(result, "error_message", "Formal processing lease is not active."),
        True,
    )


def _result(command, dependencies, outcome: str, *, run: Any | None = None, **values):
    if run is None:
        run = dependencies.session.query(dependencies.models.workflow_run).filter_by(
            run_uid=command.workflow_run_uid
        ).one_or_none()
    return ProcessDocumentAlignmentWorkflowResult(
        outcome=outcome,
        workflow_run_uid=command.workflow_run_uid,
        job_uid=command.job_uid,
        run_status=str(getattr(run, "status", "") or ""),
        run_stage=str(getattr(run, "stage", "") or ""),
        total_items=int(getattr(run, "total_items", 0) or 0),
        ready_for_review_items=int(getattr(run, "ready_for_review_items", 0) or 0),
        blocked_items=int(getattr(run, "blocked_items", 0) or 0),
        failed_items=int(getattr(run, "failed_items", 0) or 0),
        warning_count=int(getattr(run, "warning_count", 0) or 0),
        **values,
    )


def _heartbeat_failure(command, dependencies, **values):
    result = dependencies.lease.heartbeat(command)
    if getattr(result, "outcome", "") == LEASE_OUTCOME_ACCEPTED:
        return None
    outcome, code, message, retryable = _lease_outcome(result)
    return _result(
        command,
        dependencies,
        outcome,
        retryable=retryable,
        error_code=code,
        error_message=message,
        **values,
    )


def _fence(command, dependencies):
    result = dependencies.lease.fence(command)
    return result if getattr(result, "outcome", "") == LEASE_OUTCOME_ACCEPTED else result


def _job_and_run(command, dependencies):
    session = dependencies.session
    models = dependencies.models
    run = session.query(models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one_or_none()
    job = session.query(models.background_job).filter_by(job_uid=command.job_uid).one_or_none()
    payload = _loads_json(getattr(job, "input_json", "{}"), {}) if job is not None else {}
    if run is None:
        return None, None, "DOCUMENT_ALIGNMENT_RUN_NOT_FOUND"
    if job is None:
        return run, None, "DOCUMENT_ALIGNMENT_JOB_NOT_FOUND"
    if not all((
        str(job.job_type or "") == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        isinstance(payload, dict),
        str(payload.get("workflow_run_uid") or "") == command.workflow_run_uid,
        str(payload.get("workflow_version") or "") == str(run.workflow_version),
    )):
        return run, job, "DOCUMENT_ALIGNMENT_JOB_MISMATCH"
    return run, job, ""


def _root_audit_uid(dependencies, event_identity: str) -> str:
    seed = _safe_error_message(dependencies.audit_uid_factory()) or uuid.uuid4().hex
    suffix = event_identity.rsplit(":", 1)[-1][:16]
    return f"{seed[:40]}-{suffix}"[:64]


def _record_root_audit_once(dependencies, run: Any, event_type: str, *, result: str = "success") -> bool:
    session = dependencies.session
    identity = build_document_alignment_root_audit_event_identity(
        str(run.run_uid),
        str(run.workflow_version),
        event_type,
    )
    existing = session.query(dependencies.models.audit_record).filter_by(event_identity=identity).one_or_none()
    if existing is not None:
        return False
    counts = {
        "total_items": int(run.total_items or 0),
        "ready_for_review_items": int(run.ready_for_review_items or 0),
        "blocked_items": int(run.blocked_items or 0),
        "failed_items": int(run.failed_items or 0),
        "warning_count": int(run.warning_count or 0),
        "status": str(run.status or ""),
        "stage": str(run.stage or ""),
    }
    actor_id = int(run.requested_by) if str(run.requested_by or "").isdigit() else None
    record = dependencies.models.audit_record(
        audit_uid=_root_audit_uid(dependencies, identity),
        event_identity=identity,
        event_type=event_type,
        target_type="document_alignment_workflow_run",
        target_uid=run.run_uid,
        actor_id=actor_id,
        actor_role="teacher",
        request_id=run.request_id or "",
        source="formal_processing_orchestrator",
        before_snapshot="{}",
        after_snapshot=json.dumps(counts, ensure_ascii=False, sort_keys=True),
        input_payload=json.dumps(
            {
                "source_uid": run.source_uid,
                "workflow_version": run.workflow_version,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        output_payload=json.dumps(counts, ensure_ascii=False, sort_keys=True),
        changed_fields=json.dumps(["status", "stage", "progress_counts"], ensure_ascii=False),
        result=result,
        error_code=run.error_code or "",
        error_message=run.error_message or "",
        prompt_version=run.prompt_version or "",
        retrieval_version=run.retrieval_version or "",
        created_at=_time_text(dependencies.current_time_factory()),
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
        return True
    except dependencies.integrity_error_type as exc:
        text = str(exc)
        if "event_identity" not in text and "uq_audit_record_event_identity" not in text:
            raise
        return False


def _persist_started_audit(command, dependencies) -> bool:
    ownership = _fence(command, dependencies)
    if getattr(ownership, "outcome", "") != LEASE_OUTCOME_ACCEPTED:
        dependencies.session.rollback()
        return False
    run = dependencies.session.query(dependencies.models.workflow_run).filter_by(
        run_uid=command.workflow_run_uid
    ).one()
    _record_root_audit_once(dependencies, run, "document_alignment_processing_started")
    dependencies.session.commit()
    return True


def _json_values(values: Any) -> str:
    return json.dumps(sorted({str(value) for value in values or () if str(value or "").strip()}), ensure_ascii=False)


def _candidate_summary(prepared: Any, candidate_count: int) -> str:
    return json.dumps(
        {
            "values": list(prepared.chinese_candidate_values),
            "provenance_refs": list(prepared.chinese_candidate_provenance_refs),
            "candidate_count": int(candidate_count or 0),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _persist_evidence_ready(command, dependencies, item_uid: str, preparation_result: Any) -> bool:
    ownership = _fence(command, dependencies)
    if getattr(ownership, "outcome", "") != LEASE_OUTCOME_ACCEPTED:
        dependencies.session.rollback()
        return False
    session = dependencies.session
    item = session.query(dependencies.models.workflow_item).filter_by(item_uid=item_uid).one_or_none()
    if item is None:
        session.rollback()
        return False
    prepared = preparation_result.prepared_input
    if item.status == ITEM_STATUS_EVIDENCE_READY:
        return True
    if item.status != ITEM_STATUS_CANDIDATE or not dependencies.preparation.validate_scope(
        command, item_uid, prepared
    ):
        session.rollback()
        return False
    item.english_evidence_refs = _json_values(preparation_result.english_evidence_refs)
    item.chinese_evidence_refs = _json_values(preparation_result.chinese_evidence_refs)
    item.chinese_candidate_summary = _candidate_summary(prepared, preparation_result.candidate_count)
    item.risk_labels = _json_values(preparation_result.risk_labels)
    item.warning_count = len(preparation_result.risk_labels)
    item.status = ITEM_STATUS_EVIDENCE_READY
    item.stage = ITEM_STAGE_EVIDENCE_RETRIEVAL
    item.error_code = ""
    item.error_message = ""
    item.started_at = item.started_at or _time_text(dependencies.current_time_factory())
    item.finished_at = ""
    try:
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False


def _block_item(command, dependencies, item_uid: str, preparation_result: Any) -> bool:
    ownership = _fence(command, dependencies)
    if getattr(ownership, "outcome", "") != LEASE_OUTCOME_ACCEPTED:
        dependencies.session.rollback()
        return False
    session = dependencies.session
    item = session.query(dependencies.models.workflow_item).filter_by(item_uid=item_uid).one_or_none()
    if item is None or item.status not in {ITEM_STATUS_CANDIDATE, ITEM_STATUS_EVIDENCE_READY}:
        session.rollback()
        return False
    item.english_evidence_refs = _json_values(preparation_result.english_evidence_refs)
    item.chinese_evidence_refs = _json_values(preparation_result.chinese_evidence_refs)
    if preparation_result.chinese_candidate_values:
        item.chinese_candidate_summary = json.dumps(
            {
                "values": list(preparation_result.chinese_candidate_values),
                "provenance_refs": list(preparation_result.chinese_candidate_provenance_refs),
                "candidate_count": int(preparation_result.candidate_count or 0),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    item.risk_labels = _json_values(preparation_result.risk_labels)
    item.warning_count = max(1, len(preparation_result.risk_labels))
    item.status = ITEM_STATUS_BLOCKED
    item.stage = ITEM_STAGE_TERMINAL
    item.error_code = preparation_result.error_code
    item.error_message = _safe_error_message(preparation_result.error_message)
    item.finished_at = _time_text(dependencies.current_time_factory())
    try:
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False


def _block_unstarted_items_for_source_change(command, dependencies, preparation_result: Any) -> bool:
    ownership = _fence(command, dependencies)
    if getattr(ownership, "outcome", "") != LEASE_OUTCOME_ACCEPTED:
        dependencies.session.rollback()
        return False
    session = dependencies.session
    run = session.query(dependencies.models.workflow_run).filter_by(
        run_uid=command.workflow_run_uid
    ).one_or_none()
    if run is None:
        session.rollback()
        return False
    items = session.query(dependencies.models.workflow_item).filter_by(
        workflow_run_id=run.id,
        status=ITEM_STATUS_CANDIDATE,
    ).all()
    finished_at = _time_text(dependencies.current_time_factory())
    for item in items:
        item.status = ITEM_STATUS_BLOCKED
        item.stage = ITEM_STAGE_TERMINAL
        item.warning_count = max(1, int(item.warning_count or 0))
        item.error_code = "DOCUMENT_ALIGNMENT_SOURCE_CHANGED"
        item.error_message = _safe_error_message(preparation_result.error_message)
        item.finished_at = finished_at
    try:
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False


def _risk_count(value: Any) -> int:
    loaded = _loads_json(value, [])
    return len(loaded) if isinstance(loaded, list) else 0


def _progress_values(items: list[Any]) -> dict[str, int]:
    ready = sum(item.status == ITEM_STATUS_NEEDS_REVIEW for item in items)
    blocked = sum(item.status == ITEM_STATUS_BLOCKED for item in items)
    failed = sum(item.status == ITEM_STATUS_FAILED for item in items)
    risky_ready = sum(
        item.status == ITEM_STATUS_NEEDS_REVIEW and _risk_count(item.risk_labels) > 0
        for item in items
    )
    return {
        "total": len(items),
        "ready": ready,
        "blocked": blocked,
        "failed": failed,
        "warnings": risky_ready + blocked + failed,
    }


def _apply_progress(run: Any, values: dict[str, int]):
    run.total_items = values["total"]
    run.successful_items = values["ready"]
    run.ready_for_review_items = values["ready"]
    run.blocked_items = values["blocked"]
    run.failed_items = values["failed"]
    run.warning_count = values["warnings"]


def _recalculate_progress(command, dependencies) -> bool:
    ownership = _fence(command, dependencies)
    if getattr(ownership, "outcome", "") != LEASE_OUTCOME_ACCEPTED:
        dependencies.session.rollback()
        return False
    session = dependencies.session
    run = session.query(dependencies.models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one()
    items = session.query(dependencies.models.workflow_item).filter_by(workflow_run_id=run.id).all()
    _apply_progress(run, _progress_values(items))
    try:
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False


def _finalize_root(command, dependencies, processed: int, reused: int):
    ownership = _fence(command, dependencies)
    if getattr(ownership, "outcome", "") != LEASE_OUTCOME_ACCEPTED:
        dependencies.session.rollback()
        outcome, code, message, retryable = _lease_outcome(ownership)
        return _result(
            command,
            dependencies,
            outcome,
            processed_in_this_invocation=processed,
            reused_items=reused,
            retryable=retryable,
            error_code=code,
            error_message=message,
        )
    session = dependencies.session
    run = session.query(dependencies.models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one()
    items = (
        session.query(dependencies.models.workflow_item)
        .filter_by(workflow_run_id=run.id)
        .order_by(dependencies.models.workflow_item.id, dependencies.models.workflow_item.item_key)
        .all()
    )
    progress = _progress_values(items)
    _apply_progress(run, progress)
    if not items:
        session.commit()
        return _result(
            command,
            dependencies,
            OUTCOME_BLOCKED,
            run=run,
            processed_in_this_invocation=processed,
            reused_items=reused,
            error_code=run.error_code,
            error_message=run.error_message,
        )
    if any(item.status not in _ITEM_TERMINAL_STATUSES for item in items):
        session.commit()
        return _result(
            command,
            dependencies,
            OUTCOME_RETRYABLE_INTERRUPTION,
            run=run,
            processed_in_this_invocation=processed,
            reused_items=reused,
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
            error_message="Formal processing still has non-terminal items.",
        )
    if progress["ready"] == progress["total"]:
        outcome = ROOT_STATUS_READY_FOR_REVIEW
        event_type = "document_alignment_ready_for_review"
        run.error_code = ""
        run.error_message = ""
    elif progress["ready"] > 0:
        outcome = ROOT_STATUS_COMPLETED_WITH_WARNINGS
        event_type = "document_alignment_completed_with_warnings"
        run.error_code = ""
        run.error_message = ""
    elif progress["failed"] > 0:
        outcome = ROOT_STATUS_FAILED
        event_type = "document_alignment_failed"
        run.error_code = "DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED"
        run.error_message = "All document alignment items failed or were blocked."
    else:
        outcome = ROOT_STATUS_BLOCKED
        event_type = "document_alignment_blocked"
        run.error_code = "DOCUMENT_ALIGNMENT_ALL_ITEMS_BLOCKED"
        run.error_message = "All document alignment items were blocked."
    run.status = outcome
    run.stage = ROOT_STAGE_TERMINAL
    run.finished_at = _time_text(dependencies.current_time_factory())
    try:
        _record_root_audit_once(
            dependencies,
            run,
            event_type,
            result="error" if outcome in {ROOT_STATUS_BLOCKED, ROOT_STATUS_FAILED} else "success",
        )
        session.commit()
    except Exception:
        session.rollback()
        return _result(
            command,
            dependencies,
            OUTCOME_PERSISTENCE_ERROR,
            processed_in_this_invocation=processed,
            reused_items=reused,
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
            error_message="Root finalization could not be persisted.",
        )
    return _result(
        command,
        dependencies,
        outcome,
        run=run,
        processed_in_this_invocation=processed,
        reused_items=reused,
    )


def finalize_document_alignment_workflow_failure(
    command: ProcessDocumentAlignmentWorkflowCommand,
    dependencies: DocumentAlignmentProcessingDependencies,
    error_code: str,
    error_message: str,
) -> ProcessDocumentAlignmentWorkflowResult:
    """Persist a lease-fenced terminal root failure without mutating its job."""

    session = dependencies.session
    safe_code = _required_text(error_code, "error_code", 120)
    safe_message = _safe_error_message(error_message) or "Document alignment processing failed safely."
    try:
        run, _, identity_error = _job_and_run(command, dependencies)
        session.rollback()
        if identity_error:
            return _result(
                command,
                dependencies,
                OUTCOME_INVALID_RUN_STATE,
                run=run,
                error_code=identity_error,
                error_message="Workflow run and formal job identity do not match.",
            )
        if run.status in _ROOT_TERMINAL_STATUSES:
            return _result(command, dependencies, OUTCOME_ALREADY_TERMINAL, run=run)

        ownership = _fence(command, dependencies)
        if getattr(ownership, "outcome", "") != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            outcome, code, message, retryable = _lease_outcome(ownership)
            return _result(
                command,
                dependencies,
                outcome,
                retryable=retryable,
                error_code=code,
                error_message=message,
            )

        run = session.query(dependencies.models.workflow_run).filter_by(
            run_uid=command.workflow_run_uid
        ).one()
        items = session.query(dependencies.models.workflow_item).filter_by(
            workflow_run_id=run.id
        ).all()
        _apply_progress(run, _progress_values(items))
        run.status = ROOT_STATUS_FAILED
        run.stage = ROOT_STAGE_TERMINAL
        run.error_code = safe_code
        run.error_message = safe_message
        run.finished_at = _time_text(dependencies.current_time_factory())
        _record_root_audit_once(dependencies, run, "document_alignment_failed", result="error")
        session.commit()
        return _result(command, dependencies, OUTCOME_FAILED, run=run)
    except Exception:
        session.rollback()
        return _result(
            command,
            dependencies,
            OUTCOME_PERSISTENCE_ERROR,
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
            error_message="Root failure finalization could not be persisted.",
        )


def process_document_alignment_workflow(
    command: ProcessDocumentAlignmentWorkflowCommand,
    dependencies: DocumentAlignmentProcessingDependencies,
) -> ProcessDocumentAlignmentWorkflowResult:
    session = dependencies.session
    processed = 0
    reused = 0
    try:
        run, _, identity_error = _job_and_run(command, dependencies)
        session.rollback()
        if identity_error:
            return _result(
                command,
                dependencies,
                OUTCOME_INVALID_RUN_STATE,
                run=run,
                error_code=identity_error,
                error_message="Workflow run and formal job identity do not match.",
            )
        if run.status not in _ROOT_ENTRY_STATUSES | _ROOT_TERMINAL_STATUSES:
            return _result(
                command,
                dependencies,
                OUTCOME_INVALID_RUN_STATE,
                run=run,
                error_code="DOCUMENT_ALIGNMENT_INVALID_RUN_STATE",
                error_message="Workflow run is not processable.",
            )
        heartbeat_failure = _heartbeat_failure(command, dependencies, run=run)
        if heartbeat_failure is not None:
            return heartbeat_failure
        run = session.query(dependencies.models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one()
        if run.status in _ROOT_TERMINAL_STATUSES:
            session.rollback()
            return _result(command, dependencies, OUTCOME_ALREADY_TERMINAL, run=run)

        if run.status in {ROOT_STATUS_QUEUED, ROOT_STATUS_VALIDATING}:
            heartbeat_failure = _heartbeat_failure(command, dependencies)
            if heartbeat_failure is not None:
                return heartbeat_failure
            bootstrap = dependencies.bootstrap.execute(command)
            if getattr(bootstrap, "outcome", "") in {
                BOOTSTRAP_OUTCOME_STALE_ATTEMPT,
                BOOTSTRAP_OUTCOME_LEASE_EXPIRED,
                BOOTSTRAP_OUTCOME_LEASE_NOT_OWNED,
            }:
                outcome = (
                    OUTCOME_STALE_ATTEMPT
                    if bootstrap.outcome == BOOTSTRAP_OUTCOME_STALE_ATTEMPT
                    else OUTCOME_LEASE_EXPIRED
                    if bootstrap.outcome == BOOTSTRAP_OUTCOME_LEASE_EXPIRED
                    else OUTCOME_RETRYABLE_INTERRUPTION
                )
                return _result(
                    command,
                    dependencies,
                    outcome,
                    retryable=outcome == OUTCOME_RETRYABLE_INTERRUPTION,
                    error_code=bootstrap.error_code,
                    error_message=bootstrap.error_message,
                )
            heartbeat_failure = _heartbeat_failure(command, dependencies)
            if heartbeat_failure is not None:
                return heartbeat_failure
            run = session.query(dependencies.models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one()
            if bootstrap.outcome not in {BOOTSTRAP_OUTCOME_CREATED, BOOTSTRAP_OUTCOME_REUSED}:
                session.rollback()
                return _result(
                    command,
                    dependencies,
                    run.status if run.status in _ROOT_TERMINAL_STATUSES else OUTCOME_RETRYABLE_INTERRUPTION,
                    run=run,
                    retryable=bool(getattr(bootstrap, "retryable", False)),
                    error_code=bootstrap.error_code,
                    error_message=bootstrap.error_message,
                )

        if not _persist_started_audit(command, dependencies):
            return _result(
                command,
                dependencies,
                OUTCOME_RETRYABLE_INTERRUPTION,
                retryable=True,
                error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
                error_message="Processing start could not be fenced.",
            )

        run = session.query(dependencies.models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one()
        item_uids = [
            row.item_uid
            for row in (
                session.query(dependencies.models.workflow_item)
                .filter_by(workflow_run_id=run.id)
                .order_by(dependencies.models.workflow_item.id, dependencies.models.workflow_item.item_key)
                .all()
            )
        ]
        session.rollback()
        for item_uid in item_uids:
            heartbeat_failure = _heartbeat_failure(
                command,
                dependencies,
                processed_in_this_invocation=processed,
                reused_items=reused,
                stopped_at_item_uid=item_uid,
            )
            if heartbeat_failure is not None:
                return heartbeat_failure
            item = session.query(dependencies.models.workflow_item).filter_by(item_uid=item_uid).one()
            status = str(item.status)
            session.rollback()
            if status in _ITEM_TERMINAL_STATUSES:
                reused += 1
                continue
            if status not in {ITEM_STATUS_CANDIDATE} | _ITEM_ADAPTER_STATUSES:
                return _result(
                    command,
                    dependencies,
                    OUTCOME_INVALID_RUN_STATE,
                    processed_in_this_invocation=processed,
                    reused_items=reused,
                    stopped_at_item_uid=item_uid,
                    error_code="DOCUMENT_ALIGNMENT_INVALID_RUN_STATE",
                    error_message="Workflow item is not processable.",
                )

            prepared_result = dependencies.preparation.prepare(command, item_uid)
            heartbeat_failure = _heartbeat_failure(
                command,
                dependencies,
                processed_in_this_invocation=processed,
                reused_items=reused,
                stopped_at_item_uid=item_uid,
            )
            if heartbeat_failure is not None:
                return heartbeat_failure
            if prepared_result.outcome in {
                PREPARATION_OUTCOME_EVIDENCE_INSUFFICIENT,
                PREPARATION_OUTCOME_CHINESE_CANDIDATE_UNAVAILABLE,
            }:
                if not _block_item(command, dependencies, item_uid, prepared_result):
                    return _result(
                        command,
                        dependencies,
                        OUTCOME_RETRYABLE_INTERRUPTION,
                        stopped_at_item_uid=item_uid,
                        retryable=True,
                        error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
                        error_message="Business-blocked item could not be saved.",
                    )
                processed += 1
                if not _recalculate_progress(command, dependencies):
                    return _result(
                        command,
                        dependencies,
                        OUTCOME_RETRYABLE_INTERRUPTION,
                        processed_in_this_invocation=processed,
                        stopped_at_item_uid=item_uid,
                        retryable=True,
                        error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
                        error_message="Workflow progress could not be recalculated.",
                    )
                continue
            if prepared_result.outcome == PREPARATION_OUTCOME_SOURCE_CHANGED:
                if not _block_unstarted_items_for_source_change(command, dependencies, prepared_result):
                    return _result(
                        command,
                        dependencies,
                        OUTCOME_RETRYABLE_INTERRUPTION,
                        processed_in_this_invocation=processed,
                        reused_items=reused,
                        stopped_at_item_uid=item_uid,
                        retryable=True,
                        error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
                        error_message="Source-change item blocking could not be saved.",
                    )
                processed += 1
                if not _recalculate_progress(command, dependencies):
                    return _result(
                        command,
                        dependencies,
                        OUTCOME_RETRYABLE_INTERRUPTION,
                        processed_in_this_invocation=processed,
                        reused_items=reused,
                        stopped_at_item_uid=item_uid,
                        retryable=True,
                        error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
                        error_message="Workflow progress could not be recalculated.",
                    )
                break
            if prepared_result.outcome == PREPARATION_OUTCOME_CHUNK_NOT_AVAILABLE:
                return _result(
                    command,
                    dependencies,
                    OUTCOME_RETRYABLE_INTERRUPTION,
                    processed_in_this_invocation=processed,
                    reused_items=reused,
                    stopped_at_item_uid=item_uid,
                    retryable=True,
                    error_code=prepared_result.error_code or "DOCUMENT_ALIGNMENT_CHUNK_NOT_AVAILABLE",
                    error_message=prepared_result.error_message or "A governed source chunk is unavailable.",
                )
            if prepared_result.outcome != PREPARATION_OUTCOME_PREPARED:
                return _result(
                    command,
                    dependencies,
                    OUTCOME_RETRYABLE_INTERRUPTION,
                    processed_in_this_invocation=processed,
                    reused_items=reused,
                    stopped_at_item_uid=item_uid,
                    retryable=True,
                    error_code=prepared_result.error_code or "DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED",
                    error_message=prepared_result.error_message or "Item preparation failed.",
                )
            if status == ITEM_STATUS_CANDIDATE and not _persist_evidence_ready(
                command, dependencies, item_uid, prepared_result
            ):
                return _result(
                    command,
                    dependencies,
                    OUTCOME_RETRYABLE_INTERRUPTION,
                    stopped_at_item_uid=item_uid,
                    retryable=True,
                    error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
                    error_message="Evidence-ready checkpoint could not be saved.",
                )
            verification = dependencies.verification.execute(
                command,
                item_uid,
                prepared_result.prepared_input,
            )
            processed += 1
            if getattr(verification, "outcome", "") in {"stale_attempt", "lease_expired"}:
                return _result(
                    command,
                    dependencies,
                    verification.outcome,
                    processed_in_this_invocation=processed,
                    reused_items=reused,
                    stopped_at_item_uid=item_uid,
                    retryable=False,
                    error_code=verification.error_code,
                    error_message=verification.error_message,
                )
            if getattr(verification, "retryable", False) or getattr(verification, "outcome", "") in {
                "persistence_error",
                "attach_pending",
                "execution_conflict",
            }:
                return _result(
                    command,
                    dependencies,
                    OUTCOME_RETRYABLE_INTERRUPTION,
                    processed_in_this_invocation=processed,
                    reused_items=reused,
                    stopped_at_item_uid=item_uid,
                    retryable=True,
                    error_code=verification.error_code or "DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
                    error_message=verification.error_message or "Item verification was interrupted.",
                )
            if getattr(verification, "outcome", "") not in {
                "needs_review",
                "reused_completed_result",
            } | _ADAPTER_BUSINESS_OUTCOMES:
                return _result(
                    command,
                    dependencies,
                    OUTCOME_RETRYABLE_INTERRUPTION,
                    processed_in_this_invocation=processed,
                    reused_items=reused,
                    stopped_at_item_uid=item_uid,
                    retryable=True,
                    error_code="DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED",
                    error_message="Item verification returned an unsupported outcome.",
                )
            heartbeat_failure = _heartbeat_failure(
                command,
                dependencies,
                processed_in_this_invocation=processed,
                reused_items=reused,
                stopped_at_item_uid=item_uid,
            )
            if heartbeat_failure is not None:
                return heartbeat_failure
            if not _recalculate_progress(command, dependencies):
                return _result(
                    command,
                    dependencies,
                    OUTCOME_RETRYABLE_INTERRUPTION,
                    processed_in_this_invocation=processed,
                    reused_items=reused,
                    stopped_at_item_uid=item_uid,
                    retryable=True,
                    error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
                    error_message="Workflow progress could not be recalculated.",
                )

        heartbeat_failure = _heartbeat_failure(
            command,
            dependencies,
            processed_in_this_invocation=processed,
            reused_items=reused,
        )
        if heartbeat_failure is not None:
            return heartbeat_failure
        return _finalize_root(command, dependencies, processed, reused)
    except Exception:
        session.rollback()
        return _result(
            command,
            dependencies,
            OUTCOME_RETRYABLE_INTERRUPTION,
            processed_in_this_invocation=processed,
            reused_items=reused,
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED",
            error_message="Document alignment processing failed safely.",
        )
