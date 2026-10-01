"""Bilingual evidence retrieval workflow for Concept Card draft payloads.

The workflow only retrieves governed evidence and prepares a draft payload. It
does not call an LLM, verify final alignment, invent confidence, or approve a
ConceptAlignmentCard.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from services import chinese_term_candidates
from services import bilingual_evidence_qualification
from services import bilingual_semantic_pairing
from services import cross_language_retrieval
from services import evidence_retrieval
from services import parse_quality_risk
from services.local_multilingual_embedding import LocalMultilingualEmbeddingBackend
from services.local_bilingual_reranker import (
    BILINGUAL_RERANKER_BACKEND_UNAVAILABLE,
    LocalBilingualReranker,
    LocalBilingualRerankerError,
)


BILINGUAL_RETRIEVAL_VERSION = "lexical-v1"
LOW_EVIDENCE_SCORE_THRESHOLD = 0.35
MAX_BILINGUAL_LIMIT = 20
CROSS_LANGUAGE_BACKEND_NAME = "local-multilingual-e5-small"
BILINGUAL_RERANKER_BACKEND_NAME = "local-bge-reranker-v2-m3"


class BilingualEvidenceWorkflowError(ValueError):
    """Raised for controlled bilingual evidence workflow failures."""


@dataclass(frozen=True)
class BilingualEvidenceResult:
    english_term: str
    chinese_term: str
    course: str
    chapter: str
    concept_scope: str
    filters: dict[str, Any]
    english_evidence_candidates: list[dict[str, Any]]
    chinese_evidence_candidates: list[dict[str, Any]]
    chinese_term_candidates: list[dict[str, Any]]
    bilingual_pair_candidates: list[dict[str, Any]]
    selected_chinese_candidate: dict[str, Any] | None
    risk_labels: list[str]
    draft_payload: dict[str, Any]
    evidence_qualification: dict[str, Any] | None = None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int = 5) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_labels(labels: Any) -> list[str]:
    return parse_quality_risk.normalize_labels(labels)


def _merge_labels(*label_groups: Any) -> list[str]:
    merged: list[str] = []
    for labels in label_groups:
        merged = parse_quality_risk.merge_risk_labels(merged, labels)
    return merged


def build_bilingual_evidence_query(input_data: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(input_data or {})
    english_term = _text(data.get("english_term") or data.get("query") or data.get("q"))
    if not english_term:
        raise BilingualEvidenceWorkflowError("english_term is required.")
    limit = max(1, min(_as_int(data.get("limit"), 5), MAX_BILINGUAL_LIMIT))
    filters = dict(data.get("filters") or {})
    for key in ("include_needs_review", "include_low_quality", "visibility", "trust_level", "quality_status", "source_uid", "source_uids"):
        if key in data and key not in filters:
            filters[key] = data[key]
    candidate_limit = max(1, min(_as_int(data.get("candidate_limit"), 10), chinese_term_candidates.MAX_CANDIDATE_LIMIT))
    return {
        "english_term": english_term,
        "chinese_term": _text(data.get("chinese_term")),
        "course": _text(data.get("course")),
        "chapter": _text(data.get("chapter")),
        "concept_scope": _text(data.get("concept_scope")),
        "english_candidate_uid": _text(data.get("english_candidate_uid")),
        "normalized_english_term": _text(data.get("normalized_english_term")) or english_term.casefold(),
        "english_context": _text(data.get("english_context"))[:cross_language_retrieval.MAX_CONTEXT_CHARS],
        "discipline": _text(data.get("discipline")),
        "limit": limit,
        "auto_generate_chinese_candidates": _as_bool(data.get("auto_generate_chinese_candidates")),
        "candidate_limit": candidate_limit,
        "selected_chinese_candidate_uid": _text(data.get("selected_chinese_candidate_uid")),
        "filters": {
            **filters,
            "include_needs_review": _as_bool(filters.get("include_needs_review")),
            "include_low_quality": _as_bool(filters.get("include_low_quality")),
        },
    }


def _candidate_key(candidate: dict[str, Any]) -> str:
    return _text(candidate.get("chunk_uid")) or _text(candidate.get("evidence_uid"))


def _merge_candidates(groups: list[list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    seen = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for candidate in group:
            key = _candidate_key(candidate)
            if not key or key in seen:
                continue
            merged.append(candidate)
            seen.add(key)
            if len(merged) >= limit:
                return merged
    return merged


def _base_filters(course: str | None, chapter: str | None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(filters or {})
    if course:
        base["course"] = course
    if chapter:
        base["chapter"] = chapter
    return base


def _search_with_attempts(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    term: str,
    attempts: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    groups = []
    for filters in attempts:
        result = evidence_retrieval.search_evidence(
            session,
            chunk_model,
            source_model,
            term,
            filters=filters,
            limit=limit,
        )
        groups.append(result.candidates)
    return _merge_candidates(groups, limit)


def retrieve_english_evidence(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    english_term: str,
    course: str | None = None,
    chapter: str | None = None,
    limit: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    term = _text(english_term)
    if not term:
        raise BilingualEvidenceWorkflowError("english_term is required.")
    base = _base_filters(course, chapter, filters)
    attempts = [
        {**base, "language": "en", "source_role": "english_course_material", "source_type": "course_material"},
        {**base, "language": "en", "source_role": "english_course_material", "source_type": "textbook"},
        {**base, "language": "en", "source_role": "english_course_material", "source_type": "reference"},
        {**base, "language": "en", "source_role": "english_course_material"},
        {**base, "language": "mixed", "source_role": "bilingual_reference"},
        {**base, "language": "en"},
    ]
    return _search_with_attempts(session, chunk_model, source_model, term, attempts, limit)


def retrieve_chinese_evidence(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    chinese_term: str,
    course: str | None = None,
    chapter: str | None = None,
    limit: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    term = _text(chinese_term)
    if not term:
        return []
    base = _base_filters(course, chapter, filters)
    attempts = [
        {**base, "language": "zh", "source_role": "chinese_reference_material", "source_type": "textbook"},
        {**base, "language": "zh", "source_role": "chinese_reference_material", "source_type": "reference"},
        {**base, "language": "zh", "source_role": "chinese_reference_material", "source_type": "teacher_upload"},
        {**base, "language": "zh", "source_role": "chinese_reference_material"},
        {**base, "language": "mixed", "source_role": "bilingual_reference"},
        {**base, "language": "zh"},
    ]
    return _search_with_attempts(session, chunk_model, source_model, term, attempts, limit)


def retrieve_cross_language_chinese_evidence(
    session: Any, chunk_model: Any, source_model: Any, input_data: dict[str, Any],
    *, embedding_backend: Any | None = None,
) -> list[dict[str, Any]]:
    configured = os.environ.get("LEXIBRIDGE_CROSS_LANGUAGE_RETRIEVAL_BACKEND", "").strip()
    if configured != CROSS_LANGUAGE_BACKEND_NAME and embedding_backend is None:
        return []
    if embedding_backend is None:
        cache_dir = os.environ.get("LEXIBRIDGE_MODEL_CACHE_DIR", "").strip()
        if not cache_dir:
            raise cross_language_retrieval.CrossLanguageRetrievalError(
                "LOCAL_MULTILINGUAL_EMBEDDING_BACKEND_UNAVAILABLE"
            )
        embedding_backend = LocalMultilingualEmbeddingBackend(model_cache_dir=cache_dir)
    chunk_query = session.query(chunk_model)
    if hasattr(chunk_model, "language"):
        chunk_query = chunk_query.filter(chunk_model.language == "zh")
    if hasattr(chunk_model, "status"):
        chunk_query = chunk_query.filter(chunk_model.status == "active")
    if input_data.get("course") and hasattr(chunk_model, "course"):
        chunk_query = chunk_query.filter(chunk_model.course == input_data["course"])
    if input_data.get("chapter") and hasattr(chunk_model, "chapter"):
        chunk_query = chunk_query.filter(chunk_model.chapter == input_data["chapter"])
    governed_source_uid = _text(input_data.get("filters", {}).get("source_uid"))
    if governed_source_uid and hasattr(chunk_model, "source_uid"):
        chunk_query = chunk_query.filter(chunk_model.source_uid == governed_source_uid)
    raw_governed_source_uids = input_data.get("filters", {}).get("source_uids", [])
    if isinstance(raw_governed_source_uids, str):
        raw_governed_source_uids = [raw_governed_source_uids]
    governed_source_uids = tuple(
        sorted({
            _text(value)
            for value in raw_governed_source_uids
            if _text(value)
        })
    )
    if governed_source_uids and hasattr(chunk_model, "source_uid"):
        chunk_query = chunk_query.filter(chunk_model.source_uid.in_(governed_source_uids))
    chunks = chunk_query.order_by(chunk_model.id.asc()).limit(
        cross_language_retrieval.MAX_PASSAGE_CANDIDATES
    ).all()
    source_map = evidence_retrieval._sources_for_chunks(session, source_model, chunks)
    passages = []
    allowed = []
    evidence_filters = {
        "language": "zh",
        "include_needs_review": _as_bool(
            input_data.get("filters", {}).get("include_needs_review")
        ),
        "include_low_quality": _as_bool(
            input_data.get("filters", {}).get("include_low_quality")
        ),
    }
    for chunk in chunks:
        source = evidence_retrieval._source_for_chunk(chunk, source_map)
        if not evidence_retrieval.should_include_chunk_as_evidence(
            chunk, evidence_filters, source=source
        ):
            continue
        source_uid = evidence_retrieval._source_uid(chunk, source)
        allowed.append(source_uid)
        content = evidence_retrieval._chunk_text(chunk)
        passages.append(cross_language_retrieval.SemanticPassage(
            source_uid=source_uid,
            chunk_uid=evidence_retrieval._text(evidence_retrieval._field(chunk, "chunk_uid", "")),
            content=content, language="zh",
            source_status=evidence_retrieval._text(evidence_retrieval._field(source, "status", "active")),
            quality_status=evidence_retrieval._combined_field(chunk, source, "quality_status", ""),
            content_hash=evidence_retrieval._text(
                evidence_retrieval._field(chunk, "content_hash", "")
            ) or __import__("hashlib").sha256(content.encode()).hexdigest(),
            page_number=evidence_retrieval._field(chunk, "page_number", None),
            block_uid=evidence_retrieval._text(
                evidence_retrieval._field(chunk, "parse_block_uid", "")
            ),
            heading_path=evidence_retrieval._text(
                evidence_retrieval._field(chunk, "source_section", "")
                or evidence_retrieval._field(chunk, "chapter", "")
            ),
        ))
    request = cross_language_retrieval.CrossLanguageRetrievalQuery(
        english_candidate_uid=input_data["english_candidate_uid"],
        canonical_english_term=input_data["english_term"],
        normalized_english_term=input_data["normalized_english_term"],
        english_context=input_data["english_context"],
        discipline=input_data["discipline"],
        allowed_chinese_source_uids=tuple(sorted(set(allowed))),
        top_k=input_data["limit"],
        retrieval_budget=cross_language_retrieval.MAX_PASSAGE_CANDIDATES,
    )
    return [
        {
            "evidence_uid": result.query_hash[:12] + result.chunk_uid[:12],
            "chunk_uid": result.chunk_uid, "source_uid": result.source_uid,
            "language": result.language, "status": result.source_status,
            "quality_status": result.quality_status, "snippet": result.snippet,
            "score": result.score, "rank": result.rank,
            "page_number": result.provenance.get("page_number"),
            "block_uid": result.provenance.get("block_uid", ""),
            "heading_path": result.provenance.get("heading_path", ""),
            "retrieval_reason": result.retrieval_method,
            "retrieval_method": result.retrieval_method,
            "backend_id": result.backend_id, "model_id": result.model_id,
            "model_revision": result.model_revision, "query_hash": result.query_hash,
            "provenance": result.provenance, "risk_labels": [],
        }
        for result in cross_language_retrieval.rank_chinese_passages(
            request, passages, embedding_backend
        )
    ]


def _candidate_has_review_risk(candidate: dict[str, Any]) -> bool:
    status = _text(candidate.get("status"))
    quality_status = _text(candidate.get("quality_status"))
    flags = set(_normalize_labels(candidate.get("quality_flags", [])))
    risk_labels = set(_normalize_labels(candidate.get("risk_labels", [])))
    return (
        status == "needs_review"
        or quality_status in evidence_retrieval.REVIEW_QUALITY_STATUSES
        or bool(flags & evidence_retrieval.REVIEW_QUALITY_STATUSES)
        or "needs_review_evidence" in risk_labels
    )


def _candidate_has_partial_text(candidate: dict[str, Any]) -> bool:
    quality_status = _text(candidate.get("quality_status"))
    flags = set(_normalize_labels(candidate.get("quality_flags", [])))
    risk_labels = set(_normalize_labels(candidate.get("risk_labels", [])))
    return quality_status == "partial_text" or "partial_text" in flags or "input_partial_text" in risk_labels


def _candidate_low_trust(candidate: dict[str, Any]) -> bool:
    trust_level = _text(candidate.get("trust_level"))
    return trust_level in {"low_quality", "unknown", "student_uploaded"}


def _mismatches(candidate: dict[str, Any], field: str, expected: str) -> bool:
    expected = _text(expected)
    actual = _text(candidate.get(field))
    return bool(expected and actual and actual != expected)


def classify_bilingual_evidence_risks(
    english_candidates: list[dict[str, Any]],
    chinese_candidates: list[dict[str, Any]],
    input_data: dict[str, Any] | None = None,
) -> list[str]:
    data = dict(input_data or {})
    risks = ["bilingual_alignment_not_verified"]
    chinese_term = _text(data.get("chinese_term"))
    course = _text(data.get("course"))
    chapter = _text(data.get("chapter"))

    if not english_candidates:
        risks.append("no_english_evidence")
    if not chinese_term:
        risks.append("missing_chinese_term")
    elif not chinese_candidates:
        risks.append("no_chinese_evidence")
    if not english_candidates or not chinese_candidates:
        risks.append("cross_language_evidence_missing")

    if english_candidates and float(english_candidates[0].get("score") or 0) < LOW_EVIDENCE_SCORE_THRESHOLD:
        risks.append("low_english_evidence_score")
    if chinese_candidates and float(chinese_candidates[0].get("score") or 0) < LOW_EVIDENCE_SCORE_THRESHOLD:
        risks.append("low_chinese_evidence_score")

    all_candidates = [*english_candidates, *chinese_candidates]
    if any(_mismatches(candidate, "course", course) for candidate in all_candidates):
        risks.append("course_mismatch")
    if any(_mismatches(candidate, "chapter", chapter) for candidate in all_candidates):
        risks.append("chapter_mismatch")
    if any(_candidate_has_review_risk(candidate) for candidate in all_candidates):
        risks.append("evidence_from_needs_review_source")
    if any(_candidate_has_partial_text(candidate) for candidate in all_candidates):
        risks.append("evidence_from_partial_text")
    if any(_candidate_low_trust(candidate) for candidate in all_candidates):
        risks.append("evidence_from_low_trust_source")
    return _merge_labels(risks)


def _status_from_risks(risk_labels: list[str]) -> str:
    return "needs_review" if risk_labels else "draft"


def build_concept_card_draft_payload_from_evidence(
    input_data: dict[str, Any],
    english_candidates: list[dict[str, Any]],
    chinese_candidates: list[dict[str, Any]],
    chinese_candidates_for_term: list[dict[str, Any]] | None = None,
    selected_chinese_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query = build_bilingual_evidence_query(input_data)
    risks = classify_bilingual_evidence_risks(english_candidates, chinese_candidates, query)
    if chinese_candidates_for_term:
        risks = _merge_labels(risks, ["candidate_not_alignment_verified"])
    if input_data.get("candidate_risk_labels"):
        risks = _merge_labels(risks, input_data.get("candidate_risk_labels"))
    chinese_evidence = [evidence_retrieval.serialize_evidence_candidate(candidate) for candidate in chinese_candidates]
    if selected_chinese_candidate:
        selected_summary = chinese_term_candidates.serialize_chinese_term_candidate(selected_chinese_candidate)
        selected_marker = {
            "evidence_type": "selected_chinese_candidate",
            "selected_chinese_candidate": selected_summary,
            "chunk_uid": selected_summary.get("chunk_uid", ""),
            "source_uid": selected_summary.get("source_uid", ""),
            "source_title": "",
            "course": selected_summary.get("course", ""),
            "chapter": selected_summary.get("chapter", ""),
            "language": "zh",
            "source_role": "",
            "trust_level": selected_summary.get("trust_level", ""),
            "quality_status": selected_summary.get("quality_status", ""),
            "quality_flags": selected_summary.get("quality_flags", []),
            "source_locator": selected_summary.get("source_locator", ""),
            "snippet": selected_summary.get("evidence_snippet", ""),
            "score": selected_summary.get("score", 0.0),
            "retrieval_reason": "selected Chinese term candidate for draft evidence retrieval",
            "risk_labels": selected_summary.get("risk_labels", []),
            "parse_uid": selected_summary.get("parse_uid", ""),
            "parse_block_uid": selected_summary.get("parse_block_uid", ""),
        }
        chinese_evidence = [selected_marker, *chinese_evidence]
    return {
        "english_term": query["english_term"],
        "chinese_term": query["chinese_term"],
        "course": query["course"],
        "chapter": query["chapter"],
        "concept_scope": query["concept_scope"],
        "english_evidence": [evidence_retrieval.serialize_evidence_candidate(candidate) for candidate in english_candidates],
        "chinese_evidence": chinese_evidence,
        "chinese_term_candidates": [
            chinese_term_candidates.serialize_chinese_term_candidate(candidate)
            for candidate in (chinese_candidates_for_term or [])
        ],
        "selected_chinese_candidate": (
            chinese_term_candidates.serialize_chinese_term_candidate(selected_chinese_candidate)
            if selected_chinese_candidate else None
        ),
        "risk_labels": risks,
        "status": _status_from_risks(risks),
        "confidence_score": None,
        "alignment_reason": "",
        "model_name": None,
        "prompt_version": None,
        "retrieval_version": BILINGUAL_RETRIEVAL_VERSION,
    }


def retrieve_bilingual_evidence(
    session: Any,
    chunk_model: Any,
    source_model: Any,
    english_term: str,
    chinese_term: str | None = None,
    course: str | None = None,
    chapter: str | None = None,
    limit: int = 5,
    filters: dict[str, Any] | None = None,
    concept_scope: str = "",
    auto_generate_chinese_candidates: bool = False,
    candidate_limit: int = 10,
    selected_chinese_candidate_uid: str | None = None,
    concept_card_model: Any | None = None,
    term_model: Any | None = None,
    terminology_card_model: Any | None = None,
    audit_context: dict[str, Any] | None = None,
    english_candidate_uid: str = "",
    normalized_english_term: str = "",
    english_context: str = "",
    discipline: str = "",
    cross_language_embedding_backend: Any | None = None,
    bilingual_pairing_backend: Any | None = None,
    bilingual_reranker_backend: Any | None = None,
) -> BilingualEvidenceResult:
    del audit_context
    input_data = build_bilingual_evidence_query({
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": course,
        "chapter": chapter,
        "concept_scope": concept_scope,
        "limit": limit,
        "filters": filters or {},
        "auto_generate_chinese_candidates": auto_generate_chinese_candidates,
        "candidate_limit": candidate_limit,
        "selected_chinese_candidate_uid": selected_chinese_candidate_uid,
        "english_candidate_uid": english_candidate_uid,
        "normalized_english_term": normalized_english_term,
        "english_context": english_context,
        "discipline": discipline,
    })
    english_filters = dict(input_data["filters"])
    english_filters.pop("source_uids", None)
    english_source_uid = _text(english_filters.pop("english_source_uid", ""))
    english_include_needs_review = _as_bool(
        english_filters.pop("english_include_needs_review", False)
    )
    if english_source_uid:
        english_filters["source_uid"] = english_source_uid
    if english_include_needs_review:
        english_filters["include_needs_review"] = True
    english_candidates = retrieve_english_evidence(
        session,
        chunk_model,
        source_model,
        input_data["english_term"],
        course=input_data["course"],
        chapter=input_data["chapter"],
        limit=input_data["limit"],
        filters=english_filters,
    )
    generated_candidates: list[dict[str, Any]] = []
    selected_candidate = None
    candidate_risk_labels: list[str] = []
    effective_chinese_term = input_data["chinese_term"]
    if not effective_chinese_term and input_data["auto_generate_chinese_candidates"]:
        candidate_result = chinese_term_candidates.generate_chinese_term_candidates(
            session,
            concept_card_model=concept_card_model,
            term_model=term_model,
            terminology_card_model=terminology_card_model,
            chunk_model=chunk_model,
            source_model=source_model,
            english_term=input_data["english_term"],
            course=input_data["course"],
            chapter=input_data["chapter"],
            limit=input_data["candidate_limit"],
            filters=input_data["filters"],
        )
        generated_candidates = [
            chinese_term_candidates.serialize_chinese_term_candidate(candidate)
            for candidate in candidate_result.candidates
        ]
        candidate_risk_labels = candidate_result.risk_labels
        requested_uid = input_data["selected_chinese_candidate_uid"]
        if generated_candidates:
            selected_candidate = next(
                (candidate for candidate in generated_candidates if requested_uid and candidate.get("candidate_uid") == requested_uid),
                generated_candidates[0],
            )
            effective_chinese_term = _text(selected_candidate.get("chinese_term"))
            input_data["chinese_term"] = effective_chinese_term

    if effective_chinese_term:
        chinese_candidates = retrieve_chinese_evidence(
            session, chunk_model, source_model, effective_chinese_term,
            course=input_data["course"], chapter=input_data["chapter"],
            limit=input_data["limit"], filters=input_data["filters"],
        )
    else:
        chinese_candidates = retrieve_cross_language_chinese_evidence(
            session, chunk_model, source_model, input_data,
            embedding_backend=cross_language_embedding_backend,
        )
        if chinese_candidates and not generated_candidates:
            identified = chinese_term_candidates.identify_standard_chinese_terms(
                input_data["english_term"],
                chinese_candidates,
                discipline=input_data["discipline"],
                limit=input_data["candidate_limit"],
            )
            generated_candidates = [
                chinese_term_candidates.serialize_chinese_term_candidate(candidate)
                for candidate in identified.candidates
            ]
            candidate_risk_labels = _merge_labels(
                candidate_risk_labels, identified.risk_labels
            )
            if generated_candidates:
                candidate_risk_labels = [
                    label
                    for label in candidate_risk_labels
                    if label != "no_chinese_candidate_found"
                ]
    pair_candidates: list[dict[str, Any]] = []
    qualification_result = None
    if generated_candidates and input_data["english_context"]:
        pairing_backend = (
            bilingual_pairing_backend
            or cross_language_embedding_backend
        )
        configured = os.environ.get(
            "LEXIBRIDGE_CROSS_LANGUAGE_RETRIEVAL_BACKEND", ""
        ).strip()
        if pairing_backend is None and configured == CROSS_LANGUAGE_BACKEND_NAME:
            cache_dir = os.environ.get("LEXIBRIDGE_MODEL_CACHE_DIR", "").strip()
            if not cache_dir:
                raise bilingual_semantic_pairing.BilingualPairingError(
                    "LOCAL_MULTILINGUAL_EMBEDDING_BACKEND_UNAVAILABLE"
                )
            pairing_backend = LocalMultilingualEmbeddingBackend(
                model_cache_dir=cache_dir
            )
        if pairing_backend is not None:
            reranker_backend = bilingual_reranker_backend
            reranker_configured = os.environ.get(
                "LEXIBRIDGE_BILINGUAL_RERANKER_BACKEND", ""
            ).strip()
            if (
                reranker_backend is None
                and reranker_configured == BILINGUAL_RERANKER_BACKEND_NAME
            ):
                cache_dir = os.environ.get(
                    "LEXIBRIDGE_MODEL_CACHE_DIR", ""
                ).strip()
                if not cache_dir:
                    raise LocalBilingualRerankerError(
                        BILINGUAL_RERANKER_BACKEND_UNAVAILABLE
                    )
                reranker_backend = LocalBilingualReranker(
                    model_cache_dir=cache_dir
                )
            english_provenance = {}
            if english_candidates:
                english_provenance = {
                    "source_uid": _text(english_candidates[0].get("source_uid")),
                    "chunk_uid": _text(english_candidates[0].get("chunk_uid")),
                }
            pair_candidates = [
                bilingual_semantic_pairing.serialize_bilingual_pair_result(pair)
                for pair in bilingual_semantic_pairing.rank_bilingual_pairs(
                    bilingual_semantic_pairing.EnglishPairingInput(
                        english_candidate_uid=input_data["english_candidate_uid"],
                        canonical_english_term=input_data["english_term"],
                        normalized_english_term=input_data["normalized_english_term"],
                        english_context=input_data["english_context"],
                        discipline=input_data["discipline"],
                        provenance=english_provenance,
                    ),
                    generated_candidates,
                    pairing_backend,
                    reranker_backend=reranker_backend,
                )
            ]
            qualification_result = bilingual_evidence_qualification.qualify_workflow_top1(
                input_data,
                english_candidates,
                chinese_candidates,
                generated_candidates,
                pair_candidates,
                consistency_backend=reranker_backend,
            )
    risk_labels = _merge_labels(
        classify_bilingual_evidence_risks(english_candidates, chinese_candidates, input_data),
        candidate_risk_labels,
    )
    draft_payload = build_concept_card_draft_payload_from_evidence(
        {**input_data, "candidate_risk_labels": candidate_risk_labels},
        english_candidates,
        chinese_candidates,
        generated_candidates,
        selected_candidate,
    )
    draft_payload["risk_labels"] = risk_labels
    draft_payload["evidence_qualification"] = (
        bilingual_evidence_qualification.serialize_qualification_result(
            qualification_result
        )
    )
    return BilingualEvidenceResult(
        english_term=input_data["english_term"],
        chinese_term=effective_chinese_term,
        course=input_data["course"],
        chapter=input_data["chapter"],
        concept_scope=input_data["concept_scope"],
        filters={**input_data["filters"], "limit": input_data["limit"]},
        english_evidence_candidates=english_candidates,
        chinese_evidence_candidates=chinese_candidates,
        chinese_term_candidates=generated_candidates,
        bilingual_pair_candidates=pair_candidates,
        selected_chinese_candidate=selected_candidate,
        risk_labels=risk_labels,
        draft_payload=draft_payload,
        evidence_qualification=(
            bilingual_evidence_qualification.serialize_qualification_result(
                qualification_result
            )
        ),
    )


def serialize_bilingual_evidence_result(result: BilingualEvidenceResult) -> dict[str, Any]:
    return {
        "english_term": result.english_term,
        "chinese_term": result.chinese_term,
        "course": result.course,
        "chapter": result.chapter,
        "concept_scope": result.concept_scope,
        "filters": dict(result.filters),
        "english_evidence_candidates": [
            evidence_retrieval.serialize_evidence_candidate(candidate)
            for candidate in result.english_evidence_candidates
        ],
        "chinese_evidence_candidates": [
            evidence_retrieval.serialize_evidence_candidate(candidate)
            for candidate in result.chinese_evidence_candidates
        ],
        "chinese_term_candidates": [
            chinese_term_candidates.serialize_chinese_term_candidate(candidate)
            for candidate in result.chinese_term_candidates
        ],
        "bilingual_pair_candidates": [
            dict(candidate) for candidate in result.bilingual_pair_candidates
        ],
        "selected_chinese_candidate": (
            chinese_term_candidates.serialize_chinese_term_candidate(result.selected_chinese_candidate)
            if result.selected_chinese_candidate else None
        ),
        "risk_labels": list(result.risk_labels),
        "draft_payload": dict(result.draft_payload),
        "evidence_qualification": (
            dict(result.evidence_qualification)
            if result.evidence_qualification is not None
            else None
        ),
    }
