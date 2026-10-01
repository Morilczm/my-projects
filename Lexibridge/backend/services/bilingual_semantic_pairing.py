"""Bounded offline semantic ranking of English/Chinese candidate pairs."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from services import bilingual_pairing_reranker
from services.local_multilingual_embedding import (
    BACKEND_UNAVAILABLE,
    MODEL_ID,
    MODEL_REVISION,
)


MAX_PAIR_CONTEXT_CHARS = 800
MAX_PAIR_CANDIDATES = 20
BILINGUAL_PAIRING_CANDIDATE_POOL_EMPTY = "BILINGUAL_PAIRING_CANDIDATE_POOL_EMPTY"
BILINGUAL_PAIRING_REPRESENTATION_INVALID = "BILINGUAL_PAIRING_REPRESENTATION_INVALID"
BILINGUAL_PAIRING_EXECUTION_FAILED = "BILINGUAL_PAIRING_EXECUTION_FAILED"

SEMANTIC_WEIGHT = 0.85
EXTRACTION_WEIGHT = 0.08
RETRIEVAL_WEIGHT = 0.05
STRUCTURE_WEIGHT = 0.02


class BilingualPairingError(RuntimeError):
    """Controlled fail-closed semantic pairing failure."""


@dataclass(frozen=True)
class EnglishPairingInput:
    english_candidate_uid: str
    canonical_english_term: str
    normalized_english_term: str
    english_context: str
    discipline: str
    provenance: dict[str, str]


@dataclass(frozen=True)
class BilingualPairResult:
    english_candidate_uid: str
    chinese_candidate_uid: str
    chinese_candidate_text: str
    chinese_normalized_text: str
    final_score: float
    semantic_score: float
    cross_encoder_score: float | None
    score_components: dict[str, float]
    rank: int
    backend_id: str
    model_id: str
    model_revision: str
    english_representation_hash: str
    chinese_representation_hash: str
    source_uid: str
    chunk_uid: str
    retrieval_rank: int
    extraction_rank: int
    pairing_method: str
    reranker_backend_id: str
    reranker_model_id: str
    reranker_model_revision: str
    provenance: dict[str, str]
    reason_code: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bounded(value: Any) -> str:
    return _text(value)[:MAX_PAIR_CONTEXT_CHARS]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_english_pair_representation(value: EnglishPairingInput) -> str:
    return (
        f"term:\n{_text(value.canonical_english_term)}\n\n"
        f"discipline:\n{_text(value.discipline)}\n\n"
        f"context:\n{_bounded(value.english_context)}"
    )


def build_chinese_pair_representation(
    candidate: dict[str, Any],
    discipline: str,
) -> str:
    return (
        f"term:\n{_text(candidate.get('chinese_term'))}\n\n"
        f"discipline:\n{_text(discipline)}\n\n"
        f"context:\n{_bounded(candidate.get('evidence_snippet') or candidate.get('snippet'))}"
    )


def _structure_prior(method: str) -> float:
    return {
        "heading": 1.0,
        "so_called_subject": 0.95,
        "called_term": 0.9,
        "list_item": 0.85,
        "definition_subject": 0.8,
    }.get(_text(method), 0.5)


def _bounded_pool(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        list(candidates or []),
        key=lambda item: (
            max(1, int(item.get("rank") or 999)),
            _text(item.get("source_uid")),
            _text(item.get("chunk_uid")),
            _text(item.get("normalized_text") or item.get("chinese_term")),
        ),
    )
    return ordered[:MAX_PAIR_CANDIDATES]


def rank_bilingual_pairs(
    english: EnglishPairingInput,
    chinese_candidates: list[dict[str, Any]],
    backend: Any,
    *,
    reranker_backend: Any | None = None,
) -> list[BilingualPairResult]:
    pool = _bounded_pool(chinese_candidates)
    if not pool:
        raise BilingualPairingError(BILINGUAL_PAIRING_CANDIDATE_POOL_EMPTY)
    readiness = backend.readiness()
    if not readiness.ready:
        raise BilingualPairingError(BACKEND_UNAVAILABLE)
    if (
        _text(getattr(backend, "model_id", "")) != MODEL_ID
        or _text(getattr(backend, "model_revision", "")) != MODEL_REVISION
    ):
        raise BilingualPairingError(BILINGUAL_PAIRING_REPRESENTATION_INVALID)
    if not _bounded(english.english_context) or not dict(english.provenance or {}):
        raise BilingualPairingError(BILINGUAL_PAIRING_REPRESENTATION_INVALID)

    valid = []
    chinese_texts = []
    for candidate in pool:
        provenance = dict(candidate.get("provenance") or {})
        context = _bounded(candidate.get("evidence_snippet") or candidate.get("snippet"))
        if (
            not _text(candidate.get("candidate_uid"))
            or not _text(candidate.get("chinese_term"))
            or not context
            or not provenance
            or not _text(candidate.get("source_uid"))
            or not _text(candidate.get("chunk_uid"))
        ):
            continue
        valid.append(candidate)
        chinese_texts.append(build_chinese_pair_representation(candidate, english.discipline))
    if not valid:
        raise BilingualPairingError(BILINGUAL_PAIRING_REPRESENTATION_INVALID)

    english_text = build_english_pair_representation(english)
    try:
        query_rows = backend.embed_queries([english_text])
        passage_rows = backend.embed_passages(chinese_texts)
    except Exception as exc:
        if BACKEND_UNAVAILABLE in str(exc):
            raise BilingualPairingError(BACKEND_UNAVAILABLE) from exc
        raise BilingualPairingError(BILINGUAL_PAIRING_EXECUTION_FAILED) from exc
    if (
        len(query_rows) != 1
        or len(passage_rows) != len(valid)
        or not query_rows[0]
        or any(not row or len(row) != len(query_rows[0]) for row in passage_rows)
    ):
        raise BilingualPairingError(BILINGUAL_PAIRING_REPRESENTATION_INVALID)

    scored = []
    english_hash = _hash(english_text)
    for candidate, chinese_text, vector in zip(valid, chinese_texts, passage_rows):
        semantic = round(sum(
            float(left) * float(right)
            for left, right in zip(query_rows[0], vector)
        ), 8)
        extraction = max(0.0, min(float(candidate.get("score") or 0.0), 1.0))
        retrieval_rank = max(1, int(candidate.get("retrieval_rank") or 999))
        retrieval = round(1.0 / retrieval_rank, 8)
        structure = _structure_prior(candidate.get("extraction_method"))
        final = round(
            SEMANTIC_WEIGHT * semantic
            + EXTRACTION_WEIGHT * extraction
            + RETRIEVAL_WEIGHT * retrieval
            + STRUCTURE_WEIGHT * structure,
            8,
        )
        scored.append({
            "candidate": candidate,
            "english_text": english_text,
            "chinese_text": chinese_text,
            "semantic": semantic,
            "extraction": extraction,
            "retrieval": retrieval,
            "structure": structure,
            "final": final,
        })
    if reranker_backend is not None:
        scored = bilingual_pairing_reranker.rerank_pair_scores(
            scored,
            reranker_backend,
        )
    else:
        scored.sort(key=lambda item: (
            -item["final"],
            -item["semantic"],
            max(1, int(item["candidate"].get("rank") or 999)),
            max(1, int(item["candidate"].get("retrieval_rank") or 999)),
            _text(item["candidate"].get("source_uid")),
            _text(item["candidate"].get("chunk_uid")),
            _text(item["candidate"].get("normalized_text") or item["candidate"].get("chinese_term")),
        ))

    results = []
    for rank, item in enumerate(scored, 1):
        candidate = item["candidate"]
        results.append(BilingualPairResult(
            english_candidate_uid=_text(english.english_candidate_uid),
            chinese_candidate_uid=_text(candidate.get("candidate_uid")),
            chinese_candidate_text=_text(candidate.get("chinese_term")),
            chinese_normalized_text=_text(
                candidate.get("normalized_text") or candidate.get("chinese_term")
            ),
            final_score=item["final"],
            semantic_score=item["semantic"],
            cross_encoder_score=item.get("cross_encoder_score"),
            score_components={
                "semantic_score": item["semantic"],
                "bi_encoder_score": item["semantic"],
                "semantic_weight": (
                    bilingual_pairing_reranker.BI_ENCODER_WEIGHT
                    if reranker_backend is not None
                    else SEMANTIC_WEIGHT
                ),
                "bi_encoder_weight": (
                    bilingual_pairing_reranker.BI_ENCODER_WEIGHT
                    if reranker_backend is not None
                    else SEMANTIC_WEIGHT
                ),
                "cross_encoder_score": item.get("cross_encoder_score", 0.0),
                "cross_encoder_weight": (
                    bilingual_pairing_reranker.CROSS_ENCODER_WEIGHT
                    if reranker_backend is not None
                    else 0.0
                ),
                "extraction_prior": item["extraction"],
                "extraction_weight": (
                    bilingual_pairing_reranker.EXTRACTION_WEIGHT
                    if reranker_backend is not None
                    else EXTRACTION_WEIGHT
                ),
                "retrieval_prior": item["retrieval"],
                "retrieval_weight": (
                    bilingual_pairing_reranker.RETRIEVAL_WEIGHT
                    if reranker_backend is not None
                    else RETRIEVAL_WEIGHT
                ),
                "structural_prior": item["structure"],
                "structural_weight": (
                    bilingual_pairing_reranker.STRUCTURE_WEIGHT
                    if reranker_backend is not None
                    else STRUCTURE_WEIGHT
                ),
            },
            rank=rank,
            backend_id=_text(getattr(backend, "backend_id", "")),
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
            english_representation_hash=english_hash,
            chinese_representation_hash=_hash(item["chinese_text"]),
            source_uid=_text(candidate.get("source_uid")),
            chunk_uid=_text(candidate.get("chunk_uid")),
            retrieval_rank=max(1, int(candidate.get("retrieval_rank") or 999)),
            extraction_rank=max(1, int(candidate.get("rank") or 999)),
            pairing_method=(
                "bge_reranker_v2_m3_cross_encoder_v1"
                if reranker_backend is not None
                else "multilingual_e5_semantic_pairing_v1"
            ),
            reranker_backend_id=_text(
                getattr(reranker_backend, "backend_id", "")
            ),
            reranker_model_id=_text(
                getattr(reranker_backend, "model_id", "")
            ),
            reranker_model_revision=_text(
                getattr(reranker_backend, "model_revision", "")
            ),
            provenance=dict(candidate.get("provenance") or {}),
            reason_code=(
                "BILINGUAL_SEMANTIC_PAIR_RERANKED"
                if reranker_backend is not None
                else "BILINGUAL_SEMANTIC_PAIR_RANKED"
            ),
        ))
    return results


def serialize_bilingual_pair_result(result: BilingualPairResult) -> dict[str, Any]:
    return {
        field: getattr(result, field)
        for field in result.__dataclass_fields__
    }
