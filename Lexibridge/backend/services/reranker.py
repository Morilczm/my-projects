"""Reranker provider abstraction."""

from __future__ import annotations

from services.scoring import score_knowledge_chunk


class RerankerProvider:
    def rerank(self, query, candidates, top_k):
        return candidates[:top_k]

    def provider_name(self):
        return "none"

    def is_available(self):
        return False


class NoneRerankerProvider(RerankerProvider):
    pass


class LocalHeuristicRerankerProvider(RerankerProvider):
    def provider_name(self):
        return "local_heuristic"

    def is_available(self):
        return True

    def rerank(self, query, candidates, top_k):
        reranked = []
        for item in candidates:
            chunk = item.get("_chunk")
            score_payload = score_knowledge_chunk(query, chunk) if chunk is not None else {"score_breakdown": {}, "evidence_score": 0}
            breakdown = score_payload.get("score_breakdown", {})
            rerank_score = (
                0.50 * float(breakdown.get("term_exact_or_alias_match") or 0)
                + 0.25 * float(breakdown.get("lexical_overlap_score") or 0)
                + 0.15 * float(item.get("final_retrieval_score") or item.get("hybrid_score") or item.get("evidence_score") or 0)
                + 0.10 * float(breakdown.get("source_quality_score") or 0)
            )
            enriched = dict(item)
            enriched["rerank_score"] = round(rerank_score, 6)
            enriched["reranker_provider"] = self.provider_name()
            enriched["rerank_reason"] = "Local heuristic rerank using exact match, lexical overlap, source quality, and prior retrieval score."
            reranked.append(enriched)
        reranked.sort(key=lambda result: result.get("rerank_score", 0), reverse=True)
        return reranked[:top_k]


def get_reranker_provider(name=None):
    provider = (name or "").strip().lower()
    if provider == "local_heuristic":
        return LocalHeuristicRerankerProvider()
    return NoneRerankerProvider()
