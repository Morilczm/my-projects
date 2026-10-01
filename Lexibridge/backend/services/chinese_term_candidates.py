"""Evidence-constrained Chinese term candidate generation.

This module only extracts candidates from existing governed records. It does
not translate, call an LLM, or assert final bilingual alignment.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_

from services import evidence_retrieval
from services import parse_quality_risk


MAX_CANDIDATE_LIMIT = 50
DEFAULT_CANDIDATE_LIMIT = 10
MAX_MONOLINGUAL_CANDIDATES_PER_CHUNK = 8
SNIPPET_CHARS = 300
WEAK_SCORE_THRESHOLD = 0.45
CHINESE_PATTERN = r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9·\-]{0,31}"
DISALLOWED_CARD_STATUSES = {"rejected", "deprecated"}
APPROVED_CARD_STATUSES = {"approved", "teacher_verified"}
LEGACY_APPROVED_STATUSES = {"approved", "auto_approved", "teacher_verified"}
LOW_TRUST_LEVELS = {"low_quality", "student_uploaded", "unknown"}
BLOCKED_QUALITY_STATUSES = evidence_retrieval.BLOCKED_QUALITY_STATUSES
DEFINITION_PREDICATES = (
    "定义为", "适用于", "表示", "描述", "说明", "反映", "衡量", "用于",
    "等于", "来自", "给出", "属于", "包含", "记录", "刻画", "比较",
    "是", "指", "由",
)
GENERIC_CHINESE_TERMS = {
    "物体", "作用", "过程", "状态", "变化", "现象", "能力", "性质",
    "情况", "方式", "结果", "内容", "对象", "它", "它们", "这", "这种",
}


class ChineseTermCandidateError(ValueError):
    """Raised for controlled Chinese candidate generation failures."""


@dataclass(frozen=True)
class ChineseTermCandidateResult:
    english_term: str
    course: str
    chapter: str
    candidates: list[dict[str, Any]]
    risk_labels: list[str]

    @property
    def total(self) -> int:
        return len(self.candidates)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any, default: int = DEFAULT_CANDIDATE_LIMIT) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _limit(value: Any, default: int = DEFAULT_CANDIDATE_LIMIT) -> int:
    return max(1, min(_as_int(value, default), MAX_CANDIDATE_LIMIT))


def _field(obj: Any, field: str, default: Any = "") -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _labels(value: Any) -> list[str]:
    return parse_quality_risk.normalize_labels(value)


def _merge_labels(*groups: Any) -> list[str]:
    merged: list[str] = []
    for labels in groups:
        merged = parse_quality_risk.merge_risk_labels(merged, labels)
    return merged


def _normalize_term(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value)).lower()


def _normalize_chinese_candidate(value: Any) -> str:
    text = unicodedata.normalize("NFC", _text(value))
    text = re.sub(r"^[：:，,。；;\s]+|[：:，,。；;\s]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text[:80]


def normalize_monolingual_chinese_term(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _normalize_chinese_candidate(value))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"[。；;，,:：]+$", "", text)


def _has_chinese(value: Any) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", _text(value)))


def _candidate_uid(candidate: dict[str, Any]) -> str:
    seed = "|".join(
        _text(candidate.get(key))
        for key in (
            "english_term",
            "chinese_term",
            "source_type",
            "source_uid",
            "chunk_uid",
            "card_uid",
            "term_id",
            "match_pattern",
        )
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _snippet(text: str, query: str, max_chars: int = SNIPPET_CHARS) -> str:
    return evidence_retrieval.highlight_or_extract_snippet(text, query, max_chars=max_chars)


def _source_title(source: Any) -> str:
    return _text(
        _field(source, "title", "")
        or _field(source, "source_title", "")
        or _field(source, "name", "")
    )


def _candidate(
    *,
    english_term: str,
    chinese_term: str,
    course: str = "",
    chapter: str = "",
    source_type: str,
    source_uid: str = "",
    chunk_uid: str = "",
    card_uid: str = "",
    term_id: Any = "",
    evidence_snippet: str = "",
    source_locator: str = "",
    trust_level: str = "unknown",
    quality_status: str = "",
    quality_flags: Any = None,
    match_pattern: str = "",
    risk_labels: Any = None,
    retrieval_reason: str = "",
    parse_uid: str = "",
    parse_block_uid: str = "",
    score_breakdown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    labels = _merge_labels(risk_labels or [], ["candidate_not_alignment_verified"])
    item = {
        "candidate_uid": "",
        "english_term": _text(english_term),
        "chinese_term": _normalize_chinese_candidate(chinese_term),
        "course": _text(course),
        "chapter": _text(chapter),
        "source_type": _text(source_type),
        "source_uid": _text(source_uid),
        "chunk_uid": _text(chunk_uid),
        "card_uid": _text(card_uid),
        "term_id": _text(term_id),
        "evidence_snippet": _snippet(evidence_snippet, english_term),
        "source_locator": _text(source_locator),
        "trust_level": _text(trust_level) or "unknown",
        "quality_status": _text(quality_status),
        "quality_flags": _labels(quality_flags or []),
        "score": 0.0,
        "score_breakdown": score_breakdown or {},
        "match_pattern": _text(match_pattern),
        "risk_labels": labels,
        "retrieval_reason": _text(retrieval_reason),
        "parse_uid": _text(parse_uid),
        "parse_block_uid": _text(parse_block_uid),
    }
    item["candidate_uid"] = _candidate_uid(item)
    return item


def _course_chapter_risks(candidate: dict[str, Any], course: str, chapter: str) -> list[str]:
    risks = []
    if course and candidate.get("course") and _text(candidate.get("course")) != course:
        risks.append("course_mismatch")
    if chapter and candidate.get("chapter") and _text(candidate.get("chapter")) != chapter:
        risks.append("chapter_mismatch")
    return risks


def _quality_risks(status: str, quality_status: str, quality_flags: list[str], trust_level: str) -> list[str]:
    risks = []
    if status == "needs_review":
        risks.append("candidate_from_needs_review_source")
    if quality_status in evidence_retrieval.REVIEW_QUALITY_STATUSES or bool(
        set(quality_flags) & evidence_retrieval.REVIEW_QUALITY_STATUSES
    ):
        risks.append("candidate_from_partial_text")
    if trust_level in LOW_TRUST_LEVELS:
        risks.append("candidate_from_low_trust_source")
    if "formula_ocr_unavailable" in set(quality_flags) or quality_status == "formula_ocr_unavailable":
        risks.append("formula_recognition_unavailable")
    return risks


def _is_blocked_quality(quality_status: Any, quality_flags: Any) -> bool:
    status = _text(quality_status)
    flags = set(_labels(quality_flags or []))
    return status in BLOCKED_QUALITY_STATUSES or bool(flags & BLOCKED_QUALITY_STATUSES)


def _score_base_for_source(candidate: dict[str, Any]) -> float:
    source_type = _text(candidate.get("source_type"))
    labels = set(_labels(candidate.get("risk_labels", [])))
    if source_type == "concept_card":
        return 0.86 if "existing_approved_card_match" in labels else 0.62
    if source_type == "terminology_card":
        return 0.62
    if source_type == "legacy_term":
        return 0.52
    if source_type == "manual":
        return 0.58
    if source_type == "bilingual_chunk":
        return 0.55
    if source_type == "monolingual_chinese_chunk":
        return 0.55
    return 0.45


def score_chinese_term_candidate(candidate: dict[str, Any], context: dict[str, Any] | None = None) -> tuple[float, dict[str, float]]:
    context = dict(context or {})
    risk_labels = set(_labels(candidate.get("risk_labels", [])))
    quality_status = _text(candidate.get("quality_status"))
    quality_flags = set(_labels(candidate.get("quality_flags", [])))
    trust_level = _text(candidate.get("trust_level"))
    source_role = _text(candidate.get("source_role") or candidate.get("source_role_hint"))

    base = _score_base_for_source(candidate)
    exact = 0.08 if _normalize_term(candidate.get("english_term")) == _normalize_term(context.get("english_term")) else 0.0
    course = 0.05 if context.get("course") and _text(candidate.get("course")) == _text(context.get("course")) else 0.0
    chapter = 0.05 if context.get("chapter") and _text(candidate.get("chapter")) == _text(context.get("chapter")) else 0.0
    trust = {
        "official_course": 0.07,
        "teacher_verified": 0.06,
        "reference_material": 0.04,
    }.get(trust_level, 0.0)
    role = 0.04 if source_role in {"bilingual_reference", "chinese_reference_material"} else 0.0
    pattern = 0.04 if "bilingual_pattern_extracted" in risk_labels else 0.0
    structure = {
        "heading": 0.20,
        "list_item": 0.15,
        "so_called_subject": 0.18,
        "called_term": 0.16,
        "definition_subject": 0.14,
    }.get(_text(candidate.get("extraction_method")), 0.0)
    retrieval_rank = max(1, _as_int(candidate.get("retrieval_rank"), 99))
    retrieval = round(0.08 / retrieval_rank, 4)
    length_penalty = -0.04 if len(_text(candidate.get("normalized_text"))) > 12 else 0.0
    repeat = min(0.12, 0.08 * max(0, int(candidate.get("source_count") or 1) - 1))
    review_penalty = -0.08 if "candidate_from_needs_review_source" in risk_labels else 0.0
    partial_penalty = -0.08 if (
        "candidate_from_partial_text" in risk_labels
        or quality_status in evidence_retrieval.REVIEW_QUALITY_STATUSES
        or bool(quality_flags & evidence_retrieval.REVIEW_QUALITY_STATUSES)
    ) else 0.0
    legacy_penalty = -0.07 if "legacy_unverified_source" in risk_labels else 0.0
    low_trust_penalty = -0.10 if "candidate_from_low_trust_source" in risk_labels else 0.0
    course_mismatch_penalty = -0.08 if "course_mismatch" in risk_labels else 0.0
    chapter_mismatch_penalty = -0.08 if "chapter_mismatch" in risk_labels else 0.0

    breakdown = {
        "source_priority": round(base, 4),
        "exact_english_match": round(exact, 4),
        "course_match": round(course, 4),
        "chapter_match": round(chapter, 4),
        "trust_level": round(trust, 4),
        "source_role": round(role, 4),
        "bilingual_pattern": round(pattern, 4),
        "structure_confidence": round(structure, 4),
        "retrieval_rank": retrieval,
        "candidate_length_penalty": length_penalty,
        "duplicate_sources": round(repeat, 4),
        "needs_review_penalty": round(review_penalty, 4),
        "partial_text_penalty": round(partial_penalty, 4),
        "legacy_unverified_penalty": round(legacy_penalty, 4),
        "low_trust_penalty": round(low_trust_penalty, 4),
        "course_mismatch_penalty": round(course_mismatch_penalty, 4),
        "chapter_mismatch_penalty": round(chapter_mismatch_penalty, 4),
    }
    score = max(0.0, min(sum(breakdown.values()), 1.0))
    return round(score, 4), breakdown


def _finalize_candidate(candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    score, breakdown = score_chinese_term_candidate(candidate, context)
    labels = _labels(candidate.get("risk_labels", []))
    if score < WEAK_SCORE_THRESHOLD:
        labels = _merge_labels(labels, ["weak_candidate_score"])
    item = dict(candidate)
    item["score"] = score
    item["score_breakdown"] = {**dict(candidate.get("score_breakdown") or {}), **breakdown}
    item["risk_labels"] = labels
    item["candidate_uid"] = _candidate_uid(item)
    return item


def _valid_monolingual_term(value: str) -> bool:
    text = _normalize_chinese_candidate(value)
    normalized = normalize_monolingual_chinese_term(text)
    if not normalized or len(normalized) > 24 or not _has_chinese(normalized):
        return False
    if normalized in GENERIC_CHINESE_TERMS:
        return False
    if normalized.startswith(("该", "此", "其", "这种", "这些")):
        return False
    if "这一说法" in normalized or any(marker in normalized for marker in ("和", "及")):
        return False
    if any(predicate in normalized for predicate in DEFINITION_PREDICATES):
        return False
    if re.fullmatch(r"[\d\W_]+", normalized) or re.fullmatch(
        r"(?:kg|m|s|a|k|mol|cd|n|j|w|v|c|hz|pa)", normalized, re.IGNORECASE
    ):
        return False
    if re.search(r"[=<>]", normalized):
        return False
    return True


def extract_monolingual_chinese_term_spans(
    text: str,
    *,
    block_type: str = "",
    heading: str = "",
) -> list[dict[str, Any]]:
    """Extract bounded term spans from monolingual Chinese structural signals."""
    source_text = str(text or "")
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()

    def add(raw: str, start: int, end: int, method: str) -> None:
        display = _normalize_chinese_candidate(raw)
        display = re.sub(r"^(?:而|则|其中|其中的)\s*", "", display)
        if not _valid_monolingual_term(display):
            return
        normalized = normalize_monolingual_chinese_term(display)
        key = (normalized, max(0, start), max(start, end))
        if key in seen:
            return
        seen.add(key)
        matches.append({
            "text": display,
            "normalized_text": normalized,
            "start": max(0, start),
            "end": max(start, end),
            "method": method,
        })

    heading_text = _text(heading)
    if block_type in {"heading", "title"}:
        candidate = heading_text or source_text.splitlines()[0] if source_text else heading_text
        if candidate:
            start = source_text.find(candidate)
            add(candidate, max(0, start), max(0, start) + len(candidate), "heading")

    for match in re.finditer(
        r"(?:^|[\n。；;！？])\s*[•·\-—*、\d（）().]+\s*"
        r"(?P<term>[^：:\n。；;！？]{1,24})\s*[：:]",
        source_text,
    ):
        add(match.group("term"), match.start("term"), match.end("term"), "list_item")

    for match in re.finditer(
        r"所谓\s*(?P<term>[^，,。；;！？]{1,24})\s*[，,]\s*是",
        source_text,
    ):
        add(match.group("term"), match.start("term"), match.end("term"), "so_called_subject")

    for match in re.finditer(
        r"将[^。；;！？]{1,60}?称为\s*(?P<term>[^，,。；;！？]{1,24})",
        source_text,
    ):
        add(match.group("term"), match.start("term"), match.end("term"), "called_term")

    for match in re.finditer(
        r"(?:^|[，,。；;！？\n])\s*(?P<term>[^\s，,。；;！？]{1,24})"
        r"与[^，,。；;！？]{1,60}?有关",
        source_text,
    ):
        add(match.group("term"), match.start("term"), match.end("term"), "definition_subject")

    predicate_pattern = "|".join(re.escape(value) for value in DEFINITION_PREDICATES)
    for clause in re.finditer(r"[^，,。；;！？\n]+", source_text):
        raw_clause = clause.group(0)
        subject_match = re.match(
            rf"\s*(?:而|则|其中|其中的)?\s*"
            rf"(?P<term>[^\s：:，,。；;！？]{{1,24}}?)"
            rf"(?:通常|一般|主要|同时|始终|常|则|可)?(?:{predicate_pattern})",
            raw_clause,
        )
        if not subject_match:
            continue
        start = clause.start() + subject_match.start("term")
        end = clause.start() + subject_match.end("term")
        add(subject_match.group("term"), start, end, "definition_subject")

    matches.sort(key=lambda item: (item["start"], item["end"], item["normalized_text"]))
    return matches[:MAX_MONOLINGUAL_CANDIDATES_PER_CHUNK]


def identify_standard_chinese_terms(
    english_term: str,
    retrieved_evidence: list[dict[str, Any]],
    *,
    discipline: str = "",
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> ChineseTermCandidateResult:
    """Identify ranked Chinese term candidates only from retrieved evidence."""
    bounded_limit = _limit(limit)
    raw_candidates: list[dict[str, Any]] = []
    ordered_evidence = sorted(
        list(retrieved_evidence or []),
        key=lambda item: (
            max(1, _as_int(item.get("rank"), 999)),
            _text(item.get("source_uid")),
            _text(item.get("chunk_uid")),
        ),
    )
    for evidence in ordered_evidence[:MAX_CANDIDATE_LIMIT]:
        if _text(evidence.get("language")) != "zh":
            continue
        text = _text(evidence.get("snippet") or evidence.get("evidence_snippet"))
        spans = extract_monolingual_chinese_term_spans(
            text,
            block_type=_text(evidence.get("block_type")),
            heading=_text(evidence.get("heading") or evidence.get("title")),
        )
        for span in spans:
            candidate = _candidate(
                english_term=english_term,
                chinese_term=span["text"],
                source_type="monolingual_chinese_chunk",
                source_uid=evidence.get("source_uid", ""),
                chunk_uid=evidence.get("chunk_uid", ""),
                evidence_snippet=text,
                source_locator=evidence.get("source_locator", ""),
                trust_level=evidence.get("trust_level", "reference_material"),
                quality_status=evidence.get("quality_status", ""),
                quality_flags=evidence.get("quality_flags", []),
                risk_labels=["monolingual_chinese_term_extracted"],
                retrieval_reason="term structure extracted from retrieved Chinese evidence",
                parse_uid=evidence.get("parse_uid", ""),
                parse_block_uid=evidence.get("parse_block_uid", ""),
                match_pattern=span["method"],
                score_breakdown={"retrieval_score": evidence.get("score", 0.0)},
            )
            candidate.update({
                "normalized_text": span["normalized_text"],
                "original_span": span["text"],
                "span_start": span["start"],
                "span_end": span["end"],
                "extraction_method": span["method"],
                "source_language": "zh",
                "retrieval_rank": max(1, _as_int(evidence.get("rank"), 999)),
                "retrieval_score": float(evidence.get("score") or 0.0),
                "discipline": _text(discipline),
                "provenance": dict(evidence.get("provenance") or {
                    "source_uid": _text(evidence.get("source_uid")),
                    "chunk_uid": _text(evidence.get("chunk_uid")),
                }),
            })
            candidate["candidate_uid"] = _candidate_uid(candidate)
            raw_candidates.append(candidate)
    ranked = merge_and_rank_chinese_candidates(
        raw_candidates,
        bounded_limit,
        context={"english_term": english_term},
    )
    for rank, candidate in enumerate(ranked, 1):
        candidate["rank"] = rank
    risks = ["candidate_not_alignment_verified"]
    if not ranked:
        risks.append("no_chinese_candidate_found")
    if len(ranked) > 1:
        risks.append("ambiguous_chinese_candidates")
    return ChineseTermCandidateResult(
        english_term=_text(english_term),
        course="",
        chapter="",
        candidates=ranked,
        risk_labels=_merge_labels(risks),
    )


def _matches_course_chapter(obj: Any, course: str, chapter: str, strict: bool = True) -> bool:
    if course and _text(_field(obj, "course", "")) and _text(_field(obj, "course", "")) != course:
        return not strict
    if chapter and _text(_field(obj, "chapter", "")) and _text(_field(obj, "chapter", "")) != chapter:
        return not strict
    return True


def find_candidates_from_existing_concept_cards(
    session: Any,
    concept_card_model: Any,
    english_term: str,
    course: str | None = None,
    chapter: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del filters
    term = _text(english_term)
    if not term:
        raise ChineseTermCandidateError("english_term is required.")
    course = _text(course)
    chapter = _text(chapter)
    query = session.query(concept_card_model).filter(concept_card_model.english_term == term)
    if hasattr(concept_card_model, "status"):
        query = query.filter(~concept_card_model.status.in_(sorted(DISALLOWED_CARD_STATUSES)))
    cards = query.order_by(concept_card_model.id.desc()).limit(max(_limit(limit) * 3, 30)).all()
    candidates = []
    for card in cards:
        chinese_term = _normalize_chinese_candidate(_field(card, "chinese_term", ""))
        if not chinese_term or not _has_chinese(chinese_term):
            continue
        if _is_blocked_quality(_field(card, "parse_quality_status", ""), _field(card, "parse_quality_flags", [])):
            continue
        status = _text(_field(card, "status", ""))
        risk_labels = []
        if status in APPROVED_CARD_STATUSES:
            risk_labels.append("existing_approved_card_match")
        else:
            risk_labels.extend(["existing_unapproved_card_match", "candidate_from_needs_review_source"])
        risk_labels.extend(_course_chapter_risks({"course": _field(card, "course", ""), "chapter": _field(card, "chapter", "")}, course, chapter))
        candidates.append(
            _candidate(
                english_term=term,
                chinese_term=chinese_term,
                course=_field(card, "course", ""),
                chapter=_field(card, "chapter", ""),
                source_type="concept_card",
                card_uid=_field(card, "card_uid", ""),
                evidence_snippet=f"{_field(card, 'english_term', '')} / {chinese_term}",
                quality_status=_field(card, "parse_quality_status", ""),
                quality_flags=_field(card, "parse_quality_flags", []),
                trust_level="teacher_verified" if status in APPROVED_CARD_STATUSES else "unknown",
                risk_labels=risk_labels,
                retrieval_reason="existing ConceptAlignmentCard english_term match",
                parse_uid=_field(card, "parse_uid", ""),
                parse_block_uid=_field(card, "parse_block_uid", ""),
                match_pattern="concept_card_exact_english_match",
            )
        )
    return candidates[: _limit(limit)]


def _legacy_chinese_term(obj: Any) -> str:
    return _normalize_chinese_candidate(
        _field(obj, "final_chinese_term", "")
        or _field(obj, "chinese_term", "")
        or _field(obj, "ai_translation_candidate", "")
    )


def _legacy_source_type(obj: Any) -> str:
    return "terminology_card" if obj.__class__.__name__ == "TerminologyCard" else "legacy_term"


def _legacy_status(obj: Any) -> str:
    return _text(_field(obj, "status", "") or _field(obj, "review_status", "") or _field(obj, "alignment_status", ""))


def _legacy_query(session: Any, model: Any, english_term: str, limit: int) -> list[Any]:
    if model is None:
        return []
    conditions = []
    if hasattr(model, "english_term"):
        conditions.append(model.english_term == english_term)
    if hasattr(model, "normalized_english_term"):
        conditions.append(model.normalized_english_term == _normalize_term(english_term))
    if not conditions:
        return []
    return session.query(model).filter(or_(*conditions)).order_by(model.id.desc()).limit(max(_limit(limit) * 3, 30)).all()


def find_candidates_from_legacy_terms(
    session: Any,
    term_model: Any | None,
    terminology_card_model: Any | None,
    english_term: str,
    course: str | None = None,
    chapter: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del filters
    term = _text(english_term)
    if not term:
        raise ChineseTermCandidateError("english_term is required.")
    course = _text(course)
    chapter = _text(chapter)
    records = [*_legacy_query(session, term_model, term, limit), *_legacy_query(session, terminology_card_model, term, limit)]
    candidates = []
    for record in records:
        chinese_term = _legacy_chinese_term(record)
        if not chinese_term or not _has_chinese(chinese_term):
            continue
        status = _legacy_status(record)
        quality_flags = _field(record, "parse_quality_flags", []) or _field(record, "quality_flags_json", [])
        if status in {"blocked", "deprecated", "rejected"} or _is_blocked_quality(_field(record, "parse_quality_status", ""), quality_flags):
            continue
        source_type = _legacy_source_type(record)
        risk_labels = []
        if status not in LEGACY_APPROVED_STATUSES:
            risk_labels.append("legacy_unverified_source")
        risk_labels.extend(_course_chapter_risks({"course": _field(record, "course", ""), "chapter": _field(record, "chapter", "")}, course, chapter))
        risk_labels.extend(_quality_risks(status, _field(record, "parse_quality_status", ""), _labels(quality_flags), "unknown"))
        evidence = (
            _field(record, "courseware_sentence", "")
            or _field(record, "context", "")
            or _field(record, "english_kb_evidence", "")
            or f"{term} / {chinese_term}"
        )
        candidates.append(
            _candidate(
                english_term=term,
                chinese_term=chinese_term,
                course=_field(record, "course", ""),
                chapter=_field(record, "chapter", ""),
                source_type=source_type,
                term_id=_field(record, "id", ""),
                evidence_snippet=evidence,
                trust_level="teacher_verified" if status in LEGACY_APPROVED_STATUSES else "unknown",
                quality_status=_field(record, "parse_quality_status", ""),
                quality_flags=quality_flags,
                risk_labels=risk_labels,
                retrieval_reason="legacy terminology english_term match",
                parse_uid=_field(record, "parse_uid", ""),
                parse_block_uid=_field(record, "parse_block_uid", ""),
                match_pattern=f"{source_type}_exact_english_match",
            )
        )
    return candidates[: _limit(limit)]


def _escaped_english_pattern(english_term: str) -> str:
    return re.escape(_text(english_term))


def extract_chinese_candidates_from_text_around_english_term(text: str, english_term: str) -> list[dict[str, str]]:
    source_text = str(text or "")
    term_pattern = _escaped_english_pattern(english_term)
    if not source_text or not term_pattern:
        return []
    patterns = [
        (rf"(?P<zh>{CHINESE_PATTERN})\s*[（(]\s*{term_pattern}\s*[）)]", "zh_before_parentheses_en"),
        (rf"{term_pattern}\s*[（(]\s*(?P<zh>{CHINESE_PATTERN})\s*[）)]", "en_before_parentheses_zh"),
        (rf"(?P<zh>{CHINESE_PATTERN})\s*[，,、：:;；]?\s*(?:又称|也称|即|称为)\s*{term_pattern}", "zh_alias_en"),
        (rf"{term_pattern}\s*[，,、：:;；]?\s*(?:即|又称|也称|称为)\s*(?P<zh>{CHINESE_PATTERN})", "en_alias_zh"),
    ]
    matches: list[dict[str, str]] = []
    seen = set()
    for pattern, name in patterns:
        for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
            chinese_term = _normalize_chinese_candidate(match.group("zh"))
            if not chinese_term or not _has_chinese(chinese_term) or chinese_term in seen:
                continue
            seen.add(chinese_term)
            matches.append({
                "chinese_term": chinese_term,
                "match_pattern": name,
                "evidence_snippet": _snippet(source_text[max(0, match.start() - 120): match.end() + 120], english_term),
            })
    return matches


def find_candidates_from_bilingual_chunks(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    english_term: str,
    course: str | None = None,
    chapter: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    term = _text(english_term)
    if not term:
        raise ChineseTermCandidateError("english_term is required.")
    base_filters = dict(filters or {})
    if course:
        base_filters["course"] = _text(course)
    if chapter:
        base_filters["chapter"] = _text(chapter)
    candidates = []
    search_scopes = (
        ("mixed", "bilingual_reference", "bilingual pattern extracted from governed KnowledgeChunk"),
        ("zh", "chinese_reference_material", "explicit bilingual pattern extracted from governed Chinese KnowledgeChunk"),
    )
    for language, source_role, retrieval_reason in search_scopes:
        if base_filters.get("language") and base_filters.get("language") != language:
            continue
        if base_filters.get("source_role") and base_filters.get("source_role") != source_role:
            continue
        search_filters = {
            **base_filters,
            "language": language,
            "source_role": source_role,
        }
        result = evidence_retrieval.search_evidence(
            session,
            chunk_model,
            source_model,
            term,
            filters=search_filters,
            limit=max(_limit(limit) * 3, 20),
        )
        for evidence in result.candidates:
            extracted = extract_chinese_candidates_from_text_around_english_term(evidence.get("snippet", ""), term)
            if not extracted:
                extracted = extract_chinese_candidates_from_text_around_english_term(evidence.get("evidence_snippet", ""), term)
            for item in extracted:
                status = _text(evidence.get("status"))
                quality_status = _text(evidence.get("quality_status"))
                quality_flags = _labels(evidence.get("quality_flags", []))
                trust_level = _text(evidence.get("trust_level"))
                risk_labels = _merge_labels(
                    ["bilingual_pattern_extracted"],
                    _quality_risks(status, quality_status, quality_flags, trust_level),
                    _course_chapter_risks(evidence, _text(course), _text(chapter)),
                    evidence.get("risk_labels", []),
                )
                source_type = "manual" if evidence.get("source_type") in {"manual", "teacher_upload"} else "bilingual_chunk"
                if evidence.get("block_type") == "table" or evidence.get("source_type") == "manual":
                    risk_labels = _merge_labels(risk_labels, ["table_parse_risk"])
                candidates.append(
                    _candidate(
                        english_term=term,
                        chinese_term=item["chinese_term"],
                        course=evidence.get("course", ""),
                        chapter=evidence.get("chapter", ""),
                        source_type=source_type,
                        source_uid=evidence.get("source_uid", ""),
                        chunk_uid=evidence.get("chunk_uid", ""),
                        evidence_snippet=item["evidence_snippet"],
                        source_locator=evidence.get("source_locator", ""),
                        trust_level=trust_level,
                        quality_status=quality_status,
                        quality_flags=quality_flags,
                        risk_labels=risk_labels,
                        retrieval_reason=retrieval_reason,
                        parse_uid=evidence.get("parse_uid", ""),
                        parse_block_uid=evidence.get("parse_block_uid", ""),
                        match_pattern=item["match_pattern"],
                        score_breakdown={"retrieval_score": evidence.get("score", 0.0)},
                    )
                )
    return candidates[: _limit(limit)]


def merge_and_rank_chinese_candidates(
    candidates: list[dict[str, Any]],
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    context = dict(context or {})
    merged_by_term: dict[str, dict[str, Any]] = {}
    source_priority = {
        "concept_card": 5,
        "terminology_card": 4,
        "bilingual_chunk": 3,
        "manual": 3,
        "legacy_term": 2,
        "monolingual_chinese_chunk": 3,
    }
    for raw in candidates:
        chinese_term = _normalize_chinese_candidate(raw.get("chinese_term"))
        if not chinese_term:
            continue
        key = chinese_term.lower()
        item = dict(raw)
        item["chinese_term"] = chinese_term
        existing = merged_by_term.get(key)
        if existing is None:
            item["source_count"] = 1
            item["source_uids"] = [item.get("source_uid", "")]
            item["chunk_uids"] = [item.get("chunk_uid", "")]
            item["source_types"] = [item.get("source_type", "")]
            merged_by_term[key] = item
            continue
        existing["source_count"] = int(existing.get("source_count") or 1) + 1
        existing["risk_labels"] = _merge_labels(existing.get("risk_labels", []), item.get("risk_labels", []))
        existing["source_uids"] = sorted({*existing.get("source_uids", []), item.get("source_uid", "")})
        existing["chunk_uids"] = sorted({*existing.get("chunk_uids", []), item.get("chunk_uid", "")})
        existing["source_types"] = sorted({*existing.get("source_types", []), item.get("source_type", "")})
        if not existing.get("evidence_snippet") and item.get("evidence_snippet"):
            existing["evidence_snippet"] = item["evidence_snippet"]
        if source_priority.get(item.get("source_type", ""), 0) > source_priority.get(existing.get("source_type", ""), 0):
            for field in ("source_type", "card_uid", "term_id", "course", "chapter", "trust_level", "quality_status", "quality_flags", "match_pattern", "retrieval_reason"):
                existing[field] = item.get(field, existing.get(field))
    ranked = [_finalize_candidate(candidate, context) for candidate in merged_by_term.values()]
    ranked.sort(key=lambda item: (
        -float(item.get("score") or 0.0),
        max(1, _as_int(item.get("retrieval_rank"), 999)),
        _text(item.get("source_uid")),
        _text(item.get("chunk_uid")),
        _text(item.get("normalized_text") or item.get("chinese_term")),
    ))
    return ranked[: _limit(limit)]


def generate_chinese_term_candidates(
    session: Any,
    *,
    concept_card_model: Any | None,
    term_model: Any | None,
    terminology_card_model: Any | None,
    chunk_model: Any | None,
    source_model: Any | None,
    english_term: str,
    course: str | None = None,
    chapter: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    filters: dict[str, Any] | None = None,
    audit_context: dict[str, Any] | None = None,
) -> ChineseTermCandidateResult:
    del audit_context
    term = _text(english_term)
    if not term:
        raise ChineseTermCandidateError("english_term is required.")
    effective_limit = _limit(limit)
    context = {"english_term": term, "course": _text(course), "chapter": _text(chapter)}
    candidates: list[dict[str, Any]] = []
    if concept_card_model is not None:
        candidates.extend(find_candidates_from_existing_concept_cards(session, concept_card_model, term, course, chapter, effective_limit, filters))
    candidates.extend(find_candidates_from_legacy_terms(session, term_model, terminology_card_model, term, course, chapter, effective_limit, filters))
    if chunk_model is not None and source_model is not None:
        candidates.extend(find_candidates_from_bilingual_chunks(session, chunk_model, source_model, term, course, chapter, effective_limit, filters))
    ranked = merge_and_rank_chinese_candidates(candidates, effective_limit, context=context)
    risks = ["candidate_not_alignment_verified"]
    if not ranked:
        risks.append("no_chinese_candidate_found")
    if len(ranked) > 1:
        risks.append("ambiguous_chinese_candidates")
    if ranked and float(ranked[0].get("score") or 0) < WEAK_SCORE_THRESHOLD:
        risks.append("weak_candidate_score")
    for candidate in ranked:
        risks = _merge_labels(risks, candidate.get("risk_labels", []))
    return ChineseTermCandidateResult(
        english_term=term,
        course=_text(course),
        chapter=_text(chapter),
        candidates=ranked,
        risk_labels=_merge_labels(risks),
    )


def serialize_chinese_term_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return dict(candidate or {})
