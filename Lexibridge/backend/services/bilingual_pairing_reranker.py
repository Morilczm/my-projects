"""Bounded deterministic second-stage ranking for existing bilingual pairs."""
from __future__ import annotations

from typing import Any

from services.local_bilingual_reranker import (
    BILINGUAL_RERANKER_BACKEND_UNAVAILABLE,
    BILINGUAL_RERANKER_INPUT_INVALID,
    BILINGUAL_RERANKER_REVISION_MISMATCH,
    MODEL_ID,
    MODEL_REVISION,
    LocalBilingualRerankerError,
)


CROSS_ENCODER_WEIGHT = 1.0
BI_ENCODER_WEIGHT = 0.05
EXTRACTION_WEIGHT = 0.01
RETRIEVAL_WEIGHT = 0.005
STRUCTURE_WEIGHT = 0.005


def _text(value: Any) -> str:
    return str(value or "").strip()


def rerank_pair_scores(
    scored_items: list[dict[str, Any]],
    backend: Any,
) -> list[dict[str, Any]]:
    if not scored_items:
        raise LocalBilingualRerankerError(BILINGUAL_RERANKER_INPUT_INVALID)
    readiness = backend.readiness()
    if not readiness.ready:
        raise LocalBilingualRerankerError(BILINGUAL_RERANKER_BACKEND_UNAVAILABLE)
    if (
        _text(getattr(backend, "model_id", "")) != MODEL_ID
        or _text(getattr(backend, "model_revision", "")) != MODEL_REVISION
    ):
        raise LocalBilingualRerankerError(BILINGUAL_RERANKER_REVISION_MISMATCH)
    scores = backend.score_pairs([
        (item["english_text"], item["chinese_text"])
        for item in scored_items
    ])
    if len(scores) != len(scored_items):
        raise LocalBilingualRerankerError(BILINGUAL_RERANKER_INPUT_INVALID)
    reranked = []
    for item, cross_encoder_score in zip(scored_items, scores):
        value = dict(item)
        value["cross_encoder_score"] = round(float(cross_encoder_score), 8)
        value["final"] = round(
            CROSS_ENCODER_WEIGHT * value["cross_encoder_score"]
            + BI_ENCODER_WEIGHT * value["semantic"]
            + EXTRACTION_WEIGHT * value["extraction"]
            + RETRIEVAL_WEIGHT * value["retrieval"]
            + STRUCTURE_WEIGHT * value["structure"],
            8,
        )
        reranked.append(value)
    reranked.sort(key=lambda item: (
        -item["final"],
        -item["cross_encoder_score"],
        max(1, int(item["candidate"].get("rank") or 999)),
        max(1, int(item["candidate"].get("retrieval_rank") or 999)),
        _text(item["candidate"].get("source_uid")),
        _text(item["candidate"].get("chunk_uid")),
        _text(
            item["candidate"].get("normalized_text")
            or item["candidate"].get("chinese_term")
        ),
    ))
    return reranked
