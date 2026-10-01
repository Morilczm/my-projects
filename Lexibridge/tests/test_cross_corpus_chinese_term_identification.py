from services.chinese_term_candidates import identify_standard_chinese_terms


def test_independent_monolingual_evidence_produces_ranked_standard_terms():
    evidence = [{
        "source_uid": "opaque-zh-source",
        "chunk_uid": "opaque-zh-chunk",
        "language": "zh",
        "snippet": "磁通量描述穿过给定曲面的磁场总量。电流密度是邻近但不同的概念。",
        "rank": 1,
        "score": 0.78,
        "status": "active",
        "quality_status": "ready",
        "source_role": "chinese_reference_material",
        "provenance": {"source_uid": "opaque-zh-source", "chunk_uid": "opaque-zh-chunk"},
    }]
    result = identify_standard_chinese_terms(
        "an English-only technical context with no shared term",
        evidence,
        discipline="physics",
    )
    assert {candidate["chinese_term"] for candidate in result.candidates[:2]} == {
        "磁通量", "电流密度",
    }
    assert all(candidate["source_language"] == "zh" for candidate in result.candidates)
    assert all(candidate["rank"] >= 1 for candidate in result.candidates)
