from services.alignment import (
    can_auto_approve,
    finalize_alignment_decision,
    validate_card_status_transition,
)


def evidence(score=0.86, language="en", flags=None):
    return [{
        "chunk_id": 1,
        "source_title": "Signal Processing Notes",
        "source_citation": "Lecture 3, p.12",
        "language": language,
        "knowledge_base_type": "en_course_kb" if language == "en" else "zh_course_kb",
        "visibility": "course",
        "content_excerpt": "Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        "evidence_score": score,
        "evidence_strength": "strong" if score >= 0.8 else "weak",
        "score_breakdown": {
            "course_scope_score": 1.0,
            "source_quality_score": 0.9,
        },
        "risk_flags": flags or [],
    }]


def base_alignment(**overrides):
    data = {
        "english_term": "Fourier Transform",
        "final_chinese_term": "傅里叶变换",
        "alignment_status": "exact_match",
        "confidence_score": 94,
        "english_evidence_items": evidence(0.9, "en"),
        "chinese_evidence_items": evidence(0.88, "zh"),
        "ai_provider": "deepseek",
        "ai_model": "deepseek-chat",
        "provider_status": "real_provider",
        "is_real_provider": True,
    }
    data.update(overrides)
    return data


def test_missing_english_evidence_becomes_needs_more_evidence():
    result = finalize_alignment_decision(base_alignment(english_evidence_items=[]))
    assert result["alignment_status"] == "no_en_evidence"
    assert result["review_status"] == "needs_more_evidence"
    assert result["confidence_score"] <= 45


def test_missing_chinese_evidence_becomes_needs_more_evidence():
    result = finalize_alignment_decision(base_alignment(chinese_evidence_items=[]))
    assert result["alignment_status"] == "no_zh_evidence"
    assert result["review_status"] == "needs_more_evidence"
    assert result["confidence_score"] <= 45


def test_weak_evidence_requires_quality_control():
    result = finalize_alignment_decision(base_alignment(chinese_evidence_items=evidence(0.7, "zh")))
    assert "weak_evidence" in result["quality_flags"]
    assert result["review_status"] == "pending_quality_control"


def test_domain_ocr_formula_and_conflict_risks_block_auto_approval():
    domain = finalize_alignment_decision(base_alignment(english_evidence_items=evidence(0.88, "en", ["domain_mismatch"])))
    ocr = finalize_alignment_decision(base_alignment(), min_ocr_confidence=35)
    formula = finalize_alignment_decision(base_alignment(formula_status="needs_formula_ocr_engine"))
    conflict = finalize_alignment_decision(base_alignment(multi_translation_conflict=True))

    assert domain["alignment_status"] == "domain_mismatch"
    assert domain["review_status"] == "pending_quality_control"
    assert ocr["alignment_status"] == "ocr_low_confidence"
    assert formula["alignment_status"] == "formula_evidence_missing"
    assert conflict["review_status"] == "conflict_detected"


def test_mock_and_local_provider_cannot_auto_approve():
    result = finalize_alignment_decision(base_alignment(
        ai_provider="mock",
        ai_model="local_heuristic",
        provider_status="local_heuristic",
        is_real_provider=False,
    ))
    assert "mock_or_local_ai" in result["quality_flags"]
    assert result["review_status"] == "pending_quality_control"


def test_strong_live_exact_match_can_auto_approve():
    result = finalize_alignment_decision(base_alignment())
    assert result["review_status"] == "auto_approved"
    allowed, reasons = can_auto_approve({
        "confidence_score": result["confidence_score"],
        "term_quality_score": 0.86,
        "english_evidence_score": result["english_evidence_score"],
        "chinese_evidence_score": result["chinese_evidence_score"],
        "alignment_status": result["alignment_status"],
        "ai_provider": "deepseek",
        "ai_model": "deepseek-chat",
        "provider_status": "real_provider",
        "is_real_provider": True,
        "risk_flags": [],
    })
    assert allowed is True
    assert reasons == []


def test_rejected_cannot_transition_to_auto_approved():
    assert validate_card_status_transition("rejected", "auto_approved", "system", system_action=True) is False
