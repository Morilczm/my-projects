from scripts.evaluations import cross_corpus_alignment_architecture_audit as audit
from scripts.evaluations.bilingual_knowledge_quality import dataset


def test_frozen_benchmark_hashes_and_source_counts_are_preserved():
    result = audit.audit_benchmark_integrity()

    assert result["frozen_hashes"] == {
        "corpus_sha256": "33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc",
        "gold_sha256": "199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302",
    }
    assert result["english_source_count"] == 2
    assert result["chinese_source_count"] == 2
    assert result["physical_source_records_independent"] is True


def test_fixture_template_and_keyword_leakage_are_detected():
    result = audit.detect_fixture_leakage(dataset.build_corpus(), dataset.build_gold())

    assert result["shared_generator_constants"] is True
    assert result["parallel_template_mirror"] is True
    assert result["inline_bilingual_pattern_count"] == 25
    assert result["english_source_contains_chinese_gold_terms"] is False
    assert result["chinese_source_contains_all_english_gold_terms"] is True
    assert result["english_keyword_retrieval_leakage"] is True
    assert result["source_id_concept_leakage"] is False
    assert result["fixed_order_mapping_used_by_production"] is False


def test_benchmark_does_not_validate_real_cross_corpus_scenario():
    result = audit.audit_benchmark_integrity()

    assert result["simulates_english_slide_plus_independent_chinese_textbook"] is False
    assert result["cross_corpus_semantic_retrieval_validated"] is False
    assert result["historical_retrieval_hit_at_3_interpretation"] == (
        "BILINGUAL_KEYWORD_TEMPLATE_SELF_MATCH_NOT_CROSS_LANGUAGE_VALIDATION"
    )
