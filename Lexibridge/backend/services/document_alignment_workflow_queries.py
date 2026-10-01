"""Read-only queries for formal document alignment workflow state."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Optional

from services.document_alignment_workflow_contract import (
    DOCUMENT_ALIGNMENT_ITEM_STATUSES,
    ITEM_STATUS_BLOCKED,
    ITEM_STATUS_FAILED,
    ITEM_STATUS_NEEDS_REVIEW,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_FAILED,
    ROOT_STATUS_READY_FOR_REVIEW,
)


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_SAFE_ERROR_MESSAGE_LENGTH = 500
MAX_SAFE_TEXT_LENGTH = 500

QUERY_OUTCOME_FOUND = "found"
QUERY_OUTCOME_NOT_FOUND = "not_found"
QUERY_OUTCOME_FORBIDDEN = "forbidden"
QUERY_OUTCOME_INVALID_REQUEST = "invalid_request"
QUERY_OUTCOME_PERSISTENCE_ERROR = "persistence_error"

QUERY_ERROR_INVALID_REQUEST = "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST"
QUERY_ERROR_NOT_FOUND = "DOCUMENT_ALIGNMENT_WORKFLOW_NOT_FOUND"
QUERY_ERROR_PERSISTENCE = "DOCUMENT_ALIGNMENT_QUERY_PERSISTENCE_ERROR"
QUERY_DATA_INCONSISTENT = "DOCUMENT_ALIGNMENT_QUERY_DATA_INCONSISTENT"

_ROOT_TERMINAL_STATUSES = frozenset({
    ROOT_STATUS_READY_FOR_REVIEW,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_FAILED,
})
_ITEM_TERMINAL_STATUSES = frozenset({
    ITEM_STATUS_NEEDS_REVIEW,
    ITEM_STATUS_BLOCKED,
    ITEM_STATUS_FAILED,
})
_COURSE_TEACHER_ROLES = frozenset({"teacher", "owner", "admin"})
_PRIVATE_VISIBILITIES = frozenset({"private", "personal"})
_SECRET_MARKERS = (
    "lexibridge_sentinel_secret",
    "authorization",
    "bearer ",
    "cookie",
    "api_key",
    "api-key",
    "password",
    "secret=",
    "token=",
    "sk-",
)
_CONTENT_SECRET_MARKERS = (
    "lexibridge_sentinel_secret",
    "authorization:",
    "bearer ",
    "cookie:",
    "sk-",
)
_CONFIDENCE_SUMMARY_KEYS = frozenset({
    "alignment_confidence",
    "confidence",
    "label",
    "level",
    "model_identity",
    "provider_name",
    "score",
})


@dataclass(frozen=True)
class DocumentAlignmentQueryActor:
    actor_uid: str
    role: str


@dataclass(frozen=True)
class DocumentAlignmentWorkflowQueryModels:
    workflow_run: Any
    workflow_item: Any
    knowledge_source: Any
    course: Any
    course_member: Any


@dataclass(frozen=True)
class DocumentAlignmentWorkflowQueryDependencies:
    session: Any
    models: DocumentAlignmentWorkflowQueryModels

    @classmethod
    def from_app_module(cls, module: Any) -> "DocumentAlignmentWorkflowQueryDependencies":
        return cls(
            session=module.db.session,
            models=DocumentAlignmentWorkflowQueryModels(
                workflow_run=module.DocumentAlignmentWorkflowRun,
                workflow_item=module.DocumentAlignmentWorkflowItem,
                knowledge_source=module.KnowledgeSource,
                course=module.Course,
                course_member=module.CourseMember,
            ),
        )


@dataclass(frozen=True)
class GetDocumentAlignmentWorkflowRunCommand:
    run_uid: str
    actor: DocumentAlignmentQueryActor


@dataclass(frozen=True)
class ListDocumentAlignmentWorkflowItemsCommand:
    run_uid: str
    actor: DocumentAlignmentQueryActor
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    status: str = ""
    reviewable_only: bool = False


@dataclass(frozen=True)
class DocumentAlignmentWorkflowRunSummary:
    run_uid: str
    workflow_version: str
    status: str
    stage: str
    source_uid: str
    source_title: str
    source_filename: str
    course: str
    chapter: str
    requested_by: str
    created_at: str
    started_at: str
    finished_at: str
    total_items: int
    ready_for_review_items: int
    blocked_items: int
    failed_items: int
    warning_count: int
    progress_percent: int
    safe_error_code: str
    safe_error_message: str
    consistency_warnings: tuple[str, ...]
    is_terminal: bool
    can_view_items: bool
    can_review_results: bool


@dataclass(frozen=True)
class DocumentAlignmentWorkflowItemSummary:
    item_uid: str
    candidate_term: str
    normalized_term: str
    status: str
    stage: str
    source_chunk_count: int
    risk_labels: tuple[str, ...]
    draft_card_uid: Optional[str]
    verification_run_uid: Optional[str]
    confidence_score: Optional[float]
    confidence_summary: Optional[dict[str, Any]]
    recommendation: Optional[str]
    safe_error_code: str
    safe_error_message: str
    retry_count: int
    created_at: str
    updated_at: str
    consistency_warnings: tuple[str, ...]
    is_terminal: bool
    is_reviewable: bool


@dataclass(frozen=True)
class DocumentAlignmentWorkflowItemPage:
    workflow_run_uid: str
    items: tuple[DocumentAlignmentWorkflowItemSummary, ...]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


@dataclass(frozen=True)
class GetDocumentAlignmentWorkflowRunResult:
    outcome: str
    run: Optional[DocumentAlignmentWorkflowRunSummary] = None
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class ListDocumentAlignmentWorkflowItemsResult:
    outcome: str
    page: Optional[DocumentAlignmentWorkflowItemPage] = None
    error_code: str = ""
    error_message: str = ""


def _contains_secret(value: Any) -> bool:
    text = str(value or "").casefold()
    return any(marker in text for marker in _SECRET_MARKERS)


def _safe_text(value: Any, limit: int = MAX_SAFE_TEXT_LENGTH, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text or _contains_secret(text):
        return fallback
    return text[:limit]


def _safe_content_text(value: Any, limit: int = MAX_SAFE_TEXT_LENGTH, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    folded = text.casefold()
    if not text or any(marker in folded for marker in _CONTENT_SECRET_MARKERS):
        return fallback
    return text[:limit]


def _safe_error_message(value: Any) -> str:
    return _safe_text(
        value,
        MAX_SAFE_ERROR_MESSAGE_LENGTH,
        fallback="Workflow processing error details are unavailable.",
    ) if value else ""


def _safe_reference(value: Any) -> Optional[str]:
    text = _safe_text(value, 120)
    return text or None


def _safe_filename(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/")
    return _safe_content_text(normalized.rsplit("/", 1)[-1], 260)


def _json_value(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value, 160)
    return None


def _safe_summary(value: Any) -> Optional[dict[str, Any]]:
    parsed = _json_value(value, {})
    if not isinstance(parsed, dict) or _contains_secret(value):
        return None
    summary = {}
    for key in sorted(set(parsed) & _CONFIDENCE_SUMMARY_KEYS):
        safe_key = _safe_text(key, 80)
        safe_value = _safe_scalar(parsed[key])
        if safe_key and safe_value not in (None, ""):
            summary[safe_key] = safe_value
    return summary or None


def _safe_risk_labels(value: Any) -> tuple[str, ...]:
    parsed = _json_value(value, [])
    if not isinstance(parsed, list) or _contains_secret(value):
        return ()
    labels = {
        _safe_text(label, 80)
        for label in parsed
        if isinstance(label, str) and _safe_text(label, 80)
    }
    return tuple(sorted(labels))


def _reference_count(value: Any) -> int:
    parsed = _json_value(value, [])
    if not isinstance(parsed, list):
        return 0
    return len({str(reference).strip() for reference in parsed if str(reference).strip()})


def _valid_actor(actor: Any) -> bool:
    return (
        isinstance(actor, DocumentAlignmentQueryActor)
        and len(str(actor.actor_uid or "").strip()) <= 120
        and len(str(actor.role or "").strip()) <= 30
    )


def _actor_database_id(actor: DocumentAlignmentQueryActor) -> Optional[int]:
    try:
        value = int(str(actor.actor_uid).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _load_source(session: Any, source_model: Any, source_uid: str) -> Any:
    return session.query(source_model).filter(source_model.source_uid == source_uid).first()


def _is_authorized(
    session: Any,
    models: DocumentAlignmentWorkflowQueryModels,
    actor: DocumentAlignmentQueryActor,
    run: Any,
    source: Any,
) -> bool:
    role = str(actor.role or "").strip()
    actor_uid = str(actor.actor_uid or "").strip()
    if role == "admin":
        return True
    if role != "teacher" or source is None:
        return False

    actor_id = _actor_database_id(actor)
    visibility = str(getattr(source, "visibility", "") or "").strip().casefold()
    if visibility in _PRIVATE_VISIBILITIES:
        if actor_id is None or int(getattr(source, "owner_user_id", 0) or 0) != actor_id:
            return False

    if str(getattr(run, "requested_by", "") or "").strip() == actor_uid:
        return True
    if actor_id is None:
        return False

    course = None
    source_course_id = int(getattr(source, "course_id", 0) or 0)
    if source_course_id:
        course = session.query(models.course).filter(models.course.id == source_course_id).first()
    if course is None:
        course_name = str(getattr(run, "course", "") or getattr(source, "course", "") or "").strip()
        if course_name:
            course = session.query(models.course).filter(models.course.name == course_name).first()
    if course is None:
        return False
    if int(getattr(course, "teacher_id", 0) or 0) == actor_id:
        return True
    membership = (
        session.query(models.course_member)
        .filter(
            models.course_member.course_id == course.id,
            models.course_member.user_id == actor_id,
            models.course_member.status == "active",
            models.course_member.role_in_course.in_(_COURSE_TEACHER_ROLES),
        )
        .first()
    )
    return membership is not None


def _progress_percent(run: Any) -> int:
    if str(getattr(run, "status", "") or "") in _ROOT_TERMINAL_STATUSES:
        return 100
    total = max(0, int(getattr(run, "total_items", 0) or 0))
    if total == 0:
        return 0
    completed = sum(
        max(0, int(getattr(run, field_name, 0) or 0))
        for field_name in ("ready_for_review_items", "blocked_items", "failed_items")
    )
    return max(0, min(100, math.floor(completed * 100 / total)))


def _run_consistency_warnings(session: Any, models: DocumentAlignmentWorkflowQueryModels, run: Any) -> tuple[str, ...]:
    total = int(getattr(run, "total_items", 0) or 0)
    counts = [
        int(getattr(run, field_name, 0) or 0)
        for field_name in ("ready_for_review_items", "blocked_items", "failed_items")
    ]
    inconsistent = total < 0 or any(value < 0 or value > total for value in counts) or sum(counts) > total
    if str(getattr(run, "status", "") or "") in _ROOT_TERMINAL_STATUSES:
        nonterminal_count = (
            session.query(models.workflow_item.id)
            .filter(
                models.workflow_item.workflow_run_id == run.id,
                ~models.workflow_item.status.in_(_ITEM_TERMINAL_STATUSES),
            )
            .count()
        )
        inconsistent = inconsistent or nonterminal_count > 0
    return (QUERY_DATA_INCONSISTENT,) if inconsistent else ()


def _item_consistency_warnings(item: Any) -> tuple[str, ...]:
    status = str(getattr(item, "status", "") or "")
    draft_uid = str(getattr(item, "draft_card_uid", "") or "").strip()
    verification_uid = str(getattr(item, "verification_run_uid", "") or "").strip()
    inconsistent = False
    if status in {"draft_created", "verification_completed", ITEM_STATUS_NEEDS_REVIEW} and not draft_uid:
        inconsistent = True
    if status in {"verification_completed", ITEM_STATUS_NEEDS_REVIEW} and not verification_uid:
        inconsistent = True
    return (QUERY_DATA_INCONSISTENT,) if inconsistent else ()


def _not_found_run() -> GetDocumentAlignmentWorkflowRunResult:
    return GetDocumentAlignmentWorkflowRunResult(
        outcome=QUERY_OUTCOME_NOT_FOUND,
        error_code=QUERY_ERROR_NOT_FOUND,
        error_message="Workflow run was not found.",
    )


def _not_found_items() -> ListDocumentAlignmentWorkflowItemsResult:
    return ListDocumentAlignmentWorkflowItemsResult(
        outcome=QUERY_OUTCOME_NOT_FOUND,
        error_code=QUERY_ERROR_NOT_FOUND,
        error_message="Workflow run was not found.",
    )


def _run_summary(
    session: Any,
    models: DocumentAlignmentWorkflowQueryModels,
    run: Any,
    source: Any,
) -> DocumentAlignmentWorkflowRunSummary:
    status = str(getattr(run, "status", "") or "")
    return DocumentAlignmentWorkflowRunSummary(
        run_uid=_safe_text(run.run_uid, 64),
        workflow_version=_safe_text(run.workflow_version, 80),
        status=_safe_text(status, 40),
        stage=_safe_text(run.stage, 80),
        source_uid=_safe_text(run.source_uid, 64),
        source_title=_safe_content_text(
            getattr(source, "title", "") or getattr(source, "source_title", "") or getattr(source, "name", ""),
            220,
            fallback="Untitled source",
        ),
        source_filename=_safe_filename(getattr(source, "source_filename", "")),
        course=_safe_content_text(run.course, 160),
        chapter=_safe_content_text(run.chapter, 160),
        requested_by=_safe_text(run.requested_by, 120),
        created_at=_safe_text(run.created_at, 40),
        started_at=_safe_text(run.started_at, 40),
        finished_at=_safe_text(run.finished_at, 40),
        total_items=max(0, int(run.total_items or 0)),
        ready_for_review_items=max(0, int(run.ready_for_review_items or 0)),
        blocked_items=max(0, int(run.blocked_items or 0)),
        failed_items=max(0, int(run.failed_items or 0)),
        warning_count=max(0, int(run.warning_count or 0)),
        progress_percent=_progress_percent(run),
        safe_error_code=_safe_text(run.error_code, 120),
        safe_error_message=_safe_error_message(run.error_message),
        consistency_warnings=_run_consistency_warnings(session, models, run),
        is_terminal=status in _ROOT_TERMINAL_STATUSES,
        can_view_items=True,
        can_review_results=True,
    )


def _item_summary(item: Any) -> DocumentAlignmentWorkflowItemSummary:
    status = str(getattr(item, "status", "") or "")
    confidence = getattr(item, "confidence_score", None)
    return DocumentAlignmentWorkflowItemSummary(
        item_uid=_safe_text(item.item_uid, 64),
        candidate_term=_safe_content_text(item.candidate_term, 220),
        normalized_term=_safe_content_text(item.normalized_term, 220),
        status=_safe_text(status, 40),
        stage=_safe_text(item.stage, 80),
        source_chunk_count=_reference_count(item.source_chunk_refs),
        risk_labels=_safe_risk_labels(item.risk_labels),
        draft_card_uid=_safe_reference(item.draft_card_uid),
        verification_run_uid=_safe_reference(item.verification_run_uid),
        confidence_score=float(confidence) if confidence is not None else None,
        confidence_summary=_safe_summary(item.confidence_summary) if confidence is not None else None,
        recommendation=_safe_reference(item.recommendation),
        safe_error_code=_safe_text(item.error_code, 120),
        safe_error_message=_safe_error_message(item.error_message),
        retry_count=max(0, int(item.retry_count or 0)),
        created_at=_safe_text(item.created_at, 40),
        updated_at=_safe_text(item.updated_at, 40),
        consistency_warnings=_item_consistency_warnings(item),
        is_terminal=status in _ITEM_TERMINAL_STATUSES,
        is_reviewable=status == ITEM_STATUS_NEEDS_REVIEW,
    )


def get_document_alignment_workflow_run(
    command: GetDocumentAlignmentWorkflowRunCommand,
    dependencies: DocumentAlignmentWorkflowQueryDependencies,
) -> GetDocumentAlignmentWorkflowRunResult:
    if not isinstance(command, GetDocumentAlignmentWorkflowRunCommand):
        return GetDocumentAlignmentWorkflowRunResult(
            QUERY_OUTCOME_INVALID_REQUEST,
            error_code=QUERY_ERROR_INVALID_REQUEST,
            error_message="Invalid query request.",
        )
    run_uid = str(command.run_uid or "").strip()
    if not run_uid or len(run_uid) > 64 or not _valid_actor(command.actor):
        return GetDocumentAlignmentWorkflowRunResult(
            QUERY_OUTCOME_INVALID_REQUEST,
            error_code=QUERY_ERROR_INVALID_REQUEST,
            error_message="Invalid query request.",
        )
    session = dependencies.session
    models = dependencies.models
    try:
        with session.no_autoflush:
            run = session.query(models.workflow_run).filter(models.workflow_run.run_uid == run_uid).first()
            if run is None:
                return _not_found_run()
            source = _load_source(session, models.knowledge_source, run.source_uid)
            if not _is_authorized(session, models, command.actor, run, source):
                return _not_found_run()
            return GetDocumentAlignmentWorkflowRunResult(
                outcome=QUERY_OUTCOME_FOUND,
                run=_run_summary(session, models, run, source),
            )
    except Exception:
        session.rollback()
        return GetDocumentAlignmentWorkflowRunResult(
            outcome=QUERY_OUTCOME_PERSISTENCE_ERROR,
            error_code=QUERY_ERROR_PERSISTENCE,
            error_message="Workflow state could not be read.",
        )


def list_document_alignment_workflow_items(
    command: ListDocumentAlignmentWorkflowItemsCommand,
    dependencies: DocumentAlignmentWorkflowQueryDependencies,
) -> ListDocumentAlignmentWorkflowItemsResult:
    if not isinstance(command, ListDocumentAlignmentWorkflowItemsCommand):
        return ListDocumentAlignmentWorkflowItemsResult(
            QUERY_OUTCOME_INVALID_REQUEST,
            error_code=QUERY_ERROR_INVALID_REQUEST,
            error_message="Invalid query request.",
        )
    run_uid = str(command.run_uid or "").strip()
    valid_pagination = (
        isinstance(command.page, int)
        and not isinstance(command.page, bool)
        and command.page >= 1
        and isinstance(command.page_size, int)
        and not isinstance(command.page_size, bool)
        and 1 <= command.page_size <= MAX_PAGE_SIZE
    )
    status = str(command.status or "").strip()
    if (
        not run_uid
        or len(run_uid) > 64
        or not _valid_actor(command.actor)
        or not valid_pagination
        or (status and status not in DOCUMENT_ALIGNMENT_ITEM_STATUSES)
        or not isinstance(command.reviewable_only, bool)
    ):
        return ListDocumentAlignmentWorkflowItemsResult(
            QUERY_OUTCOME_INVALID_REQUEST,
            error_code=QUERY_ERROR_INVALID_REQUEST,
            error_message="Invalid query request.",
        )

    session = dependencies.session
    models = dependencies.models
    try:
        with session.no_autoflush:
            run = session.query(models.workflow_run).filter(models.workflow_run.run_uid == run_uid).first()
            if run is None:
                return _not_found_items()
            source = _load_source(session, models.knowledge_source, run.source_uid)
            if not _is_authorized(session, models, command.actor, run, source):
                return _not_found_items()

            query = session.query(models.workflow_item).filter(models.workflow_item.workflow_run_id == run.id)
            if status:
                query = query.filter(models.workflow_item.status == status)
            if command.reviewable_only:
                query = query.filter(models.workflow_item.status == ITEM_STATUS_NEEDS_REVIEW)
            total_items = query.order_by(None).count()
            rows = (
                query.order_by(models.workflow_item.id.asc(), models.workflow_item.item_key.asc())
                .offset((command.page - 1) * command.page_size)
                .limit(command.page_size)
                .all()
            )
            total_pages = math.ceil(total_items / command.page_size) if total_items else 0
            page = DocumentAlignmentWorkflowItemPage(
                workflow_run_uid=_safe_text(run.run_uid, 64),
                items=tuple(_item_summary(item) for item in rows),
                page=command.page,
                page_size=command.page_size,
                total_items=total_items,
                total_pages=total_pages,
                has_next=command.page < total_pages,
                has_previous=command.page > 1 and total_pages > 0,
            )
            return ListDocumentAlignmentWorkflowItemsResult(outcome=QUERY_OUTCOME_FOUND, page=page)
    except Exception:
        session.rollback()
        return ListDocumentAlignmentWorkflowItemsResult(
            outcome=QUERY_OUTCOME_PERSISTENCE_ERROR,
            error_code=QUERY_ERROR_PERSISTENCE,
            error_message="Workflow items could not be read.",
        )
