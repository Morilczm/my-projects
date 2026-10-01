"""Formal document alignment workflow admission service.

This module starts a formal document-alignment workflow root and queues a
transport-only BackgroundJob. It deliberately excludes HTTP, worker, provider,
evidence, card, and verification execution concerns.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1,
    FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION,
    ROOT_STAGE_QUEUED,
    ROOT_STATUS_QUEUED,
)
from services.formal_document_alignment_provider_selection import (
    resolve_default_formal_document_alignment_provider_selection,
)


OUTCOME_CREATED = "created"
OUTCOME_REUSED = "reused"
OUTCOME_INVALID_REQUEST = "invalid_request"
OUTCOME_SOURCE_NOT_AVAILABLE = "source_not_available"
OUTCOME_SOURCE_NOT_GOVERNED = "source_not_governed"
OUTCOME_PARSE_BLOCKED = "parse_blocked"
OUTCOME_NO_USABLE_CHUNKS = "no_usable_chunks"
OUTCOME_IDEMPOTENCY_CONFLICT = "idempotency_conflict"
OUTCOME_PROVIDER_SELECTION_UNAVAILABLE = "provider_selection_unavailable"
OUTCOME_PERSISTENCE_ERROR = "persistence_error"

ERROR_INVALID_REQUEST = "DOCUMENT_ALIGNMENT_INVALID_REQUEST"
ERROR_SOURCE_NOT_AVAILABLE = "DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE"
ERROR_IDEMPOTENCY_CONFLICT = "DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT"
ERROR_PROVIDER_SELECTION_UNAVAILABLE = "DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_UNAVAILABLE"
ERROR_PERSISTENCE = "DOCUMENT_ALIGNMENT_PERSISTENCE_ERROR"


def _required_text(value: Any, field_name: str, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if max_length is not None and len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _optional_text(value: Any, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    if max_length is not None:
        return text[:max_length]
    return text


def _safe_error_message(message: Any, fallback: str = "Document alignment workflow could not be started.") -> str:
    text = str(message or fallback).strip() or fallback
    forbidden = ("LEXIBRIDGE_SENTINEL_SECRET", "Authorization:", "Cookie:", "Bearer ", "sk-")
    if any(marker in text for marker in forbidden):
        return fallback
    return text[:500]


@dataclass(frozen=True)
class StartDocumentAlignmentWorkflowCommand:
    source_uid: str
    requested_by: str
    request_id: str
    idempotency_key: str

    def __post_init__(self):
        object.__setattr__(self, "source_uid", _required_text(self.source_uid, "source_uid", 64))
        object.__setattr__(self, "requested_by", _required_text(self.requested_by, "requested_by", 120))
        object.__setattr__(self, "request_id", _required_text(self.request_id, "request_id", 120))
        object.__setattr__(self, "idempotency_key", _required_text(self.idempotency_key, "idempotency_key", 160))


@dataclass(frozen=True)
class GovernedKnowledgeSourceSnapshot:
    source_uid: str
    parse_uid: str
    source_version: str
    course: str
    chapter: str
    owner_user_id: str
    visibility: str
    source_status: str
    source_trust_level: str
    parse_status: str
    parse_quality: str
    usable_chunk_count: int

    def __post_init__(self):
        object.__setattr__(self, "source_uid", _required_text(self.source_uid, "source_uid", 64))
        object.__setattr__(self, "parse_uid", _optional_text(self.parse_uid, 64))
        object.__setattr__(self, "source_version", _optional_text(self.source_version, 80))
        object.__setattr__(self, "course", _optional_text(self.course, 160))
        object.__setattr__(self, "chapter", _optional_text(self.chapter, 160))
        object.__setattr__(self, "owner_user_id", _optional_text(self.owner_user_id, 120))
        object.__setattr__(self, "visibility", _optional_text(self.visibility, 40))
        object.__setattr__(self, "source_status", _optional_text(self.source_status, 40))
        object.__setattr__(self, "source_trust_level", _optional_text(self.source_trust_level, 80))
        object.__setattr__(self, "parse_status", _optional_text(self.parse_status, 40))
        object.__setattr__(self, "parse_quality", _optional_text(self.parse_quality, 80))
        usable = int(self.usable_chunk_count or 0)
        if usable < 0:
            raise ValueError("usable_chunk_count must be non-negative.")
        object.__setattr__(self, "usable_chunk_count", usable)


@dataclass(frozen=True)
class DocumentAlignmentWorkflowAuthorizationDecision:
    allowed: bool
    safe_error_code: str = ERROR_SOURCE_NOT_AVAILABLE
    safe_error_message: str = "Source is not available."
    outcome: str = OUTCOME_SOURCE_NOT_AVAILABLE


@dataclass(frozen=True)
class DocumentAlignmentSourceAdmissionDecision:
    allowed: bool
    safe_error_code: str = ERROR_SOURCE_NOT_AVAILABLE
    safe_error_message: str = "Source is not available."
    outcome: str = OUTCOME_SOURCE_NOT_AVAILABLE


@dataclass(frozen=True)
class DocumentAlignmentRequestedAudit:
    run_uid: str
    source_uid: str
    parse_uid: str
    course: str
    chapter: str
    workflow_version: str
    job_uid: str
    request_id: str
    requested_by: str
    fingerprint_prefix: str
    created_at: str


def record_document_alignment_requested_audit(session: Any, audit_record_model: Any, audit: DocumentAlignmentRequestedAudit) -> Any:
    actor_id = None
    try:
        actor_id = int(audit.requested_by)
    except (TypeError, ValueError):
        actor_id = None
    record = audit_record_model(
        event_type="document_alignment_requested",
        target_type="document_alignment_workflow_run",
        target_uid=audit.run_uid,
        actor_id=actor_id,
        actor_role="",
        actor_name=str(audit.requested_by or "")[:160],
        request_id=audit.request_id,
        source="service",
        input_payload=json.dumps({
            "source_uid": audit.source_uid,
            "parse_uid": audit.parse_uid,
            "course": audit.course,
            "chapter": audit.chapter,
            "workflow_version": audit.workflow_version,
        }, ensure_ascii=False, sort_keys=True),
        output_payload=json.dumps({
            "run_uid": audit.run_uid,
            "job_uid": audit.job_uid,
            "workflow_version": audit.workflow_version,
            "fingerprint_prefix": audit.fingerprint_prefix,
        }, ensure_ascii=False, sort_keys=True),
        changed_fields=json.dumps(["document_alignment_workflow_run", "background_job"], ensure_ascii=False),
        result="success",
        created_at=audit.created_at,
    )
    session.add(record)
    return record


def is_idempotency_integrity_error(exc: BaseException) -> bool:
    text = str(exc)
    return (
        "uq_document_alignment_workflow_idempotency" in text
        or "document_alignment_workflow_runs.requested_by" in text
        or "document_alignment_workflow_runs.source_uid" in text
        or "UNIQUE constraint failed" in text and "document_alignment_workflow_runs" in text
    )


@dataclass(frozen=True)
class DocumentAlignmentWorkflowApplicationDependencies:
    session: Any
    workflow_run_model: Any
    background_job_model: Any
    audit_record_model: Any
    source_loader: Callable[[str], GovernedKnowledgeSourceSnapshot | None]
    authorization_checker: Callable[[str, GovernedKnowledgeSourceSnapshot], DocumentAlignmentWorkflowAuthorizationDecision]
    source_admission_checker: Callable[[GovernedKnowledgeSourceSnapshot], DocumentAlignmentSourceAdmissionDecision]
    current_time_factory: Callable[[], str]
    uid_factory: Callable[[], str]
    provider_selection_resolver: Callable[[], Any] = (
        resolve_default_formal_document_alignment_provider_selection
    )
    workflow_version: str = FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION
    audit_recorder: Callable[[Any, Any, DocumentAlignmentRequestedAudit], Any] = record_document_alignment_requested_audit
    integrity_error_type: type[BaseException] = IntegrityError
    idempotency_error_matcher: Callable[[BaseException], bool] = is_idempotency_integrity_error

    def __post_init__(self):
        object.__setattr__(self, "workflow_version", _required_text(self.workflow_version, "workflow_version", 80))


@dataclass(frozen=True)
class StartDocumentAlignmentWorkflowResult:
    outcome: str
    run_uid: str = ""
    job_uid: str = ""
    status: str = ""
    stage: str = ""
    request_id: str = ""
    reused: bool = False
    error_code: str = ""
    error_message: str = ""


def build_document_alignment_idempotency_fingerprint(
    *,
    source_uid: str,
    parse_uid: str,
    source_version: str,
    course: str,
    chapter: str,
    workflow_version: str,
    request_id: str = "",
    idempotency_key: str = "",
) -> str:
    payload = {
        "source_uid": _required_text(source_uid, "source_uid", 64),
        "parse_uid": _required_text(parse_uid, "parse_uid", 64),
        "source_version": _optional_text(source_version, 80),
        "course": _optional_text(course, 160),
        "chapter": _optional_text(chapter, 160),
        "workflow_version": _required_text(workflow_version, "workflow_version", 80),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _result_for_decision(command: StartDocumentAlignmentWorkflowCommand, decision: Any) -> StartDocumentAlignmentWorkflowResult:
    return StartDocumentAlignmentWorkflowResult(
        outcome=getattr(decision, "outcome", OUTCOME_SOURCE_NOT_AVAILABLE) or OUTCOME_SOURCE_NOT_AVAILABLE,
        request_id=command.request_id,
        error_code=getattr(decision, "safe_error_code", ERROR_SOURCE_NOT_AVAILABLE) or ERROR_SOURCE_NOT_AVAILABLE,
        error_message=_safe_error_message(getattr(decision, "safe_error_message", "Source is not available."), "Source is not available."),
    )


def _idempotency_query(command: StartDocumentAlignmentWorkflowCommand, dependencies: DocumentAlignmentWorkflowApplicationDependencies):
    return dependencies.session.query(dependencies.workflow_run_model).filter_by(
        requested_by=command.requested_by,
        source_uid=command.source_uid,
        workflow_version=dependencies.workflow_version,
        idempotency_key=command.idempotency_key,
    )


def _find_existing_job_uid(dependencies: DocumentAlignmentWorkflowApplicationDependencies, run_uid: str) -> str:
    jobs = dependencies.session.query(dependencies.background_job_model).filter_by(
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ).all()
    for job in jobs:
        try:
            payload = json.loads(getattr(job, "input_json", "") or "{}")
        except (TypeError, ValueError):
            payload = {}
        if payload.get("workflow_run_uid") == run_uid:
            return str(getattr(job, "id", "") or "")
    return ""


def _reused_result(command, dependencies, existing):
    return StartDocumentAlignmentWorkflowResult(
        outcome=OUTCOME_REUSED,
        run_uid=getattr(existing, "run_uid", ""),
        job_uid=_find_existing_job_uid(dependencies, getattr(existing, "run_uid", "")),
        status=getattr(existing, "status", ""),
        stage=getattr(existing, "stage", ""),
        request_id=command.request_id,
        reused=True,
    )


def _conflict_result(command):
    return StartDocumentAlignmentWorkflowResult(
        outcome=OUTCOME_IDEMPOTENCY_CONFLICT,
        request_id=command.request_id,
        error_code=ERROR_IDEMPOTENCY_CONFLICT,
        error_message="Idempotency key was already used for a different document alignment payload.",
    )


def _persistence_result(request_id: str) -> StartDocumentAlignmentWorkflowResult:
    return StartDocumentAlignmentWorkflowResult(
        outcome=OUTCOME_PERSISTENCE_ERROR,
        request_id=request_id,
        error_code=ERROR_PERSISTENCE,
        error_message="Document alignment workflow could not be started.",
    )


def _build_background_job(dependencies, command, source_snapshot, run):
    now = dependencies.current_time_factory()
    payload = {
        "workflow_run_uid": run.run_uid,
        "workflow_version": run.workflow_version,
    }
    created_by = 0
    try:
        created_by = int(command.requested_by)
    except (TypeError, ValueError):
        created_by = 0
    return dependencies.background_job_model(
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        status="queued",
        priority=100,
        created_by=created_by,
        course_id=None,
        document_id=None,
        alignment_run_id=None,
        evaluation_run_id=None,
        scope_type=str(source_snapshot.visibility or ""),
        owner_user_id=None,
        input_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        result_json="{}",
        progress_current=0,
        progress_total=100,
        progress_message="Queued",
        error_code="",
        error_message="",
        attempt_count=0,
        max_attempts=FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1,
        created_at=now,
        updated_at=now,
    )


def _recover_after_idempotency_integrity_error(command, dependencies, fingerprint):
    existing = _idempotency_query(command, dependencies).first()
    if existing is None:
        return _persistence_result(command.request_id)
    if getattr(existing, "idempotency_fingerprint", "") == fingerprint:
        return _reused_result(command, dependencies, existing)
    return _conflict_result(command)


def start_document_alignment_workflow(
    command: StartDocumentAlignmentWorkflowCommand,
    dependencies: DocumentAlignmentWorkflowApplicationDependencies,
) -> StartDocumentAlignmentWorkflowResult:
    source_snapshot = dependencies.source_loader(command.source_uid)
    if source_snapshot is None:
        return StartDocumentAlignmentWorkflowResult(
            outcome=OUTCOME_SOURCE_NOT_AVAILABLE,
            request_id=command.request_id,
            error_code=ERROR_SOURCE_NOT_AVAILABLE,
            error_message="Source is not available.",
        )

    authorization = dependencies.authorization_checker(command.requested_by, source_snapshot)
    if not authorization.allowed:
        return _result_for_decision(command, authorization)

    admission = dependencies.source_admission_checker(source_snapshot)
    if not admission.allowed:
        return _result_for_decision(command, admission)

    fingerprint = build_document_alignment_idempotency_fingerprint(
        source_uid=source_snapshot.source_uid,
        parse_uid=source_snapshot.parse_uid,
        source_version=source_snapshot.source_version,
        course=source_snapshot.course,
        chapter=source_snapshot.chapter,
        workflow_version=dependencies.workflow_version,
    )

    existing = _idempotency_query(command, dependencies).first()
    if existing is not None:
        if getattr(existing, "idempotency_fingerprint", "") == fingerprint:
            return _reused_result(command, dependencies, existing)
        return _conflict_result(command)

    try:
        selection = dependencies.provider_selection_resolver()
    except Exception:
        dependencies.session.rollback()
        return StartDocumentAlignmentWorkflowResult(
            outcome=OUTCOME_PROVIDER_SELECTION_UNAVAILABLE,
            request_id=command.request_id,
            error_code=ERROR_PROVIDER_SELECTION_UNAVAILABLE,
            error_message="Formal document alignment provider selection is unavailable.",
        )

    now = dependencies.current_time_factory()
    run = dependencies.workflow_run_model(
        run_uid=dependencies.uid_factory(),
        source_uid=source_snapshot.source_uid,
        parse_uid=source_snapshot.parse_uid,
        source_version=source_snapshot.source_version,
        course=source_snapshot.course,
        chapter=source_snapshot.chapter,
        requested_by=command.requested_by,
        request_id=command.request_id,
        idempotency_key=command.idempotency_key,
        idempotency_fingerprint=fingerprint,
        workflow_version=dependencies.workflow_version,
        provider_preference=selection.provider_name,
        model_preference=selection.model_identity,
        prompt_version=selection.prompt_version,
        status=ROOT_STATUS_QUEUED,
        stage=ROOT_STAGE_QUEUED,
        total_items=0,
        successful_items=0,
        ready_for_review_items=0,
        blocked_items=0,
        failed_items=0,
        warning_count=0,
        error_code="",
        error_message="",
        created_at=now,
        updated_at=now,
    )

    try:
        dependencies.session.add(run)
        job = _build_background_job(dependencies, command, source_snapshot, run)
        dependencies.session.add(job)
        dependencies.session.flush()
        dependencies.audit_recorder(
            dependencies.session,
            dependencies.audit_record_model,
            DocumentAlignmentRequestedAudit(
                run_uid=run.run_uid,
                source_uid=source_snapshot.source_uid,
                parse_uid=source_snapshot.parse_uid,
                course=source_snapshot.course,
                chapter=source_snapshot.chapter,
                workflow_version=dependencies.workflow_version,
                job_uid=str(getattr(job, "id", "") or ""),
                request_id=command.request_id,
                requested_by=command.requested_by,
                fingerprint_prefix=fingerprint[:12],
                created_at=now,
            ),
        )
        dependencies.session.flush()
        dependencies.session.commit()
        return StartDocumentAlignmentWorkflowResult(
            outcome=OUTCOME_CREATED,
            run_uid=run.run_uid,
            job_uid=str(getattr(job, "id", "") or ""),
            status=run.status,
            stage=run.stage,
            request_id=command.request_id,
            reused=False,
        )
    except dependencies.integrity_error_type as exc:
        dependencies.session.rollback()
        if dependencies.idempotency_error_matcher(exc):
            return _recover_after_idempotency_integrity_error(command, dependencies, fingerprint)
        return _persistence_result(command.request_id)
    except Exception:
        dependencies.session.rollback()
        return _persistence_result(command.request_id)
