"""Service helpers for Concept Alignment Card persistence and API use."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_

from services import audit_records
from services import parse_quality_risk


VALID_STATUSES = {"draft", "needs_review", "approved", "rejected", "deprecated"}
CONTROL_FIELDS = {"expected_version"}

CREATE_FIELDS = {
    "english_term",
    "chinese_term",
    "course",
    "chapter",
    "concept_scope",
    "english_explanation",
    "chinese_explanation",
    "english_evidence",
    "chinese_evidence",
    "alignment_reason",
    "confidence_score",
    "risk_labels",
    "parse_uid",
    "parse_block_uid",
    "parse_quality_status",
    "parse_quality_flags",
    "input_risk_labels",
    "status",
    "source_document_id",
    "source_chunk_id",
    "created_by",
    "reviewed_by",
    "model_name",
    "prompt_version",
    "retrieval_version",
}

UPDATE_FIELDS = {
    "english_term",
    "chinese_term",
    "course",
    "chapter",
    "concept_scope",
    "english_explanation",
    "chinese_explanation",
    "english_evidence",
    "chinese_evidence",
    "alignment_reason",
    "confidence_score",
    "risk_labels",
    "parse_uid",
    "parse_block_uid",
    "parse_quality_status",
    "parse_quality_flags",
    "input_risk_labels",
    "status",
    "reviewed_by",
    "model_name",
    "prompt_version",
    "retrieval_version",
}

VERSIONED_FIELDS = UPDATE_FIELDS - {"reviewed_by"}


class ConceptCardError(ValueError):
    """Base service-layer error."""


class ConceptCardNotFoundError(ConceptCardError):
    """Raised when a card id or uid cannot be found."""


class ConceptCardQualityGateError(ConceptCardError):
    """Raised when parse quality risk blocks a trusted card state."""


class ConceptCardStaleReviewError(ConceptCardError):
    """Raised when a card update uses an out-of-date review token."""

    reason = "concept_card_stale_review"


def classify_concept_card_error(error: Exception | str) -> str:
    message = str(error or "")
    if isinstance(error, ConceptCardStaleReviewError) or "stale" in message or "expected_version" in message:
        return "concept_card_stale_review"
    if isinstance(error, ConceptCardQualityGateError) or "parse quality risk" in message:
        return "concept_card_quality_gate_blocked"
    if isinstance(error, ConceptCardNotFoundError) or "not found" in message:
        return "concept_card_not_found"
    if "confidence_score" in message:
        return "invalid_confidence_score"
    if "english_term is required" in message:
        return "missing_english_term"
    if "course is required" in message:
        return "missing_course"
    if "status must be one of" in message:
        return "invalid_status"
    if "requires English or Chinese evidence" in message:
        return "evidence_required_for_approved"
    return "concept_card_operation_failed"


@dataclass(frozen=True)
class ConceptCardListResult:
    items: list[Any]
    page: int
    per_page: int
    total: int

    @property
    def pagination(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "per_page": self.per_page,
            "total": self.total,
            "has_next": self.page * self.per_page < self.total,
        }


def _loads_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _serialize_list(value: Any, field_name: str) -> str:
    if value in (None, ""):
        return "[]"
    if isinstance(value, str):
        value = _loads_json(value, None)
    if not isinstance(value, list):
        raise ConceptCardError(f"{field_name} must be a list.")
    return _dumps_json(value)


def _serialize_evidence(value: Any, field_name: str) -> str:
    if value in (None, ""):
        return "[]"
    if isinstance(value, (list, dict)):
        return _dumps_json(value)
    if isinstance(value, str):
        parsed = _loads_json(value, None)
        if isinstance(parsed, (list, dict)):
            return _dumps_json(parsed)
        return value
    raise ConceptCardError(f"{field_name} must be JSON-serializable evidence or text.")


def _has_evidence(value: Any) -> bool:
    if value in (None, ""):
        return False
    parsed = _loads_json(value, None)
    if isinstance(parsed, list):
        return any(bool(item) for item in parsed)
    if isinstance(parsed, dict):
        return bool(parsed)
    return bool(str(value).strip())


def _normalize_confidence(value: Any) -> float | None:
    if value in (None, ""):
        return None
    score = float(value)
    if score < 0 or score > 1:
        raise ConceptCardError("confidence_score must be between 0 and 1.")
    return score


def _normalize_payload(data: dict[str, Any], allowed_fields: set[str]) -> dict[str, Any]:
    payload = {}
    for field in allowed_fields:
        if field not in data:
            continue
        value = data[field]
        if field in {"english_term", "course", "status"}:
            value = str(value or "").strip()
        if field in {"risk_labels", "parse_quality_flags", "input_risk_labels"}:
            value = _serialize_list(value, field)
        elif field in {"english_evidence", "chinese_evidence"}:
            value = _serialize_evidence(value, field)
        elif field == "confidence_score":
            value = _normalize_confidence(value)
        payload[field] = value
    return payload


def _payload_list(payload: dict[str, Any], field: str, existing_card: Any | None = None) -> list[Any]:
    if field in payload:
        return _loads_json(payload.get(field), [])
    if existing_card is not None:
        return _loads_json(getattr(existing_card, field, "[]"), [])
    return []


def _apply_parse_quality_risk(
    raw_data: dict[str, Any],
    payload: dict[str, Any],
    *,
    existing_card: Any | None = None,
    is_create: bool = False,
) -> None:
    metadata_source = dict(raw_data or {})
    for field in ("parse_uid", "parse_block_uid", "parse_quality_status", "parse_quality_flags"):
        if field in payload:
            metadata_source[field] = payload[field]
        elif existing_card is not None:
            metadata_source[field] = getattr(existing_card, field, "")
    metadata = parse_quality_risk.build_parse_quality_metadata(metadata_source)
    if parse_quality_risk.should_block_downstream_creation(metadata):
        raise ConceptCardQualityGateError("blocked parse quality status cannot create or update ConceptAlignmentCard.")

    new_risk_labels = parse_quality_risk.merge_risk_labels(
        metadata.get("input_risk_labels", []),
        raw_data.get("input_risk_labels", []),
    )
    merged_risk_labels = parse_quality_risk.merge_risk_labels(
        _payload_list(payload, "risk_labels", existing_card),
        new_risk_labels,
    )
    if merged_risk_labels:
        payload["risk_labels"] = _serialize_list(merged_risk_labels, "risk_labels")
    merged_input_risks = parse_quality_risk.merge_risk_labels(
        _payload_list(payload, "input_risk_labels", existing_card),
        new_risk_labels,
    )
    if merged_input_risks:
        payload["input_risk_labels"] = _serialize_list(merged_input_risks, "input_risk_labels")

    for field in ("parse_uid", "parse_block_uid", "parse_quality_status"):
        if metadata.get(field) and (field in CREATE_FIELDS or field in UPDATE_FIELDS):
            payload[field] = metadata[field]
    if metadata.get("parse_quality_flags"):
        payload["parse_quality_flags"] = _serialize_list(metadata["parse_quality_flags"], "parse_quality_flags")

    force_review = parse_quality_risk.should_force_needs_review(metadata) or bool(
        set(merged_risk_labels) & parse_quality_risk.FORCE_REVIEW_RISK_LABELS
    )
    requested_status = payload.get("status", getattr(existing_card, "status", "draft"))
    if force_review and requested_status == "approved":
        raise ConceptCardQualityGateError("ConceptAlignmentCard with input parse quality risk cannot be approved.")
    if force_review and is_create and "status" not in raw_data:
        payload["status"] = "needs_review"
    if force_review and payload.get("confidence_score") is not None:
        payload["confidence_score"] = min(float(payload["confidence_score"]), 0.79)


def _validate_payload(payload: dict[str, Any], existing_card: Any | None = None) -> None:
    english_term = payload.get("english_term", getattr(existing_card, "english_term", ""))
    course = payload.get("course", getattr(existing_card, "course", ""))
    status = payload.get("status", getattr(existing_card, "status", "draft"))
    english_evidence = payload.get("english_evidence", getattr(existing_card, "english_evidence", "[]"))
    chinese_evidence = payload.get("chinese_evidence", getattr(existing_card, "chinese_evidence", "[]"))

    if not str(english_term or "").strip():
        raise ConceptCardError("english_term is required.")
    if not str(course or "").strip():
        raise ConceptCardError("course is required.")
    if status not in VALID_STATUSES:
        raise ConceptCardError(f"status must be one of {sorted(VALID_STATUSES)}.")
    if status == "approved" and not (_has_evidence(english_evidence) or _has_evidence(chinese_evidence)):
        raise ConceptCardError("approved ConceptAlignmentCard requires English or Chinese evidence.")


def _commit_or_flush(session: Any, commit: bool) -> None:
    if commit:
        session.commit()
    else:
        session.flush()


def _expected_version(data: dict[str, Any]) -> int | None:
    value = data.get("expected_version")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConceptCardStaleReviewError("expected_version must be an integer review token.") from exc


def require_current_version(card: Any, data: dict[str, Any]) -> int:
    expected = _expected_version(data or {})
    if expected is None:
        raise ConceptCardStaleReviewError("expected_version is required for Concept Card updates.")
    current = int(getattr(card, "version", 1) or 1)
    if expected != current:
        raise ConceptCardStaleReviewError("Concept Card review token is stale.")
    return expected


def _record_failed_operation(
    session: Any,
    audit_model: Any | None,
    *,
    target_uid: str | None,
    error: Exception,
    input_payload: dict[str, Any] | None,
    error_code: str | None = None,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
) -> None:
    if audit_model is None:
        return
    try:
        audit_records.record_concept_card_operation_failed(
            session,
            audit_model,
            target_uid=target_uid,
            error=error,
            error_code=error_code or classify_concept_card_error(error),
            input_payload=input_payload,
            actor=actor,
            audit_context=audit_context,
            source=source,
            now_fn=now_fn,
            commit=commit,
        )
    except Exception:
        if commit:
            session.rollback()


def get_concept_card(session: Any, card_model: Any, identifier: Any) -> Any:
    if identifier in (None, ""):
        raise ConceptCardNotFoundError("ConceptAlignmentCard not found.")
    card = None
    if isinstance(identifier, int) or str(identifier).isdigit():
        card = session.get(card_model, int(identifier))
    if card is None:
        card = card_model.query.filter_by(card_uid=str(identifier)).first()
    if card is None:
        raise ConceptCardNotFoundError("ConceptAlignmentCard not found.")
    return card


def create_concept_card(
    session: Any,
    card_model: Any,
    data: dict[str, Any],
    *,
    audit_model: Any | None = None,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
) -> Any:
    try:
        payload = _normalize_payload(data or {}, CREATE_FIELDS)
        payload.setdefault("status", "draft")
        _apply_parse_quality_risk(data or {}, payload, is_create=True)
        _validate_payload(payload)
    except (ConceptCardError, ValueError) as exc:
        _record_failed_operation(
            session,
            audit_model,
            target_uid=None,
            error=exc,
            input_payload=data or {},
            actor=actor,
            audit_context=audit_context,
            source=source,
            now_fn=now_fn,
            commit=commit,
        )
        raise
    now = now_fn() if now_fn else ""
    payload.setdefault("created_at", now)
    payload.setdefault("updated_at", now)
    card = card_model(**payload)
    try:
        session.add(card)
        session.flush()
        if audit_model is not None:
            audit_records.record_concept_card_created(
                session,
                audit_model,
                card,
                actor=actor,
                audit_context=audit_context,
                input_payload=data or {},
                source=source,
                now_fn=now_fn,
                commit=False,
            )
        _commit_or_flush(session, commit)
    except Exception:
        session.rollback()
        raise
    return card


def list_concept_cards(session: Any, card_model: Any, filters: dict[str, Any] | None = None) -> ConceptCardListResult:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    per_page = max(1, min(int(filters.get("per_page") or filters.get("page_size") or 20), 100))
    query = card_model.query

    course = str(filters.get("course") or "").strip()
    chapter = str(filters.get("chapter") or "").strip()
    status = str(filters.get("status") or "").strip()
    q = str(filters.get("q") or "").strip()

    if course:
        query = query.filter_by(course=course)
    if chapter:
        query = query.filter_by(chapter=chapter)
    if status:
        if status not in VALID_STATUSES:
            raise ConceptCardError(f"status must be one of {sorted(VALID_STATUSES)}.")
        query = query.filter_by(status=status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(card_model.english_term.ilike(like), card_model.chinese_term.ilike(like)))

    total = query.count()
    items = query.order_by(card_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return ConceptCardListResult(items=items, page=page, per_page=per_page, total=total)


def update_concept_card(
    session: Any,
    card_model: Any,
    identifier: Any,
    patch_data: dict[str, Any],
    *,
    audit_model: Any | None = None,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
    require_concurrency_token: bool = False,
) -> Any:
    card = get_concept_card(session, card_model, identifier)
    before_snapshot = audit_records.concept_card_snapshot(card)
    try:
        if require_concurrency_token:
            require_current_version(card, patch_data or {})
        payload = _normalize_payload(patch_data or {}, UPDATE_FIELDS)
        _apply_parse_quality_risk(patch_data or {}, payload, existing_card=card)
        _validate_payload(payload, existing_card=card)
    except (ConceptCardError, ValueError) as exc:
        _record_failed_operation(
            session,
            audit_model,
            target_uid=getattr(card, "card_uid", None),
            error=exc,
            input_payload=patch_data or {},
            actor=actor,
            audit_context=audit_context,
            source=source,
            now_fn=now_fn,
            commit=commit,
        )
        raise

    changed_versioned = False
    for field, value in payload.items():
        if getattr(card, field) != value:
            setattr(card, field, value)
            if field in VERSIONED_FIELDS:
                changed_versioned = True
    if changed_versioned:
        card.version = int(card.version or 1) + 1
    if now_fn:
        card.updated_at = now_fn()

    try:
        session.flush()
        if audit_model is not None:
            audit_records.record_concept_card_updated(
                session,
                audit_model,
                before_snapshot,
                audit_records.concept_card_snapshot(card),
                actor=actor,
                audit_context=audit_context,
                input_payload=patch_data or {},
                source=source,
                now_fn=now_fn,
                commit=False,
            )
        _commit_or_flush(session, commit)
    except Exception:
        session.rollback()
        raise
    return card


def change_concept_card_status(
    session: Any,
    card_model: Any,
    identifier: Any,
    status: str,
    *,
    reviewer: Any = None,
    audit_model: Any | None = None,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
) -> Any:
    card = get_concept_card(session, card_model, identifier)
    before_snapshot = audit_records.concept_card_snapshot(card)
    patch = {"status": status}
    if reviewer is not None:
        patch["reviewed_by"] = getattr(reviewer, "id", reviewer)
    try:
        payload = _normalize_payload(patch, UPDATE_FIELDS)
        _apply_parse_quality_risk(patch, payload, existing_card=card)
        _validate_payload(payload, existing_card=card)
    except (ConceptCardError, ValueError) as exc:
        _record_failed_operation(
            session,
            audit_model,
            target_uid=getattr(card, "card_uid", None),
            error=exc,
            input_payload=patch,
            actor=actor or reviewer,
            audit_context=audit_context,
            source=source,
            now_fn=now_fn,
            commit=commit,
        )
        raise

    changed_versioned = False
    for field, value in payload.items():
        if getattr(card, field) != value:
            setattr(card, field, value)
            if field in VERSIONED_FIELDS:
                changed_versioned = True
    if reviewer is not None and now_fn is not None:
        card.reviewed_at = now_fn()
    if changed_versioned:
        card.version = int(card.version or 1) + 1
    if now_fn:
        card.updated_at = now_fn()
    try:
        session.flush()
        if audit_model is not None:
            audit_records.record_concept_card_status_changed(
                session,
                audit_model,
                before_snapshot,
                audit_records.concept_card_snapshot(card),
                actor=actor or reviewer,
                audit_context=audit_context,
                input_payload=patch,
                source=source,
                now_fn=now_fn,
                commit=False,
            )
        _commit_or_flush(session, commit)
    except Exception:
        session.rollback()
        raise
    return card


def serialize_concept_card(card: Any) -> dict[str, Any]:
    return {
        "id": card.id,
        "card_uid": card.card_uid,
        "english_term": card.english_term,
        "chinese_term": card.chinese_term,
        "course": card.course,
        "chapter": card.chapter,
        "concept_scope": card.concept_scope,
        "english_explanation": card.english_explanation,
        "chinese_explanation": card.chinese_explanation,
        "english_evidence": _loads_json(card.english_evidence, card.english_evidence or []),
        "chinese_evidence": _loads_json(card.chinese_evidence, card.chinese_evidence or []),
        "alignment_reason": card.alignment_reason,
        "confidence_score": card.confidence_score,
        "risk_labels": _loads_json(card.risk_labels, []),
        "parse_uid": getattr(card, "parse_uid", ""),
        "parse_block_uid": getattr(card, "parse_block_uid", ""),
        "parse_quality_status": getattr(card, "parse_quality_status", ""),
        "parse_quality_flags": _loads_json(getattr(card, "parse_quality_flags", "[]"), []),
        "input_risk_labels": _loads_json(getattr(card, "input_risk_labels", "[]"), []),
        "status": card.status,
        "source_document_id": card.source_document_id,
        "source_chunk_id": card.source_chunk_id,
        "created_by": card.created_by,
        "reviewed_by": card.reviewed_by,
        "reviewed_at": card.reviewed_at,
        "model_name": card.model_name,
        "prompt_version": card.prompt_version,
        "retrieval_version": card.retrieval_version,
        "version": card.version,
        "review_token": str(card.version or ""),
        "created_at": card.created_at,
        "updated_at": card.updated_at,
    }


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _confidence_from_legacy(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 1:
        return score
    if 1 < score <= 100:
        return round(score / 100, 4)
    return None


def build_concept_card_draft_from_term(term_like: Any) -> dict[str, Any]:
    english_term = _first_text(getattr(term_like, "english_term", ""))
    chinese_term = _first_text(
        getattr(term_like, "final_chinese_term", ""),
        getattr(term_like, "chinese_term", ""),
        getattr(term_like, "ai_translation_candidate", ""),
    )
    english_evidence = _first_text(
        getattr(term_like, "english_evidence_snapshot", ""),
        getattr(term_like, "english_kb_evidence", ""),
        getattr(term_like, "english_evidence", ""),
    )
    chinese_evidence = _first_text(
        getattr(term_like, "chinese_evidence_snapshot", ""),
        getattr(term_like, "chinese_kb_evidence", ""),
        getattr(term_like, "chinese_evidence", ""),
    )
    parse_metadata = parse_quality_risk.build_parse_quality_metadata({
        "parse_uid": getattr(term_like, "parse_uid", ""),
        "parse_block_uid": getattr(term_like, "parse_block_uid", ""),
        "parse_quality_status": getattr(term_like, "parse_quality_status", ""),
        "parse_quality_flags": getattr(term_like, "parse_quality_flags", []),
    })
    return {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": _first_text(getattr(term_like, "course", ""), getattr(term_like, "course_name", "")),
        "chapter": _first_text(getattr(term_like, "chapter", "")),
        "concept_scope": _first_text(getattr(term_like, "scope_type", ""), getattr(term_like, "context", "")),
        "english_explanation": _first_text(getattr(term_like, "concept_explanation", "")),
        "chinese_explanation": _first_text(getattr(term_like, "explanation", "")),
        "english_evidence": english_evidence,
        "chinese_evidence": chinese_evidence,
        "alignment_reason": _first_text(getattr(term_like, "alignment_reason", "")),
        "confidence_score": _confidence_from_legacy(
            getattr(term_like, "confidence_score", getattr(term_like, "confidence", None))
        ),
        "risk_labels": parse_metadata["input_risk_labels"],
        "parse_uid": parse_metadata["parse_uid"],
        "parse_block_uid": parse_metadata["parse_block_uid"],
        "parse_quality_status": parse_metadata["parse_quality_status"],
        "parse_quality_flags": parse_metadata["parse_quality_flags"],
        "input_risk_labels": parse_metadata["input_risk_labels"],
        "status": "draft",
        "source_document_id": getattr(term_like, "source_document_id", None),
        "source_chunk_id": getattr(term_like, "source_chunk_id", None),
        "model_name": _first_text(getattr(term_like, "model_name", ""), getattr(term_like, "ai_model", "")),
        "prompt_version": _first_text(getattr(term_like, "prompt_version", "")),
        "retrieval_version": _first_text(getattr(term_like, "retrieval_version", "")),
    }
