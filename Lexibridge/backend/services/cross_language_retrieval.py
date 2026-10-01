"""Bounded English-to-Chinese semantic retrieval using the qualified backend."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from services.local_multilingual_embedding import (
    BACKEND_UNAVAILABLE,
    MODEL_ID,
    MODEL_REVISION,
    cache_key,
)

MAX_CONTEXT_CHARS = 800
MAX_QUERY_CHARS = 1100
MAX_TOP_K = 10
MAX_PASSAGE_CANDIDATES = 200
MAX_PASSAGE_REPRESENTATION_CHARS = 240

_LOCATION_LINE = re.compile(
    r"^(?:\[?\s*(?:page|slide)\s*[:#]?\s*\d+\s*\]?|第\s*\d+\s*页)$",
    re.IGNORECASE,
)
_DEFINITION_MARKERS = frozenset({
    "定义", "概念定义", "术语定义", "definition", "concept definition",
})
_SECTION_BREAK_MARKERS = frozenset({
    "关键性质", "主要性质", "性质", "概念边界", "边界", "示例", "例子",
    "key properties", "properties", "concept boundary", "examples", "summary",
})


class CrossLanguageRetrievalError(RuntimeError):
    pass


@dataclass(frozen=True)
class CrossLanguageRetrievalQuery:
    english_candidate_uid: str
    canonical_english_term: str
    normalized_english_term: str
    english_context: str
    discipline: str
    allowed_chinese_source_uids: tuple[str, ...]
    top_k: int = 5
    retrieval_budget: int = 100


@dataclass(frozen=True)
class SemanticPassage:
    source_uid: str
    chunk_uid: str
    content: str
    language: str
    source_status: str
    quality_status: str
    content_hash: str
    page_number: int | None = None
    block_uid: str = ""
    heading_path: str = ""


@dataclass(frozen=True)
class CrossLanguageRetrievalResult:
    source_uid: str
    chunk_uid: str
    score: float
    rank: int
    retrieval_method: str
    backend_id: str
    model_id: str
    model_revision: str
    query_hash: str
    language: str
    source_status: str
    quality_status: str
    snippet: str
    provenance: dict[str, Any]


def build_query_text(query: CrossLanguageRetrievalQuery) -> str:
    context = str(query.english_context or "").strip()[:MAX_CONTEXT_CHARS]
    text = (
        f"term:\n{query.canonical_english_term.strip()}\n\n"
        f"discipline:\n{query.discipline.strip()}\n\ncontext:\n{context}"
    )
    return text[:MAX_QUERY_CHARS]


def _normalized_line(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _content_lines(value: str) -> list[str]:
    return [" ".join(line.split()) for line in str(value or "").splitlines() if line.strip()]


def _repeated_boilerplate(passages: Iterable[SemanticPassage]) -> frozenset[str]:
    counts: Counter[str] = Counter()
    for passage in passages:
        lines = _content_lines(passage.content)
        edge_lines = lines[:2] + lines[-2:]
        counts.update(set(_normalized_line(line) for line in edge_lines))
    return frozenset(
        line for line, count in counts.items()
        if count > 1 and len(line) >= 16
    )


def build_passage_representation(
    content: str, *, repeated_lines: Iterable[str] = ()
) -> str:
    """Build a deterministic concept-local embedding representation.

    Retrieval snippets keep the bounded original text.  Only the embedding
    representation removes repeated headers/footers and, when an explicit
    definition section is present, stops before later properties or boundary
    sections.  This prevents several neighboring concepts on a course page
    from overwhelming the selected concept without using bilingual mappings.
    """
    repeated = {_normalized_line(line) for line in repeated_lines}
    lines = []
    for line in _content_lines(content):
        normalized = _normalized_line(line)
        if _LOCATION_LINE.fullmatch(line.strip()):
            continue
        if normalized in repeated and normalized not in _DEFINITION_MARKERS:
            continue
        lines.append(line)
    if not lines:
        return ""

    normalized_lines = [_normalized_line(line) for line in lines]
    definition_index = next(
        (index for index, line in enumerate(normalized_lines) if line in _DEFINITION_MARKERS),
        None,
    )
    start = max(0, definition_index - 1) if definition_index is not None else 0
    end = len(lines)
    if definition_index is not None:
        end = next(
            (
                index for index in range(definition_index + 1, len(lines))
                if normalized_lines[index] in _SECTION_BREAK_MARKERS
            ),
            len(lines),
        )
    return "\n".join(lines[start:end]).strip()[:MAX_PASSAGE_REPRESENTATION_CHARS]


def _vector(
    backend: Any, text: str, representation_type: str, cache: dict[str, list[float]]
) -> list[float]:
    key = f"{representation_type}:{cache_key(MODEL_ID, MODEL_REVISION, text)}"
    if key not in cache:
        encoded = (
            backend.embed_queries([text])
            if representation_type == "query"
            else backend.embed_passages([text])
        )
        if not encoded or not encoded[0]:
            raise CrossLanguageRetrievalError(BACKEND_UNAVAILABLE)
        cache[key] = list(encoded[0])
    return cache[key]


def rank_chinese_passages(
    query: CrossLanguageRetrievalQuery,
    passages: Iterable[SemanticPassage],
    backend: Any,
    *,
    representation_cache: dict[str, list[float]] | None = None,
) -> list[CrossLanguageRetrievalResult]:
    readiness = backend.readiness()
    if not readiness.ready:
        raise CrossLanguageRetrievalError(BACKEND_UNAVAILABLE)
    allowed = set(query.allowed_chinese_source_uids)
    bounded = [
        p for p in passages
        if p.language == "zh"
        and p.source_status == "active"
        and p.quality_status not in {"blocked", "rejected", "withdrawn", "ocr_required"}
        and (not allowed or p.source_uid in allowed)
        and p.content.strip()
    ]
    budget = max(1, min(int(query.retrieval_budget or 1), MAX_PASSAGE_CANDIDATES))
    bounded = sorted(bounded, key=lambda p: (p.source_uid, p.chunk_uid))[:budget]
    if not bounded:
        return []
    cache = representation_cache if representation_cache is not None else {}
    query_text = build_query_text(query)
    query_vector = _vector(backend, query_text, "query", cache)
    repeated_lines = _repeated_boilerplate(bounded)
    scored = []
    for passage in bounded:
        representation = build_passage_representation(
            passage.content, repeated_lines=repeated_lines
        ) or passage.content[:MAX_PASSAGE_REPRESENTATION_CHARS]
        vector = _vector(backend, representation, "passage", cache)
        score = round(sum(a * b for a, b in zip(query_vector, vector)), 8)
        scored.append((score, passage))
    scored.sort(key=lambda item: (-item[0], item[1].source_uid, item[1].chunk_uid))
    top_k = max(1, min(int(query.top_k or 1), MAX_TOP_K))
    query_hash = hashlib.sha256(query_text.encode()).hexdigest()
    results = []
    for rank, (score, passage) in enumerate(scored[:top_k], 1):
        results.append(CrossLanguageRetrievalResult(
            source_uid=passage.source_uid, chunk_uid=passage.chunk_uid,
            score=score, rank=rank, retrieval_method="multilingual_e5_cosine",
            backend_id=backend.backend_id, model_id=backend.model_id,
            model_revision=backend.model_revision, query_hash=query_hash,
            language=passage.language, source_status=passage.source_status,
            quality_status=passage.quality_status,
            snippet=passage.content[:180],
            provenance={
                "source_uid": passage.source_uid,
                "chunk_uid": passage.chunk_uid,
                "content_hash": passage.content_hash,
                "page_number": passage.page_number,
                "block_uid": passage.block_uid,
                "heading_path": passage.heading_path,
            },
        ))
    return results
