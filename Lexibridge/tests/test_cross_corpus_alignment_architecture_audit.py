import json

from scripts.evaluations import cross_corpus_alignment_architecture_audit as audit


def test_english_only_input_is_traceable_but_cannot_identify_standard_chinese_term():
    result = audit.trace_english_only_input(
        "Electric field is force per unit positive test charge."
    )

    assert result["english_only"] is True
    assert result["english_term_extraction_supported"] is True
    assert result["standard_chinese_term_generated"] is False
    assert result["blocker"] == "CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_MISSING"


def test_independent_sources_are_modeled_separately():
    result = audit.run_audit()

    assert result["source_model"]["knowledge_source_has_language"] is True
    assert result["source_model"]["english_chinese_sources_are_independent_records"] is True
    assert result["source_model"]["independent_chinese_source_ingestion_supported"] is True
    assert result["source_model"]["chinese_source_required_from_user_or_governed_store"] is True


def test_language_filter_and_inline_shortcut_are_detected():
    assert audit.has_explicit_language_filter(
        {"language": "zh", "source_role": "chinese_reference_material"}
    )
    assert not audit.has_explicit_language_filter(
        {"source_role": "chinese_reference_material"}
    )
    assert audit.detect_inline_bilingual_shortcut("electric field 即 电场表示单位正电荷受力")
    assert not audit.detect_inline_bilingual_shortcut("电场表示单位正电荷在某点受到的力")


def test_missing_semantic_identification_and_pairing_are_detected():
    assert audit.classify_term_identification(
        {
            "existing_exact_mapping": False,
            "inline_bilingual_regex": True,
            "monolingual_chinese_definition_subject_extractor": False,
            "cross_language_translation": False,
        }
    ) == "CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_MISSING"
    assert audit.classify_pairing(
        {
            "selects_highest_candidate_score": True,
            "compares_english_context": False,
            "compares_chinese_context": False,
            "semantic_similarity": False,
        }
    ) == "CROSS_CORPUS_SEMANTIC_PAIRING_MISSING"


def test_audit_preserves_denominator_and_provider_isolation():
    result = audit.run_audit()

    assert result["status"] == "CROSS_CORPUS_ALIGNMENT_ARCHITECTURE_AUDIT_COMPLETED"
    assert len(result["concept_flows"]) == 25
    assert all(row["included_in_denominator"] is True for row in result["concept_flows"])
    assert all(float(row["retrieval_score"]) > 0 for row in result["concept_flows"])
    assert result["english_extraction"]["exact_matched"] == 25
    ready_items = result["evidence_readiness"]["ready_items"]
    assert len(ready_items) == 5
    assert all(item["english_evidence_refs"] for item in ready_items)
    assert all(item["chinese_evidence_refs"] for item in ready_items)
    assert all(item["semantic_pairing_verified"] is False for item in ready_items)
    assert result["real_provider_requests"] == 0
    assert result["production_files_modified"] == []


def test_artifacts_are_sanitized():
    serialized = json.dumps(audit.artifact_payloads(audit.run_audit()), ensure_ascii=False)

    for forbidden in (
        "/Users/",
        "DEEPSEEK_API_KEY",
        "Authorization:",
        "Bearer ",
        "Electric field is force per unit positive test charge.",
        "电荷（electric charge）是物质产生电相互作用的属性",
    ):
        assert forbidden not in serialized
