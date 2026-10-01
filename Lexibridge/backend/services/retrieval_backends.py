"""Pluggable retrieval backends while preserving metadata hard filters."""

from __future__ import annotations

import os

from services import retrieval as lexical_retrieval
from services.embedding_provider import get_embedding_provider
from services.reranker import get_reranker_provider
from services.retrieval_score_fusion import fuse_hybrid_score, lexical_gate_allows_strong
from services.scoring import score_knowledge_chunk
from services.vector_index import get_vector_index_backend


VALID_RETRIEVAL_BACKENDS = {"lexical", "vector", "hybrid", "hybrid_rerank"}


def _base_filters(filters):
    filters = filters or {}
    return {
        "course_id": filters.get("course_id"),
        "language": filters.get("language"),
        "knowledge_base_type": filters.get("knowledge_base_type"),
        "scope_type": filters.get("scope_type", "course"),
        "owner_user_id": filters.get("owner_user_id"),
        "visibility": "private" if filters.get("scope_type") == "personal" else "course" if filters.get("scope_type", "course") == "course" else "global",
    }


def _result_with_scores(result, backend, lexical_score=None, vector_score=None, hybrid_score=None):
    enriched = dict(result)
    enriched["lexical_score"] = lexical_score
    enriched["vector_score"] = vector_score
    enriched["hybrid_score"] = hybrid_score
    enriched.setdefault("rerank_score", None)
    enriched["final_retrieval_score"] = hybrid_score if hybrid_score is not None else vector_score if vector_score is not None else lexical_score if lexical_score is not None else result.get("evidence_score", 0)
    enriched["retrieval_backend"] = backend
    enriched["retrieval_version"] = {
        "lexical": "lexical_v1",
        "vector": "vector_local_json_v1",
        "hybrid": "hybrid_v1",
        "hybrid_rerank": "hybrid_rerank_v1",
    }.get(backend, "lexical_v1")
    breakdown = dict(enriched.get("score_breakdown") or {})
    breakdown["lexical_score"] = lexical_score
    breakdown["vector_score"] = vector_score
    breakdown["hybrid_score"] = hybrid_score
    breakdown["rerank_score"] = enriched.get("rerank_score")
    enriched["score_breakdown"] = breakdown
    return enriched


class RetrievalBackend:
    backend_name = "base"

    def search(self, query, filters, kb_version_id, top_k=5, context=None):
        raise NotImplementedError


class LexicalRetrievalBackend(RetrievalBackend):
    backend_name = "lexical"

    def search(self, query, filters, kb_version_id, top_k=5, context=None):
        chunks = (context or {}).get("chunks") or []
        results = lexical_retrieval.retrieve_evidence_results(
            query=query,
            course_id=filters.get("course_id"),
            language=filters.get("language"),
            knowledge_base_type=filters.get("knowledge_base_type"),
            scope_type=filters.get("scope_type", "course"),
            owner_user_id=filters.get("owner_user_id"),
            discipline=filters.get("discipline"),
            limit=top_k,
            chunks=chunks,
        )
        return [_result_with_scores(result, self.backend_name, lexical_score=result.get("evidence_score")) for result in results]


class VectorRetrievalBackend(RetrievalBackend):
    backend_name = "vector"

    def __init__(self, embedding_provider=None, vector_index=None):
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.vector_index = vector_index or get_vector_index_backend()
        self.last_error = ""

    def search(self, query, filters, kb_version_id, top_k=5, context=None):
        if not kb_version_id or not self.embedding_provider.is_available() or self.vector_index.backend_name == "none":
            self.last_error = "Vector retrieval unavailable."
            return []
        chunks = (context or {}).get("chunks") or []
        chunk_by_id = {getattr(chunk, "id", None): chunk for chunk in chunks}
        query_vector = self.embedding_provider.embed_texts([query])[0]
        vector_hits = self.vector_index.search(kb_version_id, query_vector, _base_filters(filters), top_k=max(top_k * 4, 20))
        results = []
        for hit in vector_hits:
            chunk = chunk_by_id.get(hit.get("chunk_id"))
            if chunk is None:
                continue
            score_payload = score_knowledge_chunk(query, chunk, course_id=filters.get("course_id"), discipline=filters.get("discipline"))
            breakdown = score_payload.get("score_breakdown", {})
            if breakdown.get("term_exact_or_alias_match", 0) == 0 and breakdown.get("lexical_overlap_score", 0) < 0.20:
                continue
            if score_payload.get("evidence_score", 0) < lexical_retrieval.EVIDENCE_THRESHOLD:
                continue
            result = lexical_retrieval.result_from_chunk(chunk, score_payload)
            result["_chunk"] = chunk
            results.append(_result_with_scores(result, self.backend_name, lexical_score=breakdown.get("lexical_overlap_score"), vector_score=hit.get("vector_score")))
        results.sort(key=lambda item: item.get("vector_score") or 0, reverse=True)
        return results[:top_k]


