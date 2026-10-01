from scripts.evaluations import chinese_candidate_precision_diagnosis as diagnosis


def _trace(**overrides):
    values = {
        "source_term_present": True,
        "parsed_text_term_present": True,
        "chunk_term_present": True,
        "retrieval_rank": 1,
        "candidate_count": 1,
        "exact_candidate_rank": 1,
        "alias_candidate_rank": None,
        "boundary_defect_present": False,
        "fragmentation_present": False,
        "normalization_defect_present": False,
        "selected_candidate_correct": True,
        "pair_correct": True,
        "readiness_status": "prepared",
        "benchmark_alias_gap": False,
        "benchmark_fixture_defect": False,
        "ambiguous": False,
    }
    values.update(overrides)
    return diagnosis.ChineseCandidateTrace(**values)


def test_top1_exact_candidate_with_wrong_pair_is_pairing_defect():
    assert diagnosis.attribute_failure(
        _trace(selected_candidate_correct=True, pair_correct=False)
    ) == "BILINGUAL_PAIRING_DEFECT"


def test_correct_pair_with_failed_readiness_is_evidence_readiness_defect():
    assert diagnosis.attribute_failure(
        _trace(readiness_status="evidence_insufficient")
    ) == "EVIDENCE_READINESS_DEFECT"


def test_pairing_audit_separates_candidate_precision_from_selection():
    audit = diagnosis.run_diagnosis()["pairing_audit"]

    assert audit["correct_english_input_count"] == 25
    assert audit["correct_chinese_input_count"] == 0
    assert audit["pairing_defect_count"] == 0
    assert audit["features"]["exact_english_match"] is True
    assert audit["features"]["source_proximity"] is True
    assert audit["features"]["definition_similarity"] is False
    assert audit["features"]["retrieval_rank"] is False
    assert audit["features"]["candidate_confidence"] is True
    assert audit["features"]["abbreviation_mapping"] is False
    assert audit["provenance_retained"] is True
    assert audit["explicit_pair_failure_reason_code"] is False
