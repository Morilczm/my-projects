"""Generate privacy-preserving pilot reports."""

from __future__ import annotations

from collections import Counter


def redact_identifier(value):
    if not value:
        return ""
    text = str(value)
    if "@" in text:
        prefix, _, domain = text.partition("@")
        return f"{prefix[:2]}***@{domain}"
    return text[:2] + "***" if len(text) > 4 else "***"


def count_by(items, attr):
    return dict(Counter(str(getattr(item, attr, "") or "unknown") for item in items))


def generate_pilot_report_markdown(
    course,
    feedbacks,
    cards,
    jobs,
    evaluation_run=None,
    backlog_items=None,
    usage_summary=None,
):
    backlog_items = backlog_items or []
    usage_summary = usage_summary or {}
    course_name = getattr(course, "name", "All Courses") if course else "All Courses"
    course_id = getattr(course, "id", None)
    card_status_counts = count_by(cards, "status")
    alignment_counts = count_by(cards, "alignment_status")
    feedback_type_counts = count_by(feedbacks, "feedback_type")
    feedback_severity_counts = count_by(feedbacks, "severity")
    feedback_status_counts = count_by(feedbacks, "status")
    backlog_priority_counts = count_by(backlog_items, "priority")
    unresolved_high = [
        fb for fb in feedbacks
        if getattr(fb, "severity", "") in {"high", "critical"} and getattr(fb, "status", "") not in {"resolved", "closed", "rejected"}
    ]
    latest_eval = evaluation_run
    lines = [
        "# LexiBridge AI Pilot Report",
        "",
        "## Basic Information",
        f"- course: {course_name}",
        f"- course_id: {course_id or 'all'}",
        f"- documents uploaded: {usage_summary.get('documents', 0)}",
        f"- terminology cards generated: {len(cards)}",
        f"- jobs completed: {len([job for job in jobs if getattr(job, 'status', '') == 'completed'])}",
        f"- evaluation runs: {usage_summary.get('evaluation_runs', 0)}",
        "",
        "## Usage Summary",
        f"- active students: {usage_summary.get('active_students', 0)}",
        f"- active teachers: {usage_summary.get('active_teachers', 0)}",
        f"- searches: {usage_summary.get('searches', 0)}",
        f"- favorites: {usage_summary.get('favorites', 0)}",
        f"- mastered marks: {usage_summary.get('mastered', 0)}",
        f"- feedback submitted: {len(feedbacks)}",
        f"- exports: {usage_summary.get('exports', 0)}",
        "",
        "## Terminology Quality",
        f"- total cards: {len(cards)}",
        f"- approved cards: {card_status_counts.get('approved', 0)}",
        f"- auto-approved cards: {card_status_counts.get('auto_approved', 0)}",
        f"- pending QC: {card_status_counts.get('pending_quality_control', 0)}",
        f"- needs more evidence: {card_status_counts.get('needs_more_evidence', 0)}",
        f"- conflict detected: {card_status_counts.get('conflict_detected', 0)}",
        f"- no_en_evidence: {alignment_counts.get('no_en_evidence', 0)}",
        f"- no_zh_evidence: {alignment_counts.get('no_zh_evidence', 0)}",
        f"- domain_mismatch: {alignment_counts.get('domain_mismatch', 0)}",
        f"- formula_evidence_missing: {alignment_counts.get('formula_evidence_missing', 0)}",
        "",
        "## Feedback Summary",
        f"- feedback count by type: {feedback_type_counts}",
        f"- feedback count by severity: {feedback_severity_counts}",
        f"- feedback status distribution: {feedback_status_counts}",
        f"- unresolved high severity issues: {len(unresolved_high)}",
        "",
        "## Evaluation Summary",
        f"- latest EvaluationRun: {getattr(latest_eval, 'id', None) if latest_eval else 'none'}",
        f"- extraction_precision: {getattr(latest_eval, 'extraction_precision', None) if latest_eval else 'n/a'}",
        f"- evidence_accuracy: {getattr(latest_eval, 'evidence_accuracy', None) if latest_eval else 'n/a'}",
        f"- alignment_accuracy: {getattr(latest_eval, 'alignment_accuracy', None) if latest_eval else 'n/a'}",
        f"- false_positive_rate: {getattr(latest_eval, 'false_positive_rate', None) if latest_eval else 'n/a'}",
        f"- no_evidence_forced_alignment_rate: {getattr(latest_eval, 'no_evidence_forced_alignment_rate', None) if latest_eval else 'n/a'}",
        "",
        "## Key Findings",
        "- Evidence-backed cards are useful when both English and Chinese sources exist.",
        "- Formula-related concepts still require configured Formula OCR for stronger evidence.",
        "- Feedback converted to evaluation items should drive the next regression set.",
        "",
        "## Backlog Generated",
        f"- P0 items: {backlog_priority_counts.get('P0', 0)}",
        f"- P1 items: {backlog_priority_counts.get('P1', 0)}",
        f"- P2 items: {backlog_priority_counts.get('P2', 0)}",
        f"- P3 items: {backlog_priority_counts.get('P3', 0)}",
        "",
        "## Next Iteration Plan",
        "- Review unresolved high-severity feedback.",
        "- Convert representative real feedback into EvaluationItems.",
        "- Add missing Chinese/English knowledge sources before re-running alignment.",
        "- Re-run smoke evaluation and compare no-evidence forced alignment rate.",
        "",
        "## Known Limitations",
        "- The report is a pilot summary, not production analytics.",
        "- Student identities are intentionally anonymized.",
        "- Personal document content and OCR full text are excluded.",
    ]
    return "\n".join(lines) + "\n"
