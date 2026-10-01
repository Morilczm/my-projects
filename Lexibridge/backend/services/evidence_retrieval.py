"""Lexical evidence retrieval over governed KnowledgeChunk records.

This module intentionally avoids vector search, embeddings, reranking, or LLM
calls. It returns structured evidence candidates from governed chunks only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_

from services import formula_detection
from services import parse_quality_risk


MAX_LIMIT = 50
DEFAULT_LIMIT = 10
DEFAULT_SNIPPET_CHARS = 300

ACTIVE_STATUSES = {"active"}
REVIEW_STATUSES = {"needs_review"}
ALLOWED_SOURCE_STATUSES = ACTIVE_STATUSES | REVIEW_STATUSES
ALLOWED_CHUNK_STATUSES = ACTIVE_STATUSES | REVIEW_STATUSES
BLOCKED_QUALITY_STATUSES = parse_quality_risk.BLOCKED_QUALITY_STATUSES | {"ocr_required"}
REVIEW_QUALITY_STATUSES = {
    "partial_text",
    "mixed_quality",
    "ocr_low_confidence",
    "formula_detected",
    "formula_ocr_required",
    "formula_ocr_unavailable",
}
TRUST_WEIGHTS = {
    "official_course": 0.10,
    "teacher_verified": 0.08,
    "reference_material": 0.05,
    "student_uploaded": 0.02,
    "unknown": 0.0,
    "low_quality": -0.20,
}
SOURCE_ROLE_WEIGHTS = {
    ("en", "english_course_material"): 0.05,
    ("zh", "chinese_reference_material"): 0.05,
    ("mixed", "bilingual_reference"): 0.03,
}


class EvidenceRetrievalError(ValueError):
    """Raised for controlled evidence retrieval validation failures."""


@dataclass(frozen=True)
class EvidenceSearchResult:
    query: str
    filters: dict[str, Any]
    candidates: list[dict[str, Any]]

    @property
    def total(self) -> int:
        return len(self.candidates)


def _loads_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int = DEFAULT_LIMIT) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", str(text or ""))]


def _field(obj: Any, field: str, default: Any = "") -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _chunk_text(chunk: Any) -> str:
    return _text(_field(chunk, "content", "") or _field(chunk, "text", "") or _field(chunk, "normalized_text", ""))


def _source_uid(chunk: Any, source: Any = None) -> str:
    return _text(_field(source, "source_uid", "") or _field(chunk, "source_uid", ""))


def _source_title(chunk: Any, source: Any = None) -> str:
    return _text(
        _field(source, "title", "")
        or _field(source, "source_title", "")
        or _field(source, "name", "")
        or _field(chunk, "title", "")
    )


def _combined_field(chunk: Any, source: Any, field: str, default: str = "") -> str:
    return _text(_field(chunk, field, "") or _field(source, field, "") or default)


def _quality_flags(chunk: Any, source: Any = None) -> list[str]:
    flags = []
    for value in (_field(source, "quality_flags", []), _field(chunk, "quality_flags", [])):
        parsed = _loads_json(value, [])
        if isinstance(parsed, list):
            flags.extend(str(item).strip() for item in parsed if str(item or "").strip())
    seen = set()
    normalized = []
    for flag in flags:
        if flag not in seen:
            normalized.append(flag)
            seen.add(flag)
    raw_formula_blocks = _field(chunk, "formula_block_ids_json", None)
    formula_blocks = _loads_json(raw_formula_blocks, None)
    if (
        _combined_field(chunk, source, "scope_type", "").casefold() == "personal"
        and raw_formula_blocks is not None
        and formula_blocks == []
        and not formula_detection.contains_substantive_formula_text(
            _chunk_text(chunk)
        )
    ):
        # Compatibility for documents processed by the former punctuation-
        # based detector.  Do not mutate persisted provenance; suppress only
        # the stale formula risks for a chunk that explicitly has zero layout
        # formula blocks and no formula signal under the current detector.
        stale_formula_flags = {
            "formula_detected",
            "formula_ocr_required",
            "formula_ocr_unavailable",
        }
        normalized = [
            flag for flag in normalized if flag not in stale_formula_flags
        ]
    return normalized


def normalize_evidence_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(filters or {})
    raw_source_uids = raw.get("source_uids") or []
    if isinstance(raw_source_uids, str):
        raw_source_uids = [raw_source_uids]
    source_uids = tuple(sorted({
        _text(value) for value in raw_source_uids if _text(value)
    }))
    normalized = {
        "course": _text(raw.get("course")),
        "chapter": _text(raw.get("chapter")),
        "language": _text(raw.get("language")),
        "source_type": _text(raw.get("source_type")),
        "source_role": _text(raw.get("source_role")),
        "trust_level": _text(raw.get("trust_level")),
        "quality_status": _text(raw.get("quality_status")),
        "status": _text(raw.get("status")),
        "source_uid": _text(raw.get("source_uid")),
        "source_uids": source_uids,
        "visibility": _text(raw.get("visibility")),
        "include_low_quality": _as_bool(raw.get("include_low_quality")),
        "include_needs_review": _as_bool(raw.get("include_needs_review")),
        "limit": max(1, min(_as_int(raw.get("limit"), DEFAULT_LIMIT), MAX_LIMIT)),
    }
    return {key: value for key, value in normalized.items() if value not in ("", None)}


def _matches_filter(value: str, expected: str) -> bool:
    return not expected or _text(value).lower() == _text(expected).lower()


def _is_review_quality(quality_status: str, quality_flags: list[str]) -> bool:
    return quality_status in REVIEW_QUALITY_STATUSES or bool(set(quality_flags) & REVIEW_QUALITY_STATUSES)


def should_include_chunk_as_evidence(chunk: Any, filters: dict[str, Any] | None = None, source: Any = None) -> bool:
    filters = normalize_evidence_filters(filters)
    text = _chunk_text(chunk)
    if not text:
        return False
    if not _source_uid(chunk, source):
        return False
    if filters.get("source_uids") and _source_uid(chunk, source) not in set(filters["source_uids"]):
        return False

    chunk_status = _combined_field(chunk, source, "status", "active")
    if filters.get("status") and not _matches_filter(chunk_status, filters["status"]):
        return False
    if chunk_status not in ALLOWED_CHUNK_STATUSES:
        return False
    if chunk_status in REVIEW_STATUSES and not filters.get("include_needs_review"):
        return False

    source_status = _text(_field(source, "status", "active") or "active")
    if source_status not in ALLOWED_SOURCE_STATUSES:
        return False
    if source_status in REVIEW_STATUSES and not filters.get("include_needs_review"):
        return False

    source_quality_status = _text(_field(source, "quality_status", ""))
    chunk_quality_status = _text(_field(chunk, "quality_status", ""))
    quality_status = chunk_quality_status or source_quality_status
    quality_flags = _quality_flags(chunk, source)
    if filters.get("quality_status") and not _matches_filter(quality_status, filters["quality_status"]):
        return False
    if (
        chunk_quality_status in BLOCKED_QUALITY_STATUSES
        or source_quality_status in BLOCKED_QUALITY_STATUSES
        or bool(set(quality_flags) & BLOCKED_QUALITY_STATUSES)
    ):
        return False
    if _is_review_quality(quality_status, quality_flags) and not filters.get("include_needs_review"):
        return False

    source_trust_level = _text(_field(source, "trust_level", ""))
    chunk_trust_level = _text(_field(chunk, "trust_level", ""))
    trust_level = chunk_trust_level or source_trust_level or "unknown"
    if filters.get("trust_level") and not _matches_filter(trust_level, filters["trust_level"]):
        return False
    if (trust_level == "low_quality" or source_trust_level == "low_quality") and not filters.get("include_low_quality"):
        return False

    checks = {
        "course": _combined_field(chunk, source, "course", ""),
        "chapter": _combined_field(chunk, source, "chapter", ""),
        "language": _combined_field(chunk, source, "language", ""),
        "visibility": _combined_field(chunk, source, "visibility", ""),
        "source_uid": _source_uid(chunk, source),
        "source_type": _text(_field(source, "source_type", "")),
        "source_role": _text(_field(source, "source_role", "")),
    }
    for field, value in checks.items():
        if filters.get(field) and not _matches_filter(value, filters[field]):
            return False
    return True


def _match_terms(query: str, text: str) -> tuple[list[str], bool, float]:
    lowered_query = _text(query).lower()
    lowered_text = str(text or "").lower()
    tokens = _tokens(query)
    matched = []
    phrase_match = bool(lowered_query and lowered_query in lowered_text)
    if phrase_match:
        matched.append(_text(query))
    for token in tokens:
        if token and token in lowered_text and token not in matched:
            matched.append(token)
    coverage = (len([token for token in tokens if token in lowered_text]) / len(tokens)) if tokens else 0.0
    return matched, phrase_match, coverage


def score_chunk_lexical(
    query: str,
    chunk: Any,
    filters: dict[str, Any] | None = None,
    source: Any = None,
) -> tuple[float, list[str], dict[str, float]]:
    filters = normalize_evidence_filters(filters)
    text = _chunk_text(chunk)
    matched_terms, phrase_match, coverage = _match_terms(query, text)
    if not matched_terms:
        return 0.0, [], {"lexical": 0.0}

    phrase_score = 0.45 if phrase_match else 0.0
    token_score = min(0.30, 0.30 * coverage)
    frequency_score = min(0.05, 0.01 * sum(str(text).lower().count(term.lower()) for term in matched_terms))
    course_score = 0.05 if filters.get("course") and _matches_filter(_combined_field(chunk, source, "course", ""), filters["course"]) else 0.0
    chapter_score = 0.05 if filters.get("chapter") and _matches_filter(_combined_field(chunk, source, "chapter", ""), filters["chapter"]) else 0.0
    language = _combined_field(chunk, source, "language", "")
    source_role = _text(_field(source, "source_role", ""))
    source_role_score = SOURCE_ROLE_WEIGHTS.get((language, source_role), 0.0)
    trust_level = _combined_field(chunk, source, "trust_level", "unknown")
    trust_score = TRUST_WEIGHTS.get(trust_level, 0.0)

    quality_status = _combined_field(chunk, source, "quality_status", "")
    quality_flags = _quality_flags(chunk, source)
    review_penalty = -0.10 if _is_review_quality(quality_status, quality_flags) or _combined_field(chunk, source, "status", "") == "needs_review" else 0.0

    breakdown = {
        "phrase": round(phrase_score, 4),
        "token_coverage": round(token_score, 4),
        "frequency": round(frequency_score, 4),
        "course": round(course_score, 4),
        "chapter": round(chapter_score, 4),
        "source_role": round(source_role_score, 4),
        "trust_level": round(trust_score, 4),
        "quality_penalty": round(review_penalty, 4),
    }
    score = sum(breakdown.values())
    return round(max(0.0, min(score, 1.0)), 4), matched_terms, breakdown


def highlight_or_extract_snippet(text: str, query: str, max_chars: int = DEFAULT_SNIPPET_CHARS) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    lowered_text = text.lower()
    lowered_query = _text(query).lower()
    idx = lowered_text.find(lowered_query) if lowered_query else -1
    if idx < 0:
        tokens = _tokens(query)
        idx = min([lowered_text.find(token) for token in tokens if lowered_text.find(token) >= 0] or [0])
    half = max_chars // 2
    start = max(0, idx - half)
    end = min(len(text), start + max_chars)
    start = max(0, end - max_chars)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text):
        snippet = f"{snippet}..."
    return snippet[: max_chars + 6]


def _risk_labels(chunk: Any, source: Any = None) -> list[str]:
    metadata = {
        "parse_quality_status": _combined_field(chunk, source, "quality_status", ""),
        "parse_quality_flags": _quality_flags(chunk, source),
    }
    labels = parse_quality_risk.parse_quality_to_risk_labels(metadata)
    if _combined_field(chunk, source, "status", "") == "needs_review":
        labels = parse_quality_risk.merge_risk_labels(labels, ["needs_review_evidence"])
    if _combined_field(chunk, source, "trust_level", "") == "low_quality":
        labels = parse_quality_risk.merge_risk_labels(labels, ["low_quality_source"])
    return labels


def build_evidence_candidate(
    chunk: Any,
    query: str,
    score: float,
    matched_terms: list[str],
    reason: str,
    *,
    source: Any = None,
    score_breakdown: dict[str, float] | None = None,
) -> dict[str, Any]:
    chunk_uid = _text(_field(chunk, "chunk_uid", ""))
    source_uid = _source_uid(chunk, source)
    evidence_seed = f"{source_uid}:{chunk_uid}:{_text(query).lower()}"
    return {
        "evidence_uid": hashlib.sha256(evidence_seed.encode("utf-8")).hexdigest()[:24],
        "chunk_uid": chunk_uid,
        "source_uid": source_uid,
        "source_title": _source_title(chunk, source),
        "course": _combined_field(chunk, source, "course", ""),
        "chapter": _combined_field(chunk, source, "chapter", ""),
        "language": _combined_field(chunk, source, "language", "unknown"),
        "source_type": _text(_field(source, "source_type", "")),
        "source_role": _text(_field(source, "source_role", "")),
        "trust_level": _combined_field(chunk, source, "trust_level", "unknown"),
        "quality_status": _combined_field(chunk, source, "quality_status", ""),
        "quality_flags": _quality_flags(chunk, source),
        "visibility": _combined_field(chunk, source, "visibility", ""),
        "status": _combined_field(chunk, source, "status", ""),
        "source_locator": _text(_field(chunk, "source_locator", "") or _field(chunk, "source_section", "")),
        "page_number": _field(chunk, "page_number", None),
        "slide_number": _field(chunk, "slide_number", None),
        "snippet": highlight_or_extract_snippet(_chunk_text(chunk), query),
        "matched_terms": matched_terms,
        "score": round(max(0.0, min(float(score or 0), 1.0)), 4),
        "score_breakdown": score_breakdown or {},
        "retrieval_reason": reason,
        "risk_labels": _risk_labels(chunk, source),
        "parse_uid": _combined_field(chunk, source, "parse_uid", ""),
        "parse_block_uid": _text(_field(chunk, "parse_block_uid", "")),
    }


def serialize_evidence_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return dict(candidate or {})


def _sources_for_chunks(session: Any, source_model: Any, chunks: list[Any]) -> dict[tuple[str, Any], Any]:
    source_uids = sorted({_text(_field(chunk, "source_uid", "")) for chunk in chunks if _text(_field(chunk, "source_uid", ""))})
    source_ids = sorted({
        _field(chunk, "knowledge_source_id", None) or _field(chunk, "source_id", None)
        for chunk in chunks
        if _field(chunk, "knowledge_source_id", None) or _field(chunk, "source_id", None)
    })
    if not source_uids and not source_ids:
        return {}
    conditions = []
    if source_uids:
        conditions.append(source_model.source_uid.in_(source_uids))
    if source_ids:
        conditions.append(source_model.id.in_(source_ids))
    sources = session.query(source_model).filter(or_(*conditions)).all()
    mapping = {}
    for source in sources:
        mapping[("uid", _text(_field(source, "source_uid", "")))] = source
        mapping[("id", _field(source, "id", None))] = source
    return mapping


def _source_for_chunk(chunk: Any, source_map: dict[tuple[str, Any], Any]) -> Any:
    return (
        source_map.get(("uid", _text(_field(chunk, "source_uid", ""))))
        or source_map.get(("id", _field(chunk, "knowledge_source_id", None)))
        or source_map.get(("id", _field(chunk, "source_id", None)))
    )


def search_knowledge_chunks_lexical(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    query: str,
    filters: dict[str, Any] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    normalized_query = _text(query)
    if not normalized_query:
        raise EvidenceRetrievalError("query is required.")
    normalized_filters = normalize_evidence_filters({**(filters or {}), "limit": limit})
    effective_limit = normalized_filters.get("limit", DEFAULT_LIMIT)

    chunk_query = session.query(chunk_model)
    if hasattr(chunk_model, "content"):
        chunk_query = chunk_query.filter(chunk_model.content != "")
    for field in ("course", "chapter", "language", "quality_status", "status", "source_uid", "visibility", "trust_level"):
        value = normalized_filters.get(field)
        if value and hasattr(chunk_model, field):
            chunk_query = chunk_query.filter(getattr(chunk_model, field) == value)
    if hasattr(chunk_model, "status"):
        chunk_query = chunk_query.filter(chunk_model.status.in_(sorted(ALLOWED_CHUNK_STATUSES)))
    if hasattr(chunk_model, "quality_status"):
        chunk_query = chunk_query.filter(~chunk_model.quality_status.in_(sorted(BLOCKED_QUALITY_STATUSES)))
    if hasattr(chunk_model, "trust_level") and not normalized_filters.get("include_low_quality"):
        chunk_query = chunk_query.filter(chunk_model.trust_level != "low_quality")

    chunks = chunk_query.order_by(chunk_model.id.desc()).limit(max(effective_limit * 20, 100)).all()
    source_map = _sources_for_chunks(session, source_model, chunks)
    candidates = []
    for chunk in chunks:
        source = _source_for_chunk(chunk, source_map)
        if not should_include_chunk_as_evidence(chunk, normalized_filters, source=source):
            continue
        score, matched_terms, score_breakdown = score_chunk_lexical(normalized_query, chunk, normalized_filters, source)
        if score <= 0:
            continue
        candidate = build_evidence_candidate(
            chunk,
            normalized_query,
            score,
            matched_terms,
            "lexical phrase/token match over governed KnowledgeChunk",
            source=source,
            score_breakdown=score_breakdown,
        )
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    return candidates[:effective_limit]


def search_evidence(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    query: str,
    filters: dict[str, Any] | None = None,
    limit: int = DEFAULT_LIMIT,
    audit_context: dict[str, Any] | None = None,
) -> EvidenceSearchResult:
    del audit_context
    normalized_filters = normalize_evidence_filters({**(filters or {}), "limit": limit})
    candidates = search_knowledge_chunks_lexical(
        session,
        chunk_model,
        source_model,
        query,
        normalized_filters,
        normalized_filters.get("limit", DEFAULT_LIMIT),
    )
    return EvidenceSearchResult(query=_text(query), filters=normalized_filters, candidates=candidates)


def attach_evidence_candidates_to_card_payload(
    card_payload: dict[str, Any],
    english_candidates: list[dict[str, Any]] | None = None,
    chinese_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(card_payload or {})
    if english_candidates is not None:
        payload["english_evidence"] = [serialize_evidence_candidate(candidate) for candidate in english_candidates]
    if chinese_candidates is not None:
        payload["chinese_evidence"] = [serialize_evidence_candidate(candidate) for candidate in chinese_candidates]
    payload.setdefault("status", "needs_review")
    return payload
