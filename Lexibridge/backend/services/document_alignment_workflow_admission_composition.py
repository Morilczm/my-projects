"""Production dependency composition for formal workflow admission.

The application service owns admission writes and transactions. This module
only adapts the existing governed-source and course-permission models into its
explicit loader and decision contracts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from services.document_alignment_workflow_application import (
    DocumentAlignmentSourceAdmissionDecision,
    DocumentAlignmentWorkflowApplicationDependencies,
    DocumentAlignmentWorkflowAuthorizationDecision,
    GovernedKnowledgeSourceSnapshot,
)
from services.formal_document_alignment_provider_selection import (
    resolve_default_formal_document_alignment_provider_selection,
    resolve_formal_document_alignment_provider_selection,
)


@dataclass(frozen=True)
class DocumentAlignmentWorkflowAdmissionModels:
    workflow_run: Any
    background_job: Any
    audit_record: Any
    knowledge_source: Any
    parse_record: Any
    knowledge_chunk: Any
    course: Any
    course_member: Any


def _source_not_available() -> DocumentAlignmentWorkflowAuthorizationDecision:
    return DocumentAlignmentWorkflowAuthorizationDecision(
        allowed=False,
        safe_error_code="DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE",
        safe_error_message="Source is not available.",
        outcome="source_not_available",
    )


def _load_source(session: Any, models: DocumentAlignmentWorkflowAdmissionModels, source_uid: str):
    source = session.query(models.knowledge_source).filter_by(source_uid=source_uid).one_or_none()
    if source is None:
        return None
    parse = session.query(models.parse_record).filter_by(parse_uid=source.parse_uid).one_or_none()
    usable_chunks = session.query(models.knowledge_chunk).filter_by(
        source_uid=source.source_uid,
        parse_uid=source.parse_uid,
        status="active",
        is_active=True,
    ).count()
    return GovernedKnowledgeSourceSnapshot(
        source_uid=source.source_uid,
        parse_uid=source.parse_uid,
        source_version=str(source.version or ""),
        course=source.course,
        chapter=source.chapter,
        owner_user_id=str(source.owner_user_id or ""),
        visibility=source.visibility,
        source_status=source.status,
        source_trust_level=source.trust_level,
        parse_status=getattr(parse, "parse_status", "") if parse else "",
        parse_quality=(getattr(parse, "quality_status", "") if parse else "")
        or str(getattr(source, "quality_status", "") or ""),
        usable_chunk_count=usable_chunks,
    )


def _teacher_can_manage_source(
    session: Any,
    models: DocumentAlignmentWorkflowAdmissionModels,
    user: Any,
    source: GovernedKnowledgeSourceSnapshot,
) -> bool:
    try:
        actor_id = int(getattr(user, "id", 0) or 0)
    except (TypeError, ValueError):
        return False
    if actor_id <= 0:
        return False
    try:
        if int(source.owner_user_id or 0) == actor_id:
            return True
    except (TypeError, ValueError):
        pass
    course = None
    if source.course:
        course = session.query(models.course).filter_by(name=source.course).one_or_none()
    if course is None:
        return False
    if int(getattr(course, "teacher_id", 0) or 0) == actor_id:
        return True
    return session.query(models.course_member).filter(
        models.course_member.course_id == course.id,
        models.course_member.user_id == actor_id,
        models.course_member.status == "active",
        models.course_member.role_in_course.in_(("teacher", "owner", "admin")),
    ).first() is not None


def _authorize_source(
    session: Any,
    models: DocumentAlignmentWorkflowAdmissionModels,
    user: Any,
    requested_by: str,
    source: GovernedKnowledgeSourceSnapshot,
) -> DocumentAlignmentWorkflowAuthorizationDecision:
    if str(getattr(user, "id", "") or "") != str(requested_by or ""):
        return _source_not_available()
    role = str(getattr(user, "role", "") or "")
    if role == "admin":
        return DocumentAlignmentWorkflowAuthorizationDecision(allowed=True)
    if role == "teacher" and _teacher_can_manage_source(session, models, user, source):
        return DocumentAlignmentWorkflowAuthorizationDecision(allowed=True)
    return _source_not_available()


def _admit_source(source: GovernedKnowledgeSourceSnapshot) -> DocumentAlignmentSourceAdmissionDecision:
    if source.source_status != "active":
        return DocumentAlignmentSourceAdmissionDecision(
            False,
            "DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE",
            "Source is not available.",
            "source_not_available",
        )
    if source.source_trust_level not in {"teacher_verified", "governed", "approved"}:
        return DocumentAlignmentSourceAdmissionDecision(
            False,
            "DOCUMENT_ALIGNMENT_SOURCE_NOT_GOVERNED",
            "Source is not governed.",
            "source_not_governed",
        )
    if source.parse_status != "success" or source.parse_quality not in {"native_text_ok", "ocr_text_ok", "partial_text"}:
        return DocumentAlignmentSourceAdmissionDecision(
            False,
            "DOCUMENT_ALIGNMENT_PARSE_BLOCKED",
            "Parse is blocked.",
            "parse_blocked",
        )
    if source.usable_chunk_count <= 0:
        return DocumentAlignmentSourceAdmissionDecision(
            False,
            "DOCUMENT_ALIGNMENT_NO_USABLE_CHUNKS",
            "No usable chunks.",
            "no_usable_chunks",
        )
    return DocumentAlignmentSourceAdmissionDecision(allowed=True)


def build_document_alignment_workflow_admission_dependencies(
    *,
    session: Any,
    models: DocumentAlignmentWorkflowAdmissionModels,
    user: Any,
    current_time_factory: Callable[[], str],
    uid_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    evaluation_context: Any = None,
) -> DocumentAlignmentWorkflowApplicationDependencies:
    provider_selection_resolver = resolve_default_formal_document_alignment_provider_selection
    if evaluation_context is not None:
        provider_selection_resolver = lambda: resolve_formal_document_alignment_provider_selection(
            evaluation_context.provider_name,
            evaluation_context=evaluation_context,
        )
    return DocumentAlignmentWorkflowApplicationDependencies(
        session=session,
        workflow_run_model=models.workflow_run,
        background_job_model=models.background_job,
        audit_record_model=models.audit_record,
        source_loader=lambda source_uid: _load_source(session, models, source_uid),
        authorization_checker=lambda requested_by, source: _authorize_source(
            session, models, user, requested_by, source
        ),
        source_admission_checker=_admit_source,
        current_time_factory=current_time_factory,
        uid_factory=uid_factory,
        provider_selection_resolver=provider_selection_resolver,
    )
