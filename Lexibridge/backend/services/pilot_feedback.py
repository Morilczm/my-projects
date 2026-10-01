"""Pilot feedback classification and workflow helpers."""

from __future__ import annotations


FEEDBACK_TYPES = {
    "translation_error",
    "evidence_error",
    "concept_explanation_error",
    "missing_term",
    "wrong_term_extraction",
    "ocr_error",
    "formula_ocr_error",
    "ui_confusion",
    "permission_issue",
    "performance_issue",
    "export_issue",
    "other",
}

FEEDBACK_SOURCES = {
    "student_card_detail",
    "student_search_result",
    "student_personal_upload",
    "teacher_quality_control",
    "teacher_document_review",
    "admin_evaluation_review",
    "pilot_form_import",
    "student_concept_card",
}

SEVERITIES = {"low", "medium", "high", "critical"}

FEEDBACK_STATUSES = {
    "submitted",
    "triaged",
    "in_review",
    "needs_more_evidence",
    "resolved",
    "rejected",
    "converted_to_backlog",
    "converted_to_evaluation_item",
    "linked_to_review",
    "duplicate",
    "closed",
}

CLASSIFICATIONS = {
    "data_gap",
    "retrieval_failure",
    "alignment_failure",
    "ocr_failure",
    "formula_ocr_failure",
    "term_extraction_failure",
    "teacher_review_needed",
    "ui_usability",
    "permission_security",
    "performance_stability",
    "not_a_bug",
}

ROOT_CAUSES = {
    "missing_chinese_kb",
    "missing_english_kb",
    "weak_evidence",
    "wrong_evidence",
    "domain_mismatch",
    "ocr_noise",
    "formula_missing",
    "ai_provider_error",
    "prompt_issue",
    "threshold_issue",
    "user_misunderstanding",
    "unknown",
}


def normalize_choice(value, allowed, default):
    value = str(value or "").strip().lower()
    return value if value in allowed else default


def classify_feedback(feedback_type, reported_issue=""):
    feedback_type = normalize_choice(feedback_type, FEEDBACK_TYPES, "other")
    text = str(reported_issue or "").lower()
    mapping = {
        "translation_error": ("alignment_failure", "prompt_issue"),
        "evidence_error": ("retrieval_failure", "wrong_evidence"),
        "concept_explanation_error": ("alignment_failure", "prompt_issue"),
        "missing_term": ("data_gap", "missing_english_kb"),
        "wrong_term_extraction": ("term_extraction_failure", "threshold_issue"),
        "ocr_error": ("ocr_failure", "ocr_noise"),
        "formula_ocr_error": ("formula_ocr_failure", "formula_missing"),
        "ui_confusion": ("ui_usability", "user_misunderstanding"),
        "permission_issue": ("permission_security", "unknown"),
        "performance_issue": ("performance_stability", "unknown"),
        "export_issue": ("frontend_ux", "unknown"),
    }
    classification, root_cause = mapping.get(feedback_type, ("teacher_review_needed", "unknown"))
    if "中文" in text or "chinese" in text:
        root_cause = "missing_chinese_kb" if feedback_type == "missing_term" else root_cause
    return classification, root_cause


def should_escalate_card(feedback_type, severity, open_high_count=0):
    feedback_type = normalize_choice(feedback_type, FEEDBACK_TYPES, "other")
    severity = normalize_choice(severity, SEVERITIES, "medium")
    if severity == "critical":
        return True
    if feedback_type in {"translation_error", "evidence_error"} and severity == "high" and open_high_count >= 2:
        return True
    return False


def anonymize_user(user_id):
    return f"student-{int(user_id or 0):04d}"
