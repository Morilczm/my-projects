from services import parse_quality_risk


def test_native_text_ok_adds_no_parse_risk():
    metadata = {"quality_status": "native_text_ok", "quality_flags": ["native_text_ok"]}

    assert parse_quality_risk.parse_quality_to_risk_labels(metadata) == []
    assert parse_quality_risk.should_force_needs_review(metadata) is False


def test_partial_text_maps_to_input_partial_text():
    metadata = {"quality_status": "partial_text", "quality_flags": ["partial_text"]}

    assert parse_quality_risk.parse_quality_to_risk_labels(metadata) == ["input_partial_text"]
    assert parse_quality_risk.parse_quality_to_review_status(metadata) == "needs_review"
    assert parse_quality_risk.should_force_needs_review(metadata) is True


def test_mixed_quality_maps_to_input_mixed_quality():
    metadata = {"quality_status": "mixed_quality", "quality_flags": ["mixed_quality"]}

    assert parse_quality_risk.parse_quality_to_risk_labels(metadata) == ["input_mixed_quality"]
    assert parse_quality_risk.should_force_needs_review(metadata) is True


def test_ocr_low_confidence_maps_to_ocr_low_confidence():
    metadata = {"quality_status": "ocr_low_confidence", "quality_flags": ["ocr_low_confidence"]}

    assert parse_quality_risk.parse_quality_to_risk_labels(metadata) == ["ocr_low_confidence"]


def test_formula_ocr_unavailable_maps_to_formula_recognition_unavailable():
    metadata = {
        "quality_status": "formula_ocr_unavailable",
        "quality_flags": ["formula_ocr_unavailable"],
    }

    assert parse_quality_risk.parse_quality_to_risk_labels(metadata) == ["formula_recognition_unavailable"]


def test_merge_risk_labels_deduplicates_and_preserves_order():
    labels = parse_quality_risk.merge_risk_labels(
        ["weak_evidence", "input_partial_text"],
        ["input_partial_text", "formula_context_risk"],
    )

    assert labels == ["weak_evidence", "input_partial_text", "formula_context_risk"]


def test_blocked_quality_status_blocks_downstream_creation():
    metadata = {"quality_status": "parse_failed", "quality_flags": ["parse_failed"]}

    assert parse_quality_risk.parse_quality_to_review_status(metadata) == "blocked"
    assert parse_quality_risk.should_block_downstream_creation(metadata) is True
