"""Iteration backlog mapping helpers for pilot feedback."""

from __future__ import annotations


BACKLOG_CATEGORIES = {
    "data_quality",
    "retrieval",
    "alignment",
    "ocr",
    "formula_ocr",
    "evaluation",
    "frontend_ux",
    "security_privacy",
    "performance",
    "documentation",
    "deployment",
}

BACKLOG_STATUSES = {"open", "planned", "in_progress", "done", "wont_fix", "duplicate"}


def map_feedback_to_category(feedback_type, classification=""):
    feedback_type = str(feedback_type or "").strip().lower()
    classification = str(classification or "").strip().lower()
    if feedback_type == "formula_ocr_error" or classification == "formula_ocr_failure":
        return "formula_ocr"
    if feedback_type == "ocr_error" or classification == "ocr_failure":
        return "ocr"
    if feedback_type == "permission_issue" or classification == "permission_security":
        return "security_privacy"
    if feedback_type in {"evidence_error"} or classification == "retrieval_failure":
        return "retrieval"
    if feedback_type in {"translation_error", "concept_explanation_error"} or classification == "alignment_failure":
        return "alignment"
    if feedback_type in {"missing_term", "wrong_term_extraction"}:
        return "data_quality"
    if feedback_type in {"ui_confusion", "export_issue"}:
        return "frontend_ux"
    if feedback_type == "performance_issue":
        return "performance"
    return "documentation"


def map_feedback_to_priority(feedback_type, severity, classification=""):
    severity = str(severity or "").strip().lower()
    category = map_feedback_to_category(feedback_type, classification)
    if severity == "critical" or category == "security_privacy":
        return "P0"
    if severity == "high" or category in {"retrieval", "alignment", "formula_ocr"}:
        return "P1"
    if severity == "medium":
        return "P2"
    return "P3"


def default_acceptance_criteria(feedback_type, category):
    if category == "security_privacy":
        return "Reproduce the issue, close the permission gap, add regression tests, and verify no private data is exposed."
    if category == "retrieval":
        return "Add or update evidence fixtures, prevent the wrong evidence match, and add regression evaluation coverage."
    if category == "alignment":
        return "Update alignment status/risk handling and verify the card no longer reaches an unsafe status."
    if category == "formula_ocr":
        return "Mark formula limitation clearly or configure a provider; add a regression sample."
    if category == "frontend_ux":
        return "Improve the visible workflow and confirm the user can complete the task without console inspection."
    return "Define expected behavior, implement the fix, and add a regression test."
