from scripts.evaluations import candidate_failure_diagnosis as diagnosis


def _trace(**overrides):
    values = {
        "concept_id": "physics-01",
        "source_term_present": True,
        "parsed_text_term_present": True,
        "chunk_term_present": True,
        "exact_candidate_present": False,
        "near_candidate_present": False,
        "overlong_candidate_present": False,
        "fragmented_candidate_present": False,
        "normalized_match_present": False,
        "binding_status": "missing",
        "benchmark_status": "BENCHMARK_SOURCE_VALID",
    }
    values.update(overrides)
    return diagnosis.DiagnosticTrace(**values)


def test_attribution_distinguishes_pipeline_stages():
    assert diagnosis.attribute_failure(_trace()) == "CANDIDATE_EXTRACTION_DEFECT"
    assert diagnosis.attribute_failure(
        _trace(parsed_text_term_present=False, chunk_term_present=False)
    ) == "PARSING_DEFECT"
    assert diagnosis.attribute_failure(
        _trace(chunk_term_present=False)
    ) == "CHUNKING_DEFECT"


def test_boundary_and_fragmentation_precede_generic_extraction():
    assert diagnosis.attribute_failure(
        _trace(overlong_candidate_present=True)
    ) == "CANDIDATE_BOUNDARY_DEFECT"
    assert diagnosis.attribute_failure(
        _trace(fragmented_candidate_present=True)
    ) == "CANDIDATE_FRAGMENTATION_DEFECT"


def test_diagnosis_distinguishes_governance_overflow_from_true_missing():
    overflow = _trace(
        candidate_governance_overflow_present=True,
        candidate_overflow_match_present=True,
    )
    missing = _trace(candidate_governance_overflow_present=True)

    assert diagnosis.attribute_failure(overflow) == "CANDIDATE_GOVERNANCE_OVERFLOW"
    assert diagnosis.attribute_failure(missing) == "CANDIDATE_EXTRACTION_DEFECT"


def test_residual_boundary_requires_a_term_leading_definition_fragment():
    mass = diagnosis._candidate_diagnostics(
        "mass",
        [{"id": "1", "text": "Mass measures the amount", "length": 24, "normalized": "mass measures the amount"}],
    )
    force = diagnosis._candidate_diagnostics(
        "force",
        [{"id": "2", "text": "Centripetal force", "length": 17, "normalized": "centripetal force"}],
    )

    assert mass["overlong"]
    assert force["overlong"] == []


def test_unicode_and_case_are_diagnostic_only():
    comparison = diagnosis.compare_candidate("Electric Potential", "ｅｌｅｃｔｒｉｃ potential")
    assert comparison["normalized_exact"] is True
    assert comparison["raw_exact"] is False
    assert diagnosis.attribute_failure(
        _trace(near_candidate_present=True, normalized_match_present=True)
    ) == "BINDING_DEFECT"


def test_runner_preserves_denominator_and_never_calls_provider():
    rows = diagnosis.build_diagnostic_rows(
        [{"concept_id": f"physics-{index:02d}"} for index in range(1, 26)],
        trace_item=lambda item: _trace(concept_id=item["concept_id"]),
    )
    assert len(rows) == 25
    assert all(row["included_in_denominator"] is True for row in rows)
    assert diagnosis.REAL_PROVIDER_REQUESTS == 0


def test_sanitizer_rejects_source_text_paths_and_credentials():
    safe = diagnosis.sanitize_artifact({
        "concept_id": "physics-01",
        "source_excerpt": "full source",
        "path": "LOCAL_PATH_SENTINEL",
        "api_key": "secret",
        "candidate_summary": "bounded",
    })
    assert safe == {"concept_id": "physics-01", "candidate_summary": "bounded"}
