POSITIVE_ALIGNMENT_STATUSES = {
    "exact_match",
    "accepted_translation",
    "auto_approved",
    "approved",
}

POSITIVE_EXPECTED_STATUSES = {
    "exact_match",
    "accepted_translation",
}


def _safe_divide(numerator, denominator, none_when_empty=False):
    if denominator == 0:
        return None if none_when_empty else 0
    return round(float(numerator) / float(denominator), 4)


def compute_evaluation_metrics(results):
    results = results or []
    total = len(results)

    extracted_total = sum(int(item.get("system_extracted_term_count", 0) or 0) for item in results)
    correct_extracted_total = sum(int(item.get("correct_extracted_term_count", 0) or 0) for item in results)
    expected_found = sum(1 for item in results if item.get("expected_term_found"))

    english_returned = [item for item in results if item.get("english_evidence_returned")]
    chinese_returned = [item for item in results if item.get("chinese_evidence_returned")]
    any_evidence_returned = [item for item in results if item.get("english_evidence_returned") or item.get("chinese_evidence_returned")]
    both_evidence_returned = [
        item for item in any_evidence_returned
        if item.get("english_evidence_correct") and item.get("chinese_evidence_correct")
    ]

    alignment_correct = sum(1 for item in results if item.get("alignment_status_correct"))
    false_positive = 0
    for item in results:
        actual_status = str(item.get("actual_alignment_status", "") or "")
        card_status = str(item.get("card_status", "") or "")
        expected_status = str(item.get("expected_alignment_status", "") or "")
        system_positive = actual_status in POSITIVE_ALIGNMENT_STATUSES or card_status in POSITIVE_ALIGNMENT_STATUSES
        expected_positive = expected_status in POSITIVE_EXPECTED_STATUSES
        if system_positive and not expected_positive:
            false_positive += 1

    auto_approved_items = [item for item in results if item.get("card_status") == "auto_approved"]
    auto_approval_errors = [
        item for item in auto_approved_items
        if str(item.get("expected_alignment_status", "")) not in POSITIVE_EXPECTED_STATUSES
    ]

    forced_alignment = 0
    for item in results:
        missing_evidence = not item.get("english_evidence_returned") or not item.get("chinese_evidence_returned")
        actual_status = str(item.get("actual_alignment_status", "") or "")
        card_status = str(item.get("card_status", "") or "")
        system_positive = actual_status in POSITIVE_EXPECTED_STATUSES or card_status == "auto_approved"
        if missing_evidence and system_positive:
            forced_alignment += 1

    ocr_candidates = sum(int(item.get("ocr_term_candidate_count", 0) or 0) for item in results)
    ocr_noise = sum(int(item.get("ocr_noise_term_count", 0) or 0) for item in results)

    metrics = {
        "input_count": total,
        "skipped_count": sum(1 for item in results if item.get("skipped")),
        "extraction_precision": _safe_divide(correct_extracted_total, extracted_total),
        "extraction_recall": _safe_divide(expected_found, total),
        "english_evidence_accuracy": _safe_divide(
            sum(1 for item in english_returned if item.get("english_evidence_correct")),
            len(english_returned),
        ),
        "chinese_evidence_accuracy": _safe_divide(
            sum(1 for item in chinese_returned if item.get("chinese_evidence_correct")),
            len(chinese_returned),
        ),
        "evidence_accuracy": _safe_divide(len(both_evidence_returned), len(any_evidence_returned)),
        "alignment_accuracy": _safe_divide(alignment_correct, total),
        "false_positive_rate": _safe_divide(false_positive, total),
        "auto_approval_error_rate": _safe_divide(len(auto_approval_errors), len(auto_approved_items)),
        "ocr_noise_term_rate": _safe_divide(ocr_noise, ocr_candidates, none_when_empty=True),
        "no_evidence_forced_alignment_rate": _safe_divide(forced_alignment, total),
        "counts": {
            "system_extracted_term_count": extracted_total,
            "correct_extracted_term_count": correct_extracted_total,
            "expected_term_found_count": expected_found,
            "english_evidence_returned_count": len(english_returned),
            "chinese_evidence_returned_count": len(chinese_returned),
            "false_positive_count": false_positive,
            "auto_approved_count": len(auto_approved_items),
            "auto_approval_error_count": len(auto_approval_errors),
            "no_evidence_forced_alignment_count": forced_alignment,
            "ocr_term_candidate_count": ocr_candidates,
            "ocr_noise_term_count": ocr_noise,
        }
    }
    return metrics


SMOKE_RELEASE_GATE = {
    "extraction_precision": (">=", 0.75),
    "extraction_recall": (">=", 0.60),
    "evidence_accuracy": (">=", 0.70),
    "alignment_accuracy": (">=", 0.70),
    "false_positive_rate": ("<=", 0.10),
    "auto_approval_error_rate": ("<=", 0.05),
    "no_evidence_forced_alignment_rate": ("==", 0.0),
}


def evaluate_release_gate(metrics, thresholds=None):
    thresholds = thresholds or SMOKE_RELEASE_GATE
    checks = {}
    passed = True
    for name, (operator, target) in thresholds.items():
        value = metrics.get(name)
        if value is None:
            ok = False
        elif operator == ">=":
            ok = value >= target
        elif operator == "<=":
            ok = value <= target
        elif operator == "==":
            ok = value == target
        else:
            ok = False
        checks[name] = {
            "value": value,
            "operator": operator,
            "target": target,
            "passed": ok,
        }
        passed = passed and ok
    return {
        "passed": passed,
        "checks": checks,
    }
