"""Score normalization and fusion for hybrid retrieval."""

from __future__ import annotations


def normalize_scores(items, key):
    values = [float(item.get(key) or 0) for item in items]
    max_value = max(values) if values else 0
    if max_value <= 0:
        return {item.get("chunk_id"): 0.0 for item in items}
    return {item.get("chunk_id"): round(float(item.get(key) or 0) / max_value, 6) for item in items}


def fuse_hybrid_score(lexical_score, vector_score, lexical_weight=0.55, vector_weight=0.45):
    return round(float(lexical_weight) * float(lexical_score or 0) + float(vector_weight) * float(vector_score or 0), 6)


def lexical_gate_allows_strong(score_breakdown, lexical_score, min_lexical_gate=0.20):
    exact = float((score_breakdown or {}).get("term_exact_or_alias_match") or 0)
    lexical_overlap = float((score_breakdown or {}).get("lexical_overlap_score") or lexical_score or 0)
    return exact > 0 or lexical_overlap >= float(min_lexical_gate)
