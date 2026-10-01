"""Attempt-fenced item bootstrap for formal document alignment workflows."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from sqlalchemy.exc import IntegrityError

from services.document_alignment_term_candidates import (
    EXTRACTION_OUTCOME_EXTRACTED,
    EXTRACTION_OUTCOME_EXTRACTION_FAILED,
    EXTRACTION_OUTCOME_INVALID_CHUNK_SCOPE,
    EXTRACTION_OUTCOME_ITEM_LIMIT_EXCEEDED,
    EXTRACTION_OUTCOME_NO_CANDIDATES,
    EXTRACTION_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED,
    ChunkScopedTermCandidate,
    ChunkScopedTermCandidateExtractionResult,
    GovernedSourceChunkSnapshot,
    extract_chunk_scoped_term_candidates,
)
from services.document_alignment_workflow_application import GovernedKnowledgeSourceSnapshot
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ITEM_STAGE_CANDIDATE,
    ITEM_STATUS_CANDIDATE,
    ROOT_STAGE_EVIDENCE_RETRIEVAL,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_PROCESSING,
    ROOT_STATUS_QUEUED,
    ROOT_STATUS_VALIDATING,
    WORKFLOW_VERSION_V1,
    build_document_alignment_item_key,
)
from services.formal_background_job_execution import (
    LEASE_OUTCOME_ACCEPTED,
    LEASE_OUTCOME_LEASE_EXPIRED,
    LEASE_OUTCOME_LEASE_NOT_OWNED,
    LEASE_OUTCOME_STALE_ATTEMPT,
    FormalBackgroundJobExecutionDependencies,
    FormalJobExecutionFence,
    fence_active_formal_job_lease_in_transaction,
)


BOOTSTRAP_OUTCOME_CREATED = "created"
BOOTSTRAP_OUTCOME_REUSED = "reused"
BOOTSTRAP_OUTCOME_NO_CANDIDATES = "no_candidates"
BOOTSTRAP_OUTCOME_ITEM_LIMIT_EXCEEDED = "item_limit_exceeded"
BOOTSTRAP_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED = "term_scope_limit_exceeded"
BOOTSTRAP_OUTCOME_ITEM_IDEMPOTENCY_CONFLICT = "item_idempotency_conflict"
BOOTSTRAP_OUTCOME_SOURCE_CHANGED = "source_changed"
BOOTSTRAP_OUTCOME_PARSE_BLOCKED = "parse_blocked"
BOOTSTRAP_OUTCOME_EXTRACTION_FAILED = "extraction_failed"
BOOTSTRAP_OUTCOME_INVALID_RUN_STATE = "invalid_run_state"
BOOTSTRAP_OUTCOME_LEASE_NOT_OWNED = "lease_not_owned"
BOOTSTRAP_OUTCOME_LEASE_EXPIRED = "lease_expired"
BOOTSTRAP_OUTCOME_STALE_ATTEMPT = "stale_attempt"
BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR = "persistence_error"

ERROR_NO_CANDIDATES = "DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES"
ERROR_ITEM_LIMIT = "DOCUMENT_ALIGNMENT_ITEM_LIMIT_EXCEEDED"
ERROR_SCOPE_LIMIT = "DOCUMENT_ALIGNMENT_TERM_SCOPE_LIMIT_EXCEEDED"
ERROR_ITEM_IDEMPOTENCY_CONFLICT = "DOCUMENT_ALIGNMENT_ITEM_IDEMPOTENCY_CONFLICT"
ERROR_SOURCE_CHANGED = "DOCUMENT_ALIGNMENT_SOURCE_CHANGED"
ERROR_PARSE_BLOCKED = "DOCUMENT_ALIGNMENT_PARSE_BLOCKED"
ERROR_INVALID_RUN_STATE = "DOCUMENT_ALIGNMENT_INVALID_RUN_STATE"
ERROR_PERSISTENCE = "DOCUMENT_ALIGNMENT_ITEM_PERSISTENCE_FAILED"

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_BOOTSTRAP_ALLOWED_STATUSES = frozenset({ROOT_STATUS_QUEUED, ROOT_STATUS_VALIDATING, ROOT_STATUS_PROCESSING})


def _utc_now() -> datetime:
    return datetime.utcnow()


def _item_uid() -> str:
    return uuid.uuid4().hex


def _required_text(value: Any, field_name: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _safe_message(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip() or fallback
    forbidden = ("LEXIBRIDGE_SENTINEL_SECRET", "Authorization:", "Cookie:", "Bearer ", "sk-")
    if any(marker in text for marker in forbidden):
        return fallback
    return text[:500]


def _time_text(value: datetime) -> str:
    return value.replace(tzinfo=None).strftime(_TIME_FORMAT)


def _json_list(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _is_item_key_integrity_error(exc: BaseException) -> bool:
    text = str(exc)
    return (
        "uq_document_alignment_workflow_item_key" in text
        or "UNIQUE constraint failed: document_alignment_workflow_items.workflow_run_id, document_alignment_workflow_items.item_key"
        in text
    )


@dataclass(frozen=True)
class BootstrapDocumentAlignmentItemsCommand:
    workflow_run_uid: str
    job_uid: str
    worker_id: str
    execution_attempt: int
    lease_token: str = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, "workflow_run_uid", _required_text(self.workflow_run_uid, "workflow_run_uid", 64))
        object.__setattr__(self, "job_uid", _required_text(self.job_uid, "job_uid", 64))
        object.__setattr__(self, "worker_id", _required_text(self.worker_id, "worker_id", 120))
        object.__setattr__(self, "lease_token", _required_text(self.lease_token, "lease_token", 128))
        attempt = int(self.execution_attempt or 0)
        if attempt <= 0:
            raise ValueError("execution_attempt must be positive.")
        object.__setattr__(self, "execution_attempt", attempt)


@dataclass(frozen=True)
class BootstrapDocumentAlignmentItemsDependencies:
    session: Any
    workflow_run_model: Any
    workflow_item_model: Any
    background_job_model: Any
    source_loader: Callable[[Any, str], GovernedKnowledgeSourceSnapshot | None]
    chunk_loader: Callable[[Any, GovernedKnowledgeSourceSnapshot], Iterable[GovernedSourceChunkSnapshot]]
    term_extractor: Callable[[str], Iterable[Any]]
    item_uid_factory: Callable[[], str] = _item_uid
    current_time_factory: Callable[[], datetime] = _utc_now
    workflow_version: str = WORKFLOW_VERSION_V1
    item_key_builder: Callable[[str, Iterable[str]], str] = build_document_alignment_item_key
    candidate_extractor: Callable[..., ChunkScopedTermCandidateExtractionResult] = extract_chunk_scoped_term_candidates
    lease_fence: Callable[..., Any] = fence_active_formal_job_lease_in_transaction
    integrity_error_type: type[BaseException] = IntegrityError
    item_key_integrity_error_matcher: Callable[[BaseException], bool] = _is_item_key_integrity_error

    def __post_init__(self):
        object.__setattr__(self, "workflow_version", _required_text(self.workflow_version, "workflow_version", 80))


@dataclass(frozen=True)
class BootstrapDocumentAlignmentItemsResult:
    outcome: str
    workflow_run_uid: str = ""
    job_uid: str = ""
    run_status: str = ""
    run_stage: str = ""
    candidate_count: int = 0
    canonical_candidate_count: int = 0
    created_item_count: int = 0
    reused_item_count: int = 0
    warning_count: int = 0
    admitted_candidate_count: int = 0
    overflow_candidate_count: int = 0
    overflow_candidate_ids: tuple[str, ...] = ()
    governance_status: str = ""
    retryable: bool = False
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self):
        for name in (
            "candidate_count",
            "canonical_candidate_count",
            "created_item_count",
            "reused_item_count",
            "warning_count",
            "admitted_candidate_count",
            "overflow_candidate_count",
        ):
            value = int(getattr(self, name) or 0)
            if value < 0:
                raise ValueError(f"{name} must be non-negative.")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "overflow_candidate_ids",
            tuple(str(value or "")[:80] for value in self.overflow_candidate_ids if str(value or "")),
        )
        object.__setattr__(self, "governance_status", str(self.governance_status or "")[:80])
        object.__setattr__(self, "error_code", str(self.error_code or "")[:120])
        if self.error_message:
            object.__setattr__(self, "error_message", _safe_message(self.error_message, "Item bootstrap failed."))


@dataclass(frozen=True)
class _RunSnapshot:
    workflow_run_uid: str
    source_uid: str
    parse_uid: str
    source_version: str
    workflow_version: str
    status: str


def _result(command: BootstrapDocumentAlignmentItemsCommand, outcome: str, **values):
    candidate_count = int(values.pop("candidate_count", values.get("canonical_candidate_count", 0)) or 0)
    values.setdefault("canonical_candidate_count", candidate_count)
    values.setdefault("candidate_count", candidate_count)
    values.setdefault(
        "retryable",
        outcome in {BOOTSTRAP_OUTCOME_EXTRACTION_FAILED, BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR},
    )
    return BootstrapDocumentAlignmentItemsResult(
        outcome=outcome,
        workflow_run_uid=command.workflow_run_uid,
        job_uid=command.job_uid,
        **values,
    )


def _run_snapshot(run: Any) -> _RunSnapshot:
    return _RunSnapshot(
        workflow_run_uid=str(run.run_uid),
        source_uid=str(run.source_uid),
        parse_uid=str(run.parse_uid),
        source_version=str(run.source_version or ""),
        workflow_version=str(run.workflow_version),
        status=str(run.status),
    )


def _source_signature(source: GovernedKnowledgeSourceSnapshot | None):
    if source is None:
        return None
    return (
        source.source_uid,
        source.parse_uid,
        source.source_version,
        source.course,
        source.chapter,
        source.source_status,
        source.source_trust_level,
        source.parse_status,
        source.parse_quality,
        source.usable_chunk_count,
    )


def _chunk_signature(chunks: Iterable[GovernedSourceChunkSnapshot]):
    return tuple(
        sorted(
            (
                chunk.chunk_uid,
                chunk.source_uid,
                chunk.parse_uid,
                chunk.source_version,
                chunk.chunk_index,
                chunk.language,
            )
            for chunk in chunks
        )
    )


def _source_matches_run(source: GovernedKnowledgeSourceSnapshot | None, run: _RunSnapshot) -> bool:
    return bool(
        source
        and source.source_uid == run.source_uid
        and source.parse_uid == run.parse_uid
        and source.source_version == run.source_version
        and source.source_status == "active"
        and source.parse_status in {"success", "succeeded"}
        and source.parse_quality in {"ready", "native_text_ok", "ocr_text_ok", "partial_text"}
        and source.usable_chunk_count > 0
    )


def _lease_result_outcome(outcome: str) -> str:
    if outcome == LEASE_OUTCOME_LEASE_NOT_OWNED:
        return BOOTSTRAP_OUTCOME_LEASE_NOT_OWNED
    if outcome == LEASE_OUTCOME_LEASE_EXPIRED:
        return BOOTSTRAP_OUTCOME_LEASE_EXPIRED
    if outcome == LEASE_OUTCOME_STALE_ATTEMPT:
        return BOOTSTRAP_OUTCOME_STALE_ATTEMPT
    return BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR


def _block_root(
    run: Any,
    *,
    code: str,
    message: str,
    now_text: str,
    warning_count: int = 0,
):
    run.status = ROOT_STATUS_BLOCKED
    run.stage = ROOT_STAGE_TERMINAL
    run.total_items = 0
    run.warning_count = warning_count
    run.error_code = code
    run.error_message = _safe_message(message, "Document alignment item bootstrap was blocked.")
    run.finished_at = now_text


def _job_matches_command(job: Any, command: BootstrapDocumentAlignmentItemsCommand, workflow_version: str) -> bool:
    if job is None or str(job.job_type) != FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE:
        return False
    try:
        payload = json.loads(job.input_json or "{}")
    except (TypeError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and str(payload.get("workflow_run_uid") or "") == command.workflow_run_uid
        and str(payload.get("workflow_version") or "") == workflow_version
    )


def _persist_blocked_extraction(
    command: BootstrapDocumentAlignmentItemsCommand,
    dependencies: BootstrapDocumentAlignmentItemsDependencies,
    run: Any,
    extraction: ChunkScopedTermCandidateExtractionResult,
    now_text: str,
):
    mapping = {
        EXTRACTION_OUTCOME_NO_CANDIDATES: (
            BOOTSTRAP_OUTCOME_NO_CANDIDATES,
            ERROR_NO_CANDIDATES,
            "No governed term candidates were extracted.",
        ),
        EXTRACTION_OUTCOME_ITEM_LIMIT_EXCEEDED: (
            BOOTSTRAP_OUTCOME_ITEM_LIMIT_EXCEEDED,
            ERROR_ITEM_LIMIT,
            extraction.error_message,
        ),
        EXTRACTION_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED: (
            BOOTSTRAP_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED,
            ERROR_SCOPE_LIMIT,
            extraction.error_message,
        ),
        EXTRACTION_OUTCOME_INVALID_CHUNK_SCOPE: (
            BOOTSTRAP_OUTCOME_SOURCE_CHANGED,
            ERROR_SOURCE_CHANGED,
            "Governed chunk scope changed before item persistence.",
        ),
    }
    outcome, code, message = mapping.get(
        extraction.outcome,
        (BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR, ERROR_PERSISTENCE, "Term extraction did not produce a usable result."),
    )
    _block_root(run, code=code, message=message, now_text=now_text, warning_count=extraction.warning_count)
    dependencies.session.commit()
    return _result(
        command,
        outcome,
        run_status=run.status,
        run_stage=run.stage,
        candidate_count=extraction.canonical_candidate_count,
        warning_count=extraction.warning_count,
        error_code=code,
        error_message=message,
    )


def _persist_candidates(
    command: BootstrapDocumentAlignmentItemsCommand,
    dependencies: BootstrapDocumentAlignmentItemsDependencies,
    run: Any,
    extraction: ChunkScopedTermCandidateExtractionResult,
    now_text: str,
):
    candidates = extraction.candidates
    warning_count = extraction.warning_count
    model = dependencies.workflow_item_model
    expected_keys = {
        dependencies.item_key_builder(candidate.normalized_term, candidate.source_chunk_uids): candidate
        for candidate in candidates
    }
    existing = (
        dependencies.session.query(model)
        .filter(model.workflow_run_id == run.id)
        .all()
    )
    existing_by_key = {str(item.item_key): item for item in existing}
    if set(existing_by_key) - set(expected_keys):
        _block_root(
            run,
            code=ERROR_SOURCE_CHANGED,
            message="Existing workflow items no longer match the governed candidate scope.",
            now_text=now_text,
        )
        dependencies.session.commit()
        return _result(
            command,
            BOOTSTRAP_OUTCOME_SOURCE_CHANGED,
            run_status=run.status,
            run_stage=run.stage,
            error_code=ERROR_SOURCE_CHANGED,
            error_message="Existing workflow items no longer match the governed candidate scope.",
        )

    created = 0
    reused = 0
    for item_key, candidate in expected_keys.items():
        item = existing_by_key.get(item_key)
        refs = _json_list(candidate.source_chunk_uids)
        risks = _json_list(candidate.risk_labels)
        if item is not None:
            if (
                str(item.candidate_term) != candidate.candidate_term
                or str(item.normalized_term) != candidate.normalized_term
                or str(item.source_chunk_refs) != refs
            ):
                _block_root(
                    run,
                    code=ERROR_ITEM_IDEMPOTENCY_CONFLICT,
                    message="An existing workflow item conflicts with the canonical candidate.",
                    now_text=now_text,
                )
                dependencies.session.commit()
                return _result(
                    command,
                    BOOTSTRAP_OUTCOME_ITEM_IDEMPOTENCY_CONFLICT,
                    run_status=run.status,
                    run_stage=run.stage,
                    error_code=ERROR_ITEM_IDEMPOTENCY_CONFLICT,
                    error_message="An existing workflow item conflicts with the canonical candidate.",
                )
            reused += 1
            continue
        dependencies.session.add(
            model(
                item_uid=_required_text(dependencies.item_uid_factory(), "item_uid", 64),
                workflow_run_id=run.id,
                item_key=item_key,
                candidate_term=candidate.candidate_term,
                normalized_term=candidate.normalized_term,
                source_chunk_refs=refs,
                status=ITEM_STATUS_CANDIDATE,
                stage=ITEM_STAGE_CANDIDATE,
                risk_labels=risks,
                warning_count=len(candidate.risk_labels),
                retry_count=0,
                created_at=now_text,
                updated_at=now_text,
            )
        )
        created += 1

    run.status = ROOT_STATUS_PROCESSING
    run.stage = ROOT_STAGE_EVIDENCE_RETRIEVAL
    run.total_items = len(expected_keys)
    run.warning_count = warning_count
    if extraction.overflow_candidates:
        run.risk_summary = json.dumps(
            {
                "candidate_set_overflow": {
                    "admitted_count": len(extraction.candidates),
                    "canonical_count": extraction.canonical_candidate_count,
                    "governance_reason": "candidate_set_item_limit_exceeded",
                    "item_limit": extraction.item_limit,
                    "overflow_candidates": [
                        {
                            "candidate_id": candidate.candidate_id,
                            "governance_reason": candidate.governance_reason,
                            "normalized_term": candidate.normalized_term,
                            "source_chunk_uids": list(candidate.source_chunk_uids),
                            "source_uid": candidate.source_uid,
                        }
                        for candidate in extraction.overflow_candidates
                    ],
                    "overflow_count": len(extraction.overflow_candidates),
                    "selection_order": "first_chunk_index,normalized_term,candidate_term",
                }
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    run.error_code = ""
    run.error_message = ""
    run.started_at = run.started_at or now_text
    run.finished_at = ""
    dependencies.session.commit()
    outcome = BOOTSTRAP_OUTCOME_CREATED if created else BOOTSTRAP_OUTCOME_REUSED
    return _result(
        command,
        outcome,
        run_status=run.status,
        run_stage=run.stage,
        candidate_count=len(candidates),
        canonical_candidate_count=extraction.canonical_candidate_count,
        admitted_candidate_count=len(candidates),
        overflow_candidate_count=len(extraction.overflow_candidates),
        overflow_candidate_ids=tuple(
            candidate.candidate_id for candidate in extraction.overflow_candidates
        ),
        governance_status=extraction.governance_status,
        created_item_count=created,
        reused_item_count=reused,
        warning_count=warning_count,
    )


def _fenced_persistence(
    command: BootstrapDocumentAlignmentItemsCommand,
    dependencies: BootstrapDocumentAlignmentItemsDependencies,
    initial_run: _RunSnapshot,
    initial_source: GovernedKnowledgeSourceSnapshot,
    initial_chunks: tuple[GovernedSourceChunkSnapshot, ...],
    extraction: ChunkScopedTermCandidateExtractionResult,
):
    now = dependencies.current_time_factory().replace(tzinfo=None)
    fence = FormalJobExecutionFence(
        job_uid=command.job_uid,
        worker_id=command.worker_id,
        execution_attempt=command.execution_attempt,
        lease_token=command.lease_token,
    )
    ownership = dependencies.lease_fence(
        fence,
        FormalBackgroundJobExecutionDependencies(
            session=dependencies.session,
            job_model=dependencies.background_job_model,
            current_time_factory=lambda: now,
        ),
    )
    if ownership.outcome != LEASE_OUTCOME_ACCEPTED:
        dependencies.session.rollback()
        return _result(
            command,
            _lease_result_outcome(ownership.outcome),
            error_code=ownership.error_code,
            error_message=ownership.error_message,
        )

    run = (
        dependencies.session.query(dependencies.workflow_run_model)
        .filter(dependencies.workflow_run_model.run_uid == command.workflow_run_uid)
        .one_or_none()
    )
    job = (
        dependencies.session.query(dependencies.background_job_model)
        .filter(dependencies.background_job_model.job_uid == command.job_uid)
        .one_or_none()
    )
    if run is None or run.status not in _BOOTSTRAP_ALLOWED_STATUSES or not _job_matches_command(job, command, dependencies.workflow_version):
        dependencies.session.rollback()
        return _result(
            command,
            BOOTSTRAP_OUTCOME_INVALID_RUN_STATE,
            error_code=ERROR_INVALID_RUN_STATE,
            error_message="Workflow run or job is not valid for item bootstrap.",
        )

    current_snapshot = _run_snapshot(run)
    source = dependencies.source_loader(dependencies.session, current_snapshot.source_uid)
    chunks = tuple(dependencies.chunk_loader(dependencies.session, source)) if source is not None else ()
    source_changed = (
        current_snapshot.workflow_version != dependencies.workflow_version
        or current_snapshot.source_uid != initial_run.source_uid
        or current_snapshot.parse_uid != initial_run.parse_uid
        or current_snapshot.source_version != initial_run.source_version
        or _source_signature(source) != _source_signature(initial_source)
        or _chunk_signature(chunks) != _chunk_signature(initial_chunks)
        or not _source_matches_run(source, current_snapshot)
    )
    now_text = _time_text(now)
    if source_changed:
        _block_root(
            run,
            code=ERROR_SOURCE_CHANGED,
            message="Governed source or chunk scope changed before item persistence.",
            now_text=now_text,
        )
        dependencies.session.commit()
        return _result(
            command,
            BOOTSTRAP_OUTCOME_SOURCE_CHANGED,
            run_status=run.status,
            run_stage=run.stage,
            error_code=ERROR_SOURCE_CHANGED,
            error_message="Governed source or chunk scope changed before item persistence.",
        )

    if extraction.outcome != EXTRACTION_OUTCOME_EXTRACTED:
        if extraction.outcome == EXTRACTION_OUTCOME_EXTRACTION_FAILED:
            dependencies.session.rollback()
            return _result(
                command,
                BOOTSTRAP_OUTCOME_EXTRACTION_FAILED,
                canonical_candidate_count=extraction.canonical_candidate_count,
                error_code=extraction.error_code,
                error_message=extraction.error_message,
            )
        return _persist_blocked_extraction(command, dependencies, run, extraction, now_text)
    return _persist_candidates(command, dependencies, run, extraction, now_text)


def bootstrap_document_alignment_workflow_items(
    command: BootstrapDocumentAlignmentItemsCommand,
    dependencies: BootstrapDocumentAlignmentItemsDependencies,
) -> BootstrapDocumentAlignmentItemsResult:
    """Build formal workflow items without invoking downstream execution."""

    try:
        run = (
            dependencies.session.query(dependencies.workflow_run_model)
            .filter(dependencies.workflow_run_model.run_uid == command.workflow_run_uid)
            .one_or_none()
        )
        if run is None or run.status not in _BOOTSTRAP_ALLOWED_STATUSES or run.workflow_version != dependencies.workflow_version:
            dependencies.session.rollback()
            return _result(
                command,
                BOOTSTRAP_OUTCOME_INVALID_RUN_STATE,
                error_code=ERROR_INVALID_RUN_STATE,
                error_message="Workflow run is not valid for item bootstrap.",
            )
        if run.status == ROOT_STATUS_PROCESSING:
            existing_count = (
                dependencies.session.query(dependencies.workflow_item_model)
                .filter(dependencies.workflow_item_model.workflow_run_id == run.id)
                .count()
            )
            if existing_count <= 0 or int(run.total_items or 0) != existing_count:
                dependencies.session.rollback()
                return _result(
                    command,
                    BOOTSTRAP_OUTCOME_INVALID_RUN_STATE,
                    error_code=ERROR_INVALID_RUN_STATE,
                    error_message="Processing workflow does not have a complete bootstrap item set.",
                )
        run_snapshot = _run_snapshot(run)
        source = dependencies.source_loader(dependencies.session, run_snapshot.source_uid)
        if source is None or (
            source.source_uid != run_snapshot.source_uid
            or source.parse_uid != run_snapshot.parse_uid
            or source.source_version != run_snapshot.source_version
            or source.source_status != "active"
        ):
            dependencies.session.rollback()
            return _result(
                command,
                BOOTSTRAP_OUTCOME_SOURCE_CHANGED,
                error_code=ERROR_SOURCE_CHANGED,
                error_message="Governed source is no longer valid for item bootstrap.",
            )
        if (
            source.parse_status not in {"success", "succeeded"}
            or source.parse_quality not in {"ready", "native_text_ok", "ocr_text_ok", "partial_text"}
            or source.usable_chunk_count <= 0
        ):
            dependencies.session.rollback()
            return _result(
                command,
                BOOTSTRAP_OUTCOME_PARSE_BLOCKED,
                error_code=ERROR_PARSE_BLOCKED,
                error_message="Governed source parse is not eligible for item bootstrap.",
            )
        chunks = tuple(dependencies.chunk_loader(dependencies.session, source))
        source_signature = _source_signature(source)
        chunk_signature = _chunk_signature(chunks)
        dependencies.session.rollback()

        extraction = dependencies.candidate_extractor(
            chunks,
            dependencies.term_extractor,
            expected_source_uid=run_snapshot.source_uid,
            expected_parse_uid=run_snapshot.parse_uid,
            expected_source_version=run_snapshot.source_version,
        )
        if _source_signature(source) != source_signature or _chunk_signature(chunks) != chunk_signature:
            return _result(
                command,
                BOOTSTRAP_OUTCOME_SOURCE_CHANGED,
                error_code=ERROR_SOURCE_CHANGED,
                error_message="Governed source changed during term extraction.",
            )
        try:
            return _fenced_persistence(command, dependencies, run_snapshot, source, chunks, extraction)
        except dependencies.integrity_error_type as exc:
            dependencies.session.rollback()
            if not dependencies.item_key_integrity_error_matcher(exc):
                return _result(
                    command,
                    BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR,
                    error_code=ERROR_PERSISTENCE,
                    error_message="Workflow items could not be saved.",
                )
            try:
                return _fenced_persistence(command, dependencies, run_snapshot, source, chunks, extraction)
            except Exception:
                dependencies.session.rollback()
                return _result(
                    command,
                    BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR,
                    error_code=ERROR_PERSISTENCE,
                    error_message="Workflow item conflict could not be resolved safely.",
                )
    except Exception:
        dependencies.session.rollback()
        return _result(
            command,
            BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR,
            error_code=ERROR_PERSISTENCE,
            error_message="Document alignment item bootstrap failed.",
        )
