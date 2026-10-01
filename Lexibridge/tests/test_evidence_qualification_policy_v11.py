from services import bilingual_evidence_qualification as qualification


def test_policy_v11_is_explicit_and_v10_manifest_remains_frozen():
    current = qualification.policy_manifest()
    legacy = qualification.legacy_policy_manifest()

    assert current["policy_version"] == "1.1.0"
    assert current["existing_evidence_threshold_changed"] is False
    assert current["threshold_calibration_source"] == (
        "benchmark-external synthetic semantic-equivalence fixtures"
    )
    assert legacy["policy_version"] == "1.0.0"
    assert legacy["thresholds"] == {
        "minimum_evidence_score": 0.35,
        "minimum_pair_semantic_score": 0.35,
        "minimum_pair_margin": 0.05,
        "minimum_qualification_score": 0.65,
        "minimum_context_chars": 12,
    }


def test_default_policy_cannot_be_selected_by_untrusted_input():
    assert qualification.DEFAULT_POLICY_VERSION == "1.1.0"
    assert "policy_version" not in qualification.BilingualEvidenceQualificationInput.__dataclass_fields__


def test_every_nonqualified_decision_has_a_stable_reason_code():
    assert set(qualification.NON_QUALIFIED_REASON_CODES) >= {
        qualification.EVIDENCE_UPSTREAM_STATE_NOT_READY,
        qualification.EVIDENCE_PAIR_UNCERTAIN,
        qualification.EVIDENCE_PAIR_MARGIN_INSUFFICIENT,
        qualification.EVIDENCE_SCORE_COMPONENT_CONFLICT,
        qualification.EVIDENCE_TERM_SCOPE_RISK,
        qualification.EVIDENCE_CONTEXT_INSUFFICIENT,
        qualification.EVIDENCE_PROVENANCE_INCOMPLETE,
        qualification.EVIDENCE_SOURCE_NOT_ELIGIBLE,
        qualification.EVIDENCE_QUALIFICATION_EXECUTION_FAILED,
    }
