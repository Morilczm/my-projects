from services.scoring import calculate_confidence_score


def test_confidence_score_without_risk_is_weighted():
    result = calculate_confidence_score(0.9, 0.88, 0.84, 0.8, 1.0, 0.8, [])
    assert result["confidence_score"] == 87
    assert result["score_breakdown"]["risk_penalty"] == 0


def test_confidence_score_applies_required_risk_penalties():
    no_zh = calculate_confidence_score(1, 1, 0, 1, 1, 1, ["no_zh_evidence"])
    domain = calculate_confidence_score(1, 1, 1, 1, 1, 1, ["domain_mismatch"])
    mock = calculate_confidence_score(1, 1, 1, 1, 1, 1, ["mock_or_local_ai"])
    invalid = calculate_confidence_score(1, 1, 1, 1, 1, 1, ["invalid_term_candidate"])

    assert no_zh["score_breakdown"]["risk_penalty"] == 40
    assert domain["confidence_score"] == 50
    assert mock["confidence_score"] == 70
    assert invalid["confidence_score"] == 40


def test_confidence_score_clamps_to_zero_and_serializes_breakdown():
    result = calculate_confidence_score(0, 0, 0, 0, 0, 0, ["invalid_term_candidate", "domain_mismatch"])
    assert result["confidence_score"] == 0
    assert "term_quality_score" in result["score_breakdown"]
    assert result["risk_flags"] == ["domain_mismatch", "invalid_term_candidate"]