class HybridRetrievalBackend(RetrievalBackend):
    backend_name = "hybrid"

    def __init__(self, embedding_provider=None, vector_index=None):
        self.lexical = LexicalRetrievalBackend()
        self.vector = VectorRetrievalBackend(embedding_provider=embedding_provider, vector_index=vector_index)
        self.lexical_weight = float(os.environ.get("HYBRID_LEXICAL_WEIGHT", "0.55"))
        self.vector_weight = float(os.environ.get("HYBRID_VECTOR_WEIGHT", "0.45"))
        self.min_lexical_gate = float(os.environ.get("HYBRID_MIN_LEXICAL_GATE", "0.20"))

    def search(self, query, filters, kb_version_id, top_k=5, context=None):
        lexical_results = self.lexical.search(query, filters, kb_version_id, top_k=max(top_k * 4, 20), context=context)
        vector_results = self.vector.search(query, filters, kb_version_id, top_k=max(top_k * 4, 20), context=context)
        merged = {}
        for item in lexical_results + vector_results:
            chunk_id = item.get("chunk_id")
            if chunk_id not in merged:
                merged[chunk_id] = dict(item)
            else:
                merged[chunk_id].update({key: value for key, value in item.items() if value is not None})
        fused = []
        for item in merged.values():
            lexical_score = item.get("lexical_score") if item.get("lexical_score") is not None else item.get("evidence_score", 0)
            vector_score = item.get("vector_score") or 0
            hybrid_score = fuse_hybrid_score(lexical_score, vector_score, self.lexical_weight, self.vector_weight)
            if not lexical_gate_allows_strong(item.get("score_breakdown"), lexical_score, self.min_lexical_gate):
                flags = set(item.get("risk_flags") or [])
                flags.add("hybrid_lexical_gate")
                item["risk_flags"] = sorted(flags)
                if item.get("evidence_strength") == "strong":
                    item["evidence_strength"] = "weak"
            fused.append(_result_with_scores(item, self.backend_name, lexical_score=lexical_score, vector_score=vector_score, hybrid_score=hybrid_score))
        fused.sort(key=lambda result: result.get("hybrid_score", 0), reverse=True)
        return fused[:top_k]


class HybridRerankRetrievalBackend(HybridRetrievalBackend):
    backend_name = "hybrid_rerank"

    def __init__(self, embedding_provider=None, vector_index=None, reranker=None):
        super().__init__(embedding_provider=embedding_provider, vector_index=vector_index)
        self.reranker = reranker or get_reranker_provider(os.environ.get("RERANKER_PROVIDER", "local_heuristic") if os.environ.get("ENABLE_RERANKER", "false").lower() == "true" else "none")

    def search(self, query, filters, kb_version_id, top_k=5, context=None):
        candidates = super().search(query, filters, kb_version_id, top_k=max(top_k * 4, 20), context=context)
        if not self.reranker.is_available():
            return candidates[:top_k]
        reranked = self.reranker.rerank(query, candidates, top_k)
        for item in reranked:
            item["retrieval_backend"] = self.backend_name
            item["retrieval_version"] = "hybrid_rerank_v1"
            breakdown = dict(item.get("score_breakdown") or {})
            breakdown["rerank_score"] = item.get("rerank_score")
            item["score_breakdown"] = breakdown
        return reranked


def get_retrieval_backend(name=None, embedding_provider=None, vector_index=None, reranker=None):
    backend = (name or os.environ.get("RETRIEVAL_BACKEND", "lexical")).strip().lower()
    if backend == "vector":
        return VectorRetrievalBackend(embedding_provider=embedding_provider, vector_index=vector_index)
    if backend == "hybrid":
        return HybridRetrievalBackend(embedding_provider=embedding_provider, vector_index=vector_index)
    if backend == "hybrid_rerank":
        return HybridRerankRetrievalBackend(embedding_provider=embedding_provider, vector_index=vector_index, reranker=reranker)
    return LexicalRetrievalBackend()
