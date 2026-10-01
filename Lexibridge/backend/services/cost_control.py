"""Local MVP usage and cost-control helpers.

The project intentionally reuses the existing UsageRecord table. These helpers
keep estimated cost and quota logic separate from feature code so the pricing
model can be replaced before production.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime


EVENT_COST_ESTIMATES = {
    "document_parse_page": 0.001,
    "ocr_page": 0.01,
    "formula_ocr_call": 0.02,
    "ai_term_extraction_call": 0.005,
    "ai_alignment_call": 0.01,
    "knowledge_search": 0.0005,
    "evaluation_item": 0.002,
    "pdf_export": 0.003,
}

PAGE_EVENTS = {"document_parse_page", "ocr_page"}
AI_EVENTS = {"ai_term_extraction_call", "ai_alignment_call", "knowledge_search"}
FORMULA_EVENTS = {"formula_ocr_call"}
EXPORT_EVENTS = {"pdf_export"}
EVALUATION_EVENTS = {"evaluation_item"}


@dataclass
class QuotaResult:
    allowed: bool
    error_code: str
    message: str
    totals: dict


def estimated_cost_for(event_type, units=1):
    return round(EVENT_COST_ESTIMATES.get(event_type, 0) * max(1, int(units or 1)), 6)


def record_usage_event(
    db_session,
    UsageRecordModel,
    user_id,
    event_type,
    units=1,
    provider="local",
    course_id=None,
    document_id=None,
    job_id=None,
    metadata=None,
):
    metadata = dict(metadata or {})
    metadata.update({
        "provider": provider,
        "course_id": course_id,
        "job_id": job_id,
        "estimated_cost": estimated_cost_for(event_type, units),
    })
    record = UsageRecordModel(
        user_id=user_id,
        action_type=event_type,
        units_used=max(1, int(units or 1)),
        related_document_id=document_id,
        related_term_id=None,
        created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    )
    # UsageRecord does not yet have metadata columns in the Local MVP, so the
    # metadata is returned to callers and can be promoted to a table later.
    db_session.add(record)
    db_session.flush()
    return {
        "record_id": record.id,
        "event_type": event_type,
        "units": record.units_used,
        "provider": provider,
        "estimated_cost": metadata["estimated_cost"],
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }


def summarize_usage(records):
    totals = {
        "document_parse_pages": 0,
        "ocr_pages": 0,
        "formula_ocr_calls": 0,
        "ai_calls": 0,
        "knowledge_searches": 0,
        "evaluation_items": 0,
        "pdf_exports": 0,
        "estimated_cost": 0.0,
    }
    for record in records:
        event_type = getattr(record, "action_type", "")
        units = int(getattr(record, "units_used", 0) or 0)
        if event_type == "document_parse_page":
            totals["document_parse_pages"] += units
        elif event_type == "ocr_page":
            totals["ocr_pages"] += units
        elif event_type in FORMULA_EVENTS:
            totals["formula_ocr_calls"] += units
        elif event_type in {"ai_alignment", "ai_term_extract"}:
            totals["ai_calls"] += units
        elif event_type in AI_EVENTS:
            totals["ai_calls"] += units
            if event_type == "knowledge_search":
                totals["knowledge_searches"] += units
        elif event_type in EVALUATION_EVENTS:
            totals["evaluation_items"] += units
        elif event_type in EXPORT_EVENTS:
            totals["pdf_exports"] += units
        totals["estimated_cost"] += estimated_cost_for(event_type, units)
    totals["estimated_cost"] = round(totals["estimated_cost"], 6)
    return totals


def check_quota(records, limits, event_type, units=1):
    totals = summarize_usage(records)
    units = max(1, int(units or 1))
    limits = dict(limits or {})
    if event_type in PAGE_EVENTS:
        limit = limits.get("monthly_pages")
        used = totals["document_parse_pages"] + totals["ocr_pages"]
        label = "monthly page quota"
    elif event_type in AI_EVENTS:
        limit = limits.get("monthly_ai_calls")
        used = totals["ai_calls"]
        label = "monthly AI/search quota"
    elif event_type in FORMULA_EVENTS:
        limit = limits.get("monthly_formula_ocr_calls")
        used = totals["formula_ocr_calls"]
        label = "monthly formula OCR quota"
    elif event_type in EXPORT_EVENTS:
        limit = limits.get("monthly_exports")
        used = totals["pdf_exports"]
        label = "monthly export quota"
    else:
        limit = None
        used = 0
        label = "quota"
    if limit is not None and used + units > int(limit):
        return QuotaResult(False, "QUOTA_EXCEEDED", f"{label} exceeded: {used}/{limit}", totals)
    return QuotaResult(True, "", "allowed", totals)
