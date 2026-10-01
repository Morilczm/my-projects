"""Student-first workspace, role, and content boundary contracts.

This module is deliberately persistence-agnostic.  Task 13A establishes stable
product DTO and validation semantics without adding a parallel alignment/card
workflow or forcing a database migration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable


CONTRACT_VERSION = "student-first-boundaries@1.0.0"
STUDENT_ALIGNMENT_RESULT_CONTRACT_ID = "student-alignment-result@1.0.0"
MAX_EVIDENCE_ITEMS = 8
MAX_CANDIDATES = 8
MAX_SNIPPET_CHARS = 600


class BoundaryContractError(ValueError):
    """Raised when content crosses a workspace, authority, or role boundary."""


class WorkspaceScope(str, Enum):
    PERSONAL = "PERSONAL"
    MANAGED_COURSE = "MANAGED_COURSE"


class Visibility(str, Enum):
    PRIVATE = "PRIVATE"
    COURSE_SHARED = "COURSE_SHARED"


class Authority(str, Enum):
    NON_OFFICIAL = "NON_OFFICIAL"
    OFFICIAL = "OFFICIAL"


class AlignmentStatus(str, Enum):
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_READY = "NOT_READY"


class PublicationStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class ContentKind(str, Enum):
    PERSONAL_LEARNING_RESULT = "PERSONAL_LEARNING_RESULT"
    OFFICIAL_COURSE_CARD = "OFFICIAL_COURSE_CARD"


DISPLAY_MODES = {
    AlignmentStatus.READY: "EVIDENCE_BACKED_RECOMMENDATION",
    AlignmentStatus.REVIEW_REQUIRED: "EVIDENCE_BACKED_ALTERNATIVES",
    AlignmentStatus.NOT_READY: "NO_RELIABLE_ALIGNMENT",
}

ROLE_CAPABILITIES = {
    "student": frozenset({
        "USE_PERSONAL_WORKSPACE",
        "JOIN_MANAGED_COURSE_WORKSPACE",
        "QUERY_CONCEPT",
        "VIEW_OWN_ALIGNMENT_RESULT",
        "SUBMIT_ALIGNMENT_FEEDBACK",
    }),
    "teacher": frozenset({
        "MANAGE_MANAGED_COURSE",
        "MANAGE_ENGLISH_COURSE_MATERIALS",
        "MANAGE_COURSE_CHAPTERS",
        "VIEW_AGGREGATE_ENGLISH_LEARNING_ANALYTICS",
    }),
    "reviewer": frozenset({
        "REVIEW_BILINGUAL_ALIGNMENT_EXCEPTIONS",
        "REVIEW_STUDENT_ALIGNMENT_FEEDBACK",
        "REVIEW_OFFICIAL_COURSE_CARD",
    }),
    "admin": frozenset({
        "MANAGE_ACCOUNTS",
        "MANAGE_PERMISSIONS",
        "MANAGE_PROVIDER_CONFIGURATION",
        "MANAGE_POLICIES",
        "VIEW_SYSTEM_AUDIT",
    }),
}


@dataclass(frozen=True)
class ResultDimensions:
    workspace_scope: str
    visibility: str
    authority: str
    alignment_status: str
    publication_status: str
    content_kind: str


def _enum_value(enum_type, value: Any, field: str) -> str:
    text = str(value or "").strip().upper()
    try:
        return enum_type(text).value
    except ValueError as exc:
        raise BoundaryContractError(f"{field} is invalid.") from exc


def role_capabilities(role: Any) -> frozenset[str]:
    return ROLE_CAPABILITIES.get(str(role or "").strip().lower(), frozenset())


def validate_workspace_memberships(
    memberships: Iterable[dict[str, Any]], *, actor_uid: str
) -> list[dict[str, str]]:
    actor = str(actor_uid or "").strip()
    if not actor:
        raise BoundaryContractError("actor_uid is required.")
    result = []
    seen = set()
    for raw in memberships:
        if not isinstance(raw, dict):
            raise BoundaryContractError("workspace membership must be an object.")
        uid = str(raw.get("workspace_uid") or "").strip()
        scope = _enum_value(WorkspaceScope, raw.get("workspace_scope"), "workspace_scope")
        role = str(raw.get("member_role") or "").strip().upper()
        if not uid or not role:
            raise BoundaryContractError("workspace_uid and member_role are required.")
        key = (uid, scope, role)
        if key not in seen:
            seen.add(key)
            result.append({
                "workspace_uid": uid,
                "workspace_scope": scope,
                "member_role": role,
                "actor_uid": actor,
            })
    return result


def validate_result_dimensions(
    *,
    workspace_scope: Any,
    visibility: Any,
    authority: Any,
    alignment_status: Any,
    publication_status: Any,
    content_kind: Any,
    actor_role: Any = "",
    reviewer_decision_uid: Any = "",
) -> ResultDimensions:
    scope = _enum_value(WorkspaceScope, workspace_scope, "workspace_scope")
    visible = _enum_value(Visibility, visibility, "visibility")
    authoritative = _enum_value(Authority, authority, "authority")
    alignment = _enum_value(AlignmentStatus, alignment_status, "alignment_status")
    publication = _enum_value(PublicationStatus, publication_status, "publication_status")
    kind = _enum_value(ContentKind, content_kind, "content_kind")

    if scope == WorkspaceScope.PERSONAL.value and (
        visible == Visibility.COURSE_SHARED.value
        or authoritative == Authority.OFFICIAL.value
        or publication != PublicationStatus.NOT_APPLICABLE.value
    ):
        raise BoundaryContractError("Personal workspace content cannot be shared or official.")

    if kind == ContentKind.PERSONAL_LEARNING_RESULT.value:
        if visible != Visibility.PRIVATE.value or authoritative != Authority.NON_OFFICIAL.value:
            raise BoundaryContractError("Personal learning results are private and non-official.")
        if publication != PublicationStatus.NOT_APPLICABLE.value:
            raise BoundaryContractError("Personal learning results are not publishable objects.")

    if kind == ContentKind.OFFICIAL_COURSE_CARD.value:
        if scope != WorkspaceScope.MANAGED_COURSE.value:
            raise BoundaryContractError("Official course cards require a managed course workspace.")
        if visible != Visibility.COURSE_SHARED.value or authoritative != Authority.OFFICIAL.value:
            raise BoundaryContractError("Official course cards are course-shared and official.")
        if publication == PublicationStatus.NOT_APPLICABLE.value:
            raise BoundaryContractError("Official course cards require a publication state.")
        if str(actor_role or "").strip().lower() not in {"reviewer", "admin"}:
            raise BoundaryContractError("Only a Reviewer or Admin may establish official content.")
        if not str(reviewer_decision_uid or "").strip():
            raise BoundaryContractError("Official course cards require a reviewer decision.")

    if authoritative == Authority.NON_OFFICIAL.value and publication in {
        PublicationStatus.PUBLISHED.value,
        PublicationStatus.WITHDRAWN.value,
    }:
        raise BoundaryContractError("Non-official results cannot enter official publication states.")

    return ResultDimensions(scope, visible, authoritative, alignment, publication, kind)


def _bounded_evidence(value: Any) -> list[dict[str, Any]]:
    output = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        output.append({
            "source_uid": str(raw.get("source_uid") or "").strip(),
            "chunk_uid": str(raw.get("chunk_uid") or "").strip(),
            "page_number": raw.get("page_number"),
            "block_uid": str(raw.get("block_uid") or raw.get("parse_block_uid") or "").strip(),
            "span_start": raw.get("span_start"),
            "span_end": raw.get("span_end"),
            "snippet": str(raw.get("snippet") or raw.get("text") or "")[:MAX_SNIPPET_CHARS],
        })
    return output[:MAX_EVIDENCE_ITEMS]


def _candidate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    generated = bool(value.get("generated"))
    evidence_backed = bool(value.get("evidence_backed")) and not generated
    if not evidence_backed:
        return None
    return {
        "candidate_uid": str(value.get("candidate_uid") or "").strip(),
        "text": str(value.get("text") or value.get("candidate_text") or "")[:160],
        "evidence_backed": True,
        "generated": False,
    }


def _generated_hint(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if not (
        value.get("generated")
        and value.get("no_evidence")
        and str(value.get("provenance_type") or "") == "GENERATED_HINT"
    ):
        return None
    return {
        "text": str(value.get("text") or value.get("chinese_term") or "")[:160],
        "generated": True,
        "no_evidence": True,
        "evidence_backed": False,
        "authority": Authority.NON_OFFICIAL.value,
        "provenance_type": "GENERATED_HINT",
        "provider_id": str(value.get("provider_id") or "")[:120],
        "provider_version": str(value.get("provider_version") or "")[:120],
    }


def serialize_student_alignment_result(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise BoundaryContractError("alignment result must be an object.")
    scope = _enum_value(WorkspaceScope, result.get("workspace_scope"), "workspace_scope")
    alignment = _enum_value(
        AlignmentStatus, result.get("alignment_status"), "alignment_status"
    )
    dimensions = validate_result_dimensions(
        workspace_scope=scope,
        visibility="PRIVATE",
        authority="NON_OFFICIAL",
        alignment_status=alignment,
        publication_status="NOT_APPLICABLE",
        content_kind="PERSONAL_LEARNING_RESULT",
    )
    candidates = [
        item
        for item in (_candidate(raw) for raw in result.get("chinese_candidates", []))
        if item is not None
    ][:MAX_CANDIDATES]
    hints = [
        item
        for item in (_generated_hint(raw) for raw in result.get("generated_hints", []))
        if item is not None
    ][:MAX_CANDIDATES]
    chinese_term = str(result.get("chinese_term") or "")[:160]
    if alignment == AlignmentStatus.NOT_READY.value:
        chinese_term = ""
    return {
        "contract_id": STUDENT_ALIGNMENT_RESULT_CONTRACT_ID,
        "alignment_result_uid": str(result.get("alignment_result_uid") or "").strip(),
        **asdict(dimensions),
        "display_mode": DISPLAY_MODES[AlignmentStatus(alignment)],
        "uncertain": alignment == AlignmentStatus.REVIEW_REQUIRED.value,
        "student_access_allowed": True,
        "requires_human_review_before_view": False,
        "english_term": str(result.get("english_term") or "")[:220],
        "chinese_term": chinese_term,
        "english_evidence": _bounded_evidence(result.get("english_evidence")),
        "chinese_evidence": _bounded_evidence(result.get("chinese_evidence")),
        "chinese_candidates": candidates,
        "generated_hints": hints,
        "official": False,
    }


def personal_learning_record_contract(
    *,
    student_uid: Any,
    workspace_uid: Any,
    workspace_scope: Any,
    alignment_result_uid: Any,
) -> dict[str, Any]:
    scope = _enum_value(WorkspaceScope, workspace_scope, "workspace_scope")
    required = {
        "student_uid": str(student_uid or "").strip(),
        "workspace_uid": str(workspace_uid or "").strip(),
        "alignment_result_uid": str(alignment_result_uid or "").strip(),
    }
    if not all(required.values()):
        raise BoundaryContractError("PersonalLearningRecord identity is incomplete.")
    return {
        "contract_id": "personal-learning-record@1.0.0",
        **required,
        "workspace_scope": scope,
        "visibility": Visibility.PRIVATE.value,
        "authority": Authority.NON_OFFICIAL.value,
        "publication_status": PublicationStatus.NOT_APPLICABLE.value,
        "requires_human_review": False,
        "persistence_status": "CONTRACT_ONLY",
    }

