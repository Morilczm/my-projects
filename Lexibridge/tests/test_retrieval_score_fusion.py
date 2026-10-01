from services.retrieval_score_fusion import fuse_hybrid_score, lexical_gate_allows_strong, normalize_scores


def test_score_fusion_and_lexical_gate():
    assert normalize_scores([{"chunk_id": 1, "score": 2}, {"chunk_id": 2, "score": 1}], "score")[1] == 1.0
    assert fuse_hybrid_score(0.8, 0.6, 0.5, 0.5) == 0.7
    assert lexical_gate_allows_strong({"term_exact_or_alias_match": 0, "lexical_overlap_score": 0.1}, 0.1) is False
    assert lexical_gate_allows_strong({"term_exact_or_alias_match": 1, "lexical_overlap_score": 0.0}, 0.0) is True
