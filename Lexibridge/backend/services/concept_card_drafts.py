"""Create safe ConceptAlignmentCard drafts from bilingual evidence retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from services import audit_records
from services import bilingual_evidence_workflow
from services import concept_alignment_cards
from services import parse_quality_risk


class ConceptCardDraftError(ValueError):
    """Raised for controlled Concept Card draft creation failures."""


@dataclass(frozen=True)
class ConceptCardDraftResult:
    card: Any | None
    bilingual_result: bilingual_evidence_workflow.BilingualEvidenceResult
    draft_payload: dict[str, Any]
    created: bool
    reused: bool = False


@dataclass(frozen=True)
class PreparedConceptCardDraftResult:
    """Transaction-neutral result for a prepared formal workflow item."""

    outcome: str
    card: Any | None
    created: bool = False
    reused: bool = False


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def determine_draft_status_from_evidence_risks(
    risk_labels: list[str],
    english_candidates: list[dict[str, Any]],
    chinese_candidates: list[dict[str, Any]],
) -> str:
    del english_candidates, chinese_candidates
    if "bilingual_alignment_not_verified" in set(risk_labels or []):
        return "needs_review"
    return "needs_review"


def validate_draft_payload_safety(payload: dict[str, Any]) -> dict[str, Any]:
    draft = dict(payload or {})
    risk_labels = parse_quality_risk.normalize_labels(draft.get("risk_labels", []))
    risk_labels = parse_quality_risk.merge_risk_labels(risk_labels, ["bilingual_alignment_not_verified"])
    draft["risk_labels"] = risk_labels
    draft["status"] = determine_draft_status_from_evidence_risks(
        risk_labels,
        draft.get("english_evidence", []) or [],
        draft.get("chinese_evidence", []) or [],
    )
    draft["confidence_score"] = None
    draft["model_name"] = None
    draft["prompt_version"] = None
    draft["alignment_reason"] = _text(draft.get("alignment_reason"))
    if draft.get("status") == "approved":
        raise ConceptCardDraftError("draft-from-evidence cannot create approved ConceptAlignmentCard.")
    if not _text(draft.get("english_term")):
        raise ConceptCardDraftError("english_term is required.")
    if not _text(draft.get("course")):
        raise ConceptCardDraftError("course is required.")
    return draft


def build_draft_payload_from_bilingual_evidence(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    input_data: dict[str, Any],
    *,
    concept_card_model: Any | None = None,
    term_model: Any | None = None,
    terminology_card_model: Any | None = None,
    audit_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bilingual_evidence_workflow.BilingualEvidenceResult]:
    query = bilingual_evidence_workflow.build_bilingual_evidence_query(input_data)
    bilingual_result = bilingual_evidence_workflow.retrieve_bilingual_evidence(
        session,
        chunk_model,
        source_model,
        query["english_term"],
        chinese_term=query["chinese_term"],
        course=query["course"],
        chapter=query["chapter"],
        concept_scope=query["concept_scope"],
        limit=query["limit"],
        filters=query["filters"],
        auto_generate_chinese_candidates=query["auto_generate_chinese_candidates"],
        candidate_limit=query["candidate_limit"],
        selected_chinese_candidate_uid=query["selected_chinese_candidate_uid"],
        concept_card_model=concept_card_model,
        term_model=term_model,
        terminology_card_model=terminology_card_model,
        audit_context=audit_context,
    )
    draft_payload = validate_draft_payload_safety(bilingual_result.draft_payload)
    if _text(input_data.get("status")).lower() == "approved":
        draft_payload["risk_labels"] = parse_quality_risk.merge_risk_labels(
            draft_payload.get("risk_labels", []),
            ["requested_approved_downgraded"],
        )
        draft_payload["status"] = "needs_review"
    return draft_payload, bilingual_result


def find_existing_draft(session: Any, card_model: Any, draft_payload: dict[str, Any]) -> Any | None:
    return card_model.query.filter_by(
        english_term=_text(draft_payload.get("english_term")),
        chinese_term=_text(draft_payload.get("chinese_term")),
        course=_text(draft_payload.get("course")),
        chapter=_text(draft_payload.get("chapter")),
        retrieval_version=_text(draft_payload.get("retrieval_version")),
    ).filter(card_model.status.in_(["draft", "needs_review"])).order_by(card_model.id.desc()).first()


def _reference_ids(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        values = []
    elif isinstance(value, str):
        try:
            values = json.loads(value)
        except (TypeError, ValueError):
            values = []
    else:
        values = value
    if not isinstance(values, list):
        return ()
    refs = []
    for item in values:
        if isinstance(item, dict):
            reference = _text(item.get("chunk_uid") or item.get("reference_id"))
        else:
            reference = _text(item)
        if reference:
            refs.append(reference)
    return tuple(sorted(set(refs)))


def _bounded_text(value: Any, max_chars: int = 300) -> str:
    text = _text(value)
    return text if len(text) <= max_chars else f"{text[: max_chars - 1]}..."


def _source_title(source: Any | None, fallback: str = "") -> str:
    if source is None:
        return fallback
    return _text(
        getattr(source, "title", "")
        or getattr(source, "source_title", "")
        or getattr(source, "name", "")
        or fallback
    )


def _evidence_payload_from_chunk_refs(
    session: Any,
    chunk_model: Any | None,
    source_model: Any | None,
    refs: tuple[str, ...],
    *,
    fallback_language: str,
) -> list[dict[str, Any]]:
    if chunk_model is None or not refs:
        return [{"chunk_uid": reference} for reference in refs]
    chunks = (
        session.query(chunk_model)
        .filter(chunk_model.chunk_uid.in_(list(refs)))
        .all()
    )
    chunks_by_uid = {getattr(chunk, "chunk_uid", ""): chunk for chunk in chunks}
    source_uids = sorted({_text(getattr(chunk, "source_uid", "")) for chunk in chunks if _text(getattr(chunk, "source_uid", ""))})
    sources_by_uid = {}
    if source_model is not None and source_uids:
        sources_by_uid = {
            getattr(source, "source_uid", ""): source
            for source in session.query(source_model).filter(source_model.source_uid.in_(source_uids)).all()
        }
    evidence = []
    for reference in refs:
        chunk = chunks_by_uid.get(reference)
        if chunk is None:
            evidence.append({"chunk_uid": reference})
            continue
        source_uid = _text(getattr(chunk, "source_uid", ""))
        source = sources_by_uid.get(source_uid)
        evidence.append({
            "chunk_uid": reference,
            "source_uid": source_uid,
            "source_title": _source_title(source, getattr(chunk, "title", "")),
            "course": _text(getattr(chunk, "course", "") or getattr(source, "course", "")),
            "chapter": _text(getattr(chunk, "chapter", "") or getattr(source, "chapter", "")),
            "language": _text(getattr(chunk, "language", "") or getattr(source, "language", "") or fallback_language),
            "source_role": _text(getattr(source, "source_role", "")),
            "trust_level": _text(getattr(chunk, "trust_level", "") or getattr(source, "trust_level", "")),
            "quality_status": _text(getattr(chunk, "quality_status", "") or getattr(source, "quality_status", "")),
            "quality_flags": parse_quality_risk.normalize_labels(getattr(chunk, "quality_flags", "[]") or []),
            "source_locator": _text(
                getattr(chunk, "source_locator", "")
                or getattr(chunk, "source_page", "")
                or getattr(chunk, "page_number", "")
                or getattr(chunk, "source_slide", "")
            ),
            "snippet": _bounded_text(getattr(chunk, "content", "") or getattr(chunk, "normalized_text", "")),
            "parse_uid": _text(getattr(chunk, "parse_uid", "")),
            "parse_block_uid": _text(getattr(chunk, "parse_block_uid", "")),
        })
    return evidence


def create_or_reuse_prepared_concept_card_draft(
    session: Any,
    card_model: Any,
    *,
    english_term: str,
    chinese_term: str,
    course: str,
    chapter: str,
    retrieval_version: str,
    english_evidence_refs: tuple[str, ...],
    chinese_evidence_refs: tuple[str, ...],
    risk_labels: tuple[str, ...] = (),
    chunk_model: Any | None = None,
    source_model: Any | None = None,
    now_fn=None,
) -> PreparedConceptCardDraftResult:
    """Create or reuse a safe draft without owning commit or rollback."""

    identity = {
        "english_term": _text(english_term),
        "chinese_term": _text(chinese_term),
        "course": _text(course),
        "chapter": _text(chapter),
    }
    if not identity["english_term"] or not identity["course"]:
        raise ConceptCardDraftError("english_term and course are required.")
    approved = (
        session.query(card_model)
        .filter_by(**identity, status="approved")
        .order_by(card_model.id.desc())
        .first()
    )
    if approved is not None:
        return PreparedConceptCardDraftResult(
            outcome="approved_protected",
            card=approved,
            reused=True,
        )

    requested_english_refs = tuple(sorted(set(english_evidence_refs or ())))
    requested_chinese_refs = tuple(sorted(set(chinese_evidence_refs or ())))
    existing_rows = (
        session.query(card_model)
        .filter_by(**identity)
        .filter(card_model.status.in_(["draft", "needs_review"]))
        .order_by(card_model.id.desc())
        .all()
    )
    for existing in existing_rows:
        same_scope = (
            _text(getattr(existing, "retrieval_version", "")) == _text(retrieval_version)
            and _reference_ids(getattr(existing, "english_evidence", "[]")) == requested_english_refs
            and _reference_ids(getattr(existing, "chinese_evidence", "[]")) == requested_chinese_refs
        )
        if same_scope:
            return PreparedConceptCardDraftResult(
                outcome="reused",
                card=existing,
                reused=True,
            )
    if existing_rows:
        return PreparedConceptCardDraftResult(outcome="conflict", card=None)

    merged_risks = parse_quality_risk.merge_risk_labels(
        list(risk_labels or ()),
        ["bilingual_alignment_not_verified"],
    )
    card = card_model(
        **identity,
        english_evidence=_evidence_payload_from_chunk_refs(
            session,
            chunk_model,
            source_model,
            requested_english_refs,
            fallback_language="en",
        ),
        chinese_evidence=_evidence_payload_from_chunk_refs(
            session,
            chunk_model,
            source_model,
            requested_chinese_refs,
            fallback_language="zh",
        ),
        risk_labels=merged_risks,
        status="needs_review",
        confidence_score=None,
        model_name=None,
        prompt_version=None,
        retrieval_version=_text(retrieval_version),
        created_at=now_fn() if now_fn else "",
        updated_at=now_fn() if now_fn else "",
    )
    session.add(card)
    session.flush()
    return PreparedConceptCardDraftResult(
        outcome="created",
        card=card,
        created=True,
    )


def _audit_summary_payload(
    draft_payload: dict[str, Any],
    bilingual_result: bilingual_evidence_workflow.BilingualEvidenceResult,
    *,
    card_uid: str = "",
    created: bool = False,
) -> dict[str, Any]:
    english_candidates = bilingual_result.english_evidence_candidates
    chinese_candidates = bilingual_result.chinese_evidence_candidates
    return {
        "card_uid": card_uid,
        "created": created,
        "english_result_count": len(english_candidates),
        "chinese_result_count": len(chinese_candidates),
        "top_english_chunk_uids": [item.get("chunk_uid", "") for item in english_candidates[:5]],
        "top_chinese_chunk_uids": [item.get("chunk_uid", "") for item in chinese_candidates[:5]],
        "risk_labels": draft_payload.get("risk_labels", []),
        "status": draft_payload.get("status", ""),
        "retrieval_version": draft_payload.get("retrieval_version", ""),
    }


def record_draft_audit(
    session: Any,
    audit_model: Any | None,
    *,
    event_type: str,
    draft_payload: dict[str, Any] | None = None,
    bilingual_result: bilingual_evidence_workflow.BilingualEvidenceResult | None = None,
    card_uid: str = "",
    created: bool = False,
    result: str = "success",
    error_code: str = "",
    error_message: str = "",
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = False,
) -> Any | None:
    if audit_model is None:
        return None
    draft_payload = dict(draft_payload or {})
    output_payload = {}
    if bilingual_result is not None:
        output_payload = _audit_summary_payload(
            draft_payload,
            bilingual_result,
            card_uid=card_uid,
            created=created,
        )
    return audit_records.create_audit_record(
        session,
        audit_model,
        {
            "event_type": event_type,
            "target_type": "concept_alignment_card",
            "target_uid": card_uid,
            "source": "api" if audit_context else "service",
            "input_payload": {
                "english_term": _text(draft_payload.get("english_term"))[:240],
                "chinese_term": _text(draft_payload.get("chinese_term"))[:240],
                "course": _text(draft_payload.get("course"))[:160],
                "chapter": _text(draft_payload.get("chapter"))[:160],
            },
            "output_payload": output_payload,
            "changed_fields": [],
            "result": result,
            "error_code": error_code,
            "error_message": error_message,
        },
        audit_context=audit_context,
        now_fn=now_fn,
        commit=commit,
    )


def create_concept_card_draft_from_evidence(
    session: Any,
    *,
    card_model: Any,
    chunk_model: Any,
    source_model: Any,
    input_data: dict[str, Any],
    term_model: Any | None = None,
    terminology_card_model: Any | None = None,
    audit_model: Any | None = None,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    force_create: bool = False,
    commit: bool = True,
) -> ConceptCardDraftResult:
    try:
        draft_payload, bilingual_result = build_draft_payload_from_bilingual_evidence(
            session,
            chunk_model,
            source_model,
            input_data,
            concept_card_model=card_model,
            term_model=term_model,
            terminology_card_model=terminology_card_model,
            audit_context=audit_context,
        )
        record_draft_audit(
            session,
            audit_model,
            event_type="concept_card_draft_payload_created",
            draft_payload=draft_payload,
            bilingual_result=bilingual_result,
            created=False,
            audit_context=audit_context,
            now_fn=now_fn,
            commit=False,
        )
        if not force_create:
            existing = find_existing_draft(session, card_model, draft_payload)
            if existing is not None:
                record_draft_audit(
                    session,
                    audit_model,
                    event_type="concept_card_draft_reused",
                    draft_payload=draft_payload,
                    bilingual_result=bilingual_result,
                    card_uid=getattr(existing, "card_uid", ""),
                    created=False,
                    audit_context=audit_context,
                    now_fn=now_fn,
                    commit=False,
                )
                if commit:
                    session.commit()
                else:
                    session.flush()
                return ConceptCardDraftResult(
                    card=existing,
                    bilingual_result=bilingual_result,
                    draft_payload=draft_payload,
                    created=False,
                    reused=True,
                )
        create_payload = dict(draft_payload)
        create_payload["created_by"] = input_data.get("created_by")
        card = concept_alignment_cards.create_concept_card(
            session,
            card_model,
            create_payload,
            audit_model=audit_model,
            actor=actor,
            audit_context=audit_context,
            source="api" if audit_context else "service",
            now_fn=now_fn,
            commit=False,
        )
        record_draft_audit(
            session,
            audit_model,
            event_type="concept_card_draft_created",
            draft_payload=draft_payload,
            bilingual_result=bilingual_result,
            card_uid=getattr(card, "card_uid", ""),
            created=True,
            audit_context=audit_context,
            now_fn=now_fn,
            commit=False,
        )
        if commit:
            session.commit()
        else:
            session.flush()
        return ConceptCardDraftResult(
            card=card,
            bilingual_result=bilingual_result,
            draft_payload=draft_payload,
            created=True,
            reused=False,
        )
    except Exception as exc:
        session.rollback()
        record_draft_audit(
            session,
            audit_model,
            event_type="concept_card_draft_creation_failed",
            draft_payload=input_data or {},
            result="error",
            error_code="concept_card_draft_creation_failed",
            error_message=str(exc),
            audit_context=audit_context,
            now_fn=now_fn,
            commit=True if audit_model is not None else False,
        )
        raise


def serialize_concept_card_draft_result(
    card: Any | None,
    bilingual_result: bilingual_evidence_workflow.BilingualEvidenceResult,
    *,
    draft_payload: dict[str, Any] | None = None,
    card_serializer=None,
    created: bool = True,
    reused: bool = False,
) -> dict[str, Any]:
    return {
        "created": bool(created),
        "reused": bool(reused),
        "card": card_serializer(card) if card is not None and card_serializer else None,
        "draft_payload": dict(draft_payload or bilingual_result.draft_payload),
        "english_evidence_candidates": [
            dict(candidate) for candidate in bilingual_result.english_evidence_candidates
        ],
        "chinese_evidence_candidates": [
            dict(candidate) for candidate in bilingual_result.chinese_evidence_candidates
        ],
        "chinese_term_candidates": [
            dict(candidate) for candidate in bilingual_result.chinese_term_candidates
        ],
        "selected_chinese_candidate": (
            dict(bilingual_result.selected_chinese_candidate)
            if bilingual_result.selected_chinese_candidate else None
        ),
        "risk_labels": list((draft_payload or bilingual_result.draft_payload).get("risk_labels", bilingual_result.risk_labels)),
    }
