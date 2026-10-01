from scripts.evaluations import candidate_failure_diagnosis as diagnosis


def test_incomplete_alias_is_a_benchmark_defect():
    result = diagnosis.audit_benchmark_item(
        english_term="potential difference",
        english_aliases=(),
        chinese_term="电势差",
        chinese_aliases=(),
        english_source="Voltage is the difference in electric potential between two points.",
        chinese_source="电势差是两点电势的差值，也称电压。",
    )
    assert result["benchmark_status"] == "BENCHMARK_ALIAS_INCOMPLETE"


def test_term_absent_from_source_is_not_extractor_attribution():
    result = diagnosis.audit_benchmark_item(
        english_term="missing term",
        english_aliases=(),
        chinese_term="缺失术语",
        chinese_aliases=(),
        english_source="Unrelated content.",
        chinese_source="无关内容。",
    )
    trace = diagnosis.DiagnosticTrace(
        concept_id="physics-01",
        source_term_present=False,
        parsed_text_term_present=False,
        chunk_term_present=False,
        exact_candidate_present=False,
        near_candidate_present=False,
        overlong_candidate_present=False,
        fragmented_candidate_present=False,
        normalized_match_present=False,
        binding_status="missing",
        benchmark_status=result["benchmark_status"],
    )
    assert result["benchmark_status"] == "BENCHMARK_TERM_NOT_IN_SOURCE"
    assert diagnosis.attribute_failure(trace) == "BENCHMARK_FIXTURE_DEFECT"


def test_artifact_input_is_not_mutated():
    payload = {"concept_id": "physics-01", "candidate_summary": "safe"}
    original = dict(payload)
    diagnosis.sanitize_artifact(payload)
    assert payload == original
