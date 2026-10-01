"""Publication integrity helpers for Concept Alignment Cards.

These helpers keep student publication, teacher review, and provenance display
consistent without adding a second Concept Card lifecycle or schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


ACTIVE_SOURCE_STATUS = "active"
ACTIVE_CHUNK_STATUS = "active"


class ConceptCardPublicationError(ValueError):
    """Raised when a card cannot be published because its evidence is unsafe."""

    def __init__(self, message: str, reason: str = "concept_card_source_unavailable", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


@dataclass(frozen=True)
class PublicationSourceReport:
    available: bool
    unavailable_sources: list[dict[str, Any]]
    unavailable_chunks: list[dict[str, Any]]
    evidence_without_source_refs: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "unavailable_sources": self.unavailable_sources,
            "unavailable_chunks": self.unavailable_chunks,
            "evidence_without_source_refs": self.evidence_without_source_refs,
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _loads_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _card_evidence(card: Any, side: str) -> list[Any]:
    field = "english_evidence" if side == "english" else "chinese_evidence"
    value = getattr(card, field, "[]")
    parsed = _loads_json(value, [])
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, str) and parsed.strip():
        return [{"snippet": parsed.strip(), "language": "en" if side == "english" else "zh"}]
    return []


def _safe_bbox(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    if isinstance(value, str):
        value = _loads_json(value, None)
    if isinstance(value, dict):
        required = {"x0", "y0", "x1", "y1"}
        if required <= set(value):
            result = {key: value.get(key) for key in ("x0", "y0", "x1", "y1")}
            result["coordinate_origin"] = _text(value.get("coordinate_origin")) or "top-left"
            return result
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return {
            "x0": value[0],
            "y0": value[1],
            "x1": value[2],
            "y1": value[3],
            "coordinate_origin": "top-left",
        }
    return None


def _load_chunks(session: Any, chunk_model: Any | None, evidence: list[Any]) -> dict[str, Any]:
    if chunk_model is None:
        return {}
    refs = sorted({
        _text(item.get("chunk_uid"))
        for item in evidence
        if isinstance(item, dict) and _text(item.get("chunk_uid"))
    })
    if not refs:
        return {}
    return {
        getattr(chunk, "chunk_uid", ""): chunk
        for chunk in session.query(chunk_model).filter(chunk_model.chunk_uid.in_(refs)).all()
    }


def _load_sources(session: Any, source_model: Any | None, evidence: list[Any], chunks_by_uid: dict[str, Any]) -> dict[str, Any]:
    if source_model is None:
        return {}
    refs = {
        _text(item.get("source_uid"))
        for item in evidence
        if isinstance(item, dict) and _text(item.get("source_uid"))
    }
    refs.update(
        _text(getattr(chunk, "source_uid", ""))
        for chunk in chunks_by_uid.values()
        if _text(getattr(chunk, "source_uid", ""))
    )
    refs = {ref for ref in refs if ref}
    if not refs:
        return {}
    return {
        getattr(source, "source_uid", ""): source
        for source in session.query(source_model).filter(source_model.source_uid.in_(sorted(refs))).all()
    }


def _load_parse_records(session: Any, parse_model: Any | None, evidence: list[Any], chunks_by_uid: dict[str, Any]) -> dict[str, Any]:
    if parse_model is None:
        return {}
    refs = {
        _text(item.get("parse_uid"))
        for item in evidence
        if isinstance(item, dict) and _text(item.get("parse_uid"))
    }
    refs.update(
        _text(getattr(chunk, "parse_uid", ""))
        for chunk in chunks_by_uid.values()
        if _text(getattr(chunk, "parse_uid", ""))
    )
    refs = {ref for ref in refs if ref}
    if not refs:
        return {}
    return {
        getattr(record, "parse_uid", ""): record
        for record in session.query(parse_model).filter(parse_model.parse_uid.in_(sorted(refs))).all()
    }


def _source_available(source: Any | None) -> tuple[bool, str]:
    if source is None:
        return False, "source_missing"
    status = _text(getattr(source, "status", "")) or ACTIVE_SOURCE_STATUS
    if status != ACTIVE_SOURCE_STATUS:
        return False, f"source_status_{status}"
    authorization = _text(getattr(source, "authorization_status", ""))
    if authorization == "restricted_no_derivative":
        return False, "source_restricted_no_derivative"
    return True, ""


def _chunk_available(chunk: Any | None) -> tuple[bool, str]:
    if chunk is None:
        return False, "chunk_missing"
    status = _text(getattr(chunk, "status", "")) or ACTIVE_CHUNK_STATUS
    if status != ACTIVE_CHUNK_STATUS:
        return False, f"chunk_status_{status}"
    if getattr(chunk, "is_active", True) is False:
        return False, "chunk_inactive"
    return True, ""


def source_availability_report(
    session: Any,
    card: Any,
    *,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
) -> PublicationSourceReport:
    evidence = _card_evidence(card, "english") + _card_evidence(card, "chinese")
    chunks_by_uid = _load_chunks(session, chunk_model, evidence)
    sources_by_uid = _load_sources(session, source_model, evidence, chunks_by_uid)
    unavailable_sources: list[dict[str, Any]] = []
    unavailable_chunks: list[dict[str, Any]] = []
    evidence_without_source_refs = 0
    seen_sources: set[str] = set()
    seen_chunks: set[str] = set()

    for item in evidence:
        if not isinstance(item, dict):
            evidence_without_source_refs += 1
            continue
        chunk_uid = _text(item.get("chunk_uid"))
        source_uid = _text(item.get("source_uid"))
        chunk = chunks_by_uid.get(chunk_uid) if chunk_uid else None
        if not source_uid and chunk is not None:
            source_uid = _text(getattr(chunk, "source_uid", ""))
        if not source_uid:
            evidence_without_source_refs += 1
        if chunk_uid and chunk_uid not in seen_chunks:
            chunk_ok, chunk_reason = _chunk_available(chunk)
            if not chunk_ok:
                unavailable_chunks.append({"chunk_uid": chunk_uid, "reason": chunk_reason})
            seen_chunks.add(chunk_uid)
        if source_uid and source_uid not in seen_sources:
            source = sources_by_uid.get(source_uid)
            source_ok, source_reason = _source_available(source)
            if not source_ok:
                unavailable_sources.append({
                    "source_uid": source_uid,
                    "reason": source_reason,
                    "status": _text(getattr(source, "status", "")) if source is not None else "",
                    "source_title": _text(
                        getattr(source, "title", "")
                        or getattr(source, "source_title", "")
                        or getattr(source, "name", "")
                    ) if source is not None else "",
                })
            seen_sources.add(source_uid)

    available = not unavailable_sources and not unavailable_chunks
    return PublicationSourceReport(
        available=available,
        unavailable_sources=unavailable_sources,
        unavailable_chunks=unavailable_chunks,
        evidence_without_source_refs=evidence_without_source_refs,
    )


def assert_sources_available(
    session: Any,
    card: Any,
    *,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
) -> PublicationSourceReport:
    report = source_availability_report(session, card, source_model=source_model, chunk_model=chunk_model)
    if not report.available:
        raise ConceptCardPublicationError(
            "Concept Card evidence source is unavailable.",
            "concept_card_source_unavailable",
            report.to_dict(),
        )
    return report


def card_is_publishable(
    session: Any,
    card: Any,
    *,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
) -> bool:
    if _text(getattr(card, "status", "")) != "approved":
        return False
    return source_availability_report(session, card, source_model=source_model, chunk_model=chunk_model).available


def enrich_evidence_items(
    session: Any,
    items: list[Any],
    *,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
    parse_model: Any | None = None,
    fallback_language: str = "",
) -> list[dict[str, Any]]:
    chunks_by_uid = _load_chunks(session, chunk_model, items)
    sources_by_uid = _load_sources(session, source_model, items, chunks_by_uid)
    parses_by_uid = _load_parse_records(session, parse_model, items, chunks_by_uid)
    enriched: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            raw = {"snippet": _text(raw)}
        chunk_uid = _text(raw.get("chunk_uid"))
        chunk = chunks_by_uid.get(chunk_uid)
        source_uid = _text(raw.get("source_uid") or getattr(chunk, "source_uid", ""))
        source = sources_by_uid.get(source_uid)
        parse_uid = _text(raw.get("parse_uid") or getattr(chunk, "parse_uid", ""))
        parse = parses_by_uid.get(parse_uid)
        page_number = raw.get("page_number")
        if page_number in ("", None) and chunk is not None:
            page_number = getattr(chunk, "page_number", None)
        bbox = _safe_bbox(raw.get("bbox") or raw.get("bounding_box"))
        source_available, source_reason = _source_available(source) if source_uid else (False, "source_reference_missing")
        chunk_available, chunk_reason = _chunk_available(chunk) if chunk_uid else (False, "chunk_reference_missing")
        source_locator = _text(
            raw.get("source_locator")
            or getattr(chunk, "source_locator", "")
            or getattr(chunk, "source_page", "")
            or (f"page:{page_number}" if page_number not in (None, "") else "")
        )
        block_type = _text(raw.get("block_type") or getattr(chunk, "block_type", ""))
        parser_name = _text(
            raw.get("parser")
            or raw.get("parser_name")
            or raw.get("parser_type")
            or getattr(parse, "parser_name", "")
        )
        quality_status = _text(
            raw.get("quality_status")
            or getattr(chunk, "quality_status", "")
            or getattr(source, "quality_status", "")
            or getattr(parse, "quality_status", "")
        )
        enriched.append({
            **raw,
            "chunk_uid": chunk_uid,
            "source_uid": source_uid,
            "source_title": _text(
                raw.get("source_title")
                or getattr(source, "title", "")
                or getattr(source, "source_title", "")
                or getattr(source, "name", "")
                or source_uid
                or "Evidence source"
            ),
            "course": _text(raw.get("course") or getattr(chunk, "course", "") or getattr(source, "course", "")),
            "chapter": _text(raw.get("chapter") or getattr(chunk, "chapter", "") or getattr(source, "chapter", "")),
            "language": _text(raw.get("language") or getattr(chunk, "language", "") or getattr(source, "language", "") or fallback_language),
            "source_role": _text(raw.get("source_role") or raw.get("source_type") or getattr(source, "source_role", "")),
            "trust_level": _text(raw.get("trust_level") or getattr(chunk, "trust_level", "") or getattr(source, "trust_level", "")),
            "quality_status": quality_status,
            "source_locator": source_locator,
            "snippet": _text(raw.get("snippet") or raw.get("evidence_snippet") or raw.get("text") or getattr(chunk, "content", ""))[:600],
            "parse_uid": parse_uid,
            "parse_block_uid": _text(raw.get("parse_block_uid") or getattr(chunk, "parse_block_uid", "")),
            "page_number": page_number,
            "bbox": bbox,
            "bbox_available": bbox is not None,
            "location_available": bool(page_number not in (None, "") or bbox is not None or source_locator),
            "block_type": block_type,
            "parser": parser_name,
            "parse_quality_status": _text(getattr(parse, "quality_status", "")),
            "source_status": _text(getattr(source, "status", "")) if source is not None else "",
            "source_available": bool(source_available and chunk_available),
            "source_unavailable_reason": "" if source_available and chunk_available else source_reason or chunk_reason,
        })
    return enriched


def enrich_card_payload(
    session: Any,
    card: Any,
    payload: dict[str, Any],
    *,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
    parse_model: Any | None = None,
) -> dict[str, Any]:
    report = source_availability_report(session, card, source_model=source_model, chunk_model=chunk_model)
    data = dict(payload)
    data["review_token"] = str(getattr(card, "version", "") or "")
    data["source_availability"] = report.to_dict()
    data["source_unavailable"] = not report.available
    data["english_evidence"] = enrich_evidence_items(
        session,
        _card_evidence(card, "english"),
        source_model=source_model,
        chunk_model=chunk_model,
        parse_model=parse_model,
        fallback_language="en",
    )
    data["chinese_evidence"] = enrich_evidence_items(
        session,
        _card_evidence(card, "chinese"),
        source_model=source_model,
        chunk_model=chunk_model,
        parse_model=parse_model,
        fallback_language="zh",
    )
    return data
