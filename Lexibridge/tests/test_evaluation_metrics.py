from services.evaluation_metrics import compute_evaluation_metrics, evaluate_release_gate


def test_evaluation_metrics_compute_core_rates():
    results = [
        {
            "system_extracted_term_count": 2,
            "correct_extracted_term_count": 1,
            "expected_term_found": True,
            "english_evidence_returned": True,
            "chinese_evidence_returned": True,
            "english_evidence_correct": True,
            "chinese_evidence_correct": True,
            "actual_alignment_status": "exact_match",
            "expected_alignment_status": "exact_match",
            "alignment_status_correct": True,
            "card_status": "auto_approved",
        },
        {
            "system_extracted_term_count": 1,
            "correct_extracted_term_count": 0,
            "expected_term_found": False,
            "english_evidence_returned": True,
            "chinese_evidence_returned": False,
            "english_evidence_correct": False,
            "chinese_evidence_correct": False,
            "actual_alignment_status": "exact_match",
            "expected_alignment_status": "no_zh_evidence",
            "alignment_status_correct": False,
            "card_status": "pending_quality_control",
            "ocr_term_candidate_count": 1,
            "ocr_noise_term_count": 1,
        },
    ]

    metrics = compute_evaluation_metrics(results)

    assert metrics["extraction_precision"] == 0.3333
    assert metrics["extraction_recall"] == 0.5
    assert metrics["english_evidence_accuracy"] == 0.5
    assert metrics["chinese_evidence_accuracy"] == 1.0
    assert metrics["evidence_accuracy"] == 0.5
    assert metrics["alignment_accuracy"] == 0.5
    assert metrics["false_positive_rate"] == 0.5
    assert metrics["auto_approval_error_rate"] == 0.0
    assert metrics["no_evidence_forced_alignment_rate"] == 0.5
    assert metrics["ocr_noise_term_rate"] == 1.0


def test_auto_approval_error_rate_and_release_gate():
    metrics = compute_evaluation_metrics([
        {
            "system_extracted_term_count": 1,
            "correct_extracted_term_count": 1,
            "expected_term_found": True,
            "english_evidence_returned": True,
            "chinese_evidence_returned": True,
            "english_evidence_correct": True,
            "chinese_evidence_correct": True,
            "actual_alignment_status": "exact_match",
            "expected_alignment_status": "domain_mismatch",
            "alignment_status_correct": False,
            "card_status": "auto_approved",
        }
    ])

    assert metrics["auto_approval_error_rate"] == 1.0
    gate = evaluate_release_gate(metrics)
    assert gate["passed"] is False
    assert gate["checks"]["auto_approval_error_rate"]["passed"] is False
