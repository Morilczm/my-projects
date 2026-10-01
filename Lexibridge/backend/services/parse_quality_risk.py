"""Map document parse quality states into downstream review risks."""

from __future__ import annotations

import json
from typing import Any


STATUS_RISK_LABELS = {
    "partial_text": ["input_partial_text"],
    "mixed_quality": ["input_mixed_quality"],
    "ocr_low_confidence": ["ocr_low_confidence"],
    "formula_detected": ["formula_context_risk"],
    "formula_ocr_required": ["formula_context_risk"],
    "formula_ocr_unavailable": ["formula_recognition_unavailable"],
}
FLAG_RISK_LABELS = {
    "partial_text": ["input_partial_text"],
    "mixed_quality": ["input_mixed_quality"],
    "ocr_low_confidence": ["ocr_low_confidence"],
    "formula_detected": ["formula_context_risk"],
    "formula_ocr_required": ["formula_context_risk"],
    "formula_ocr_unavailable": ["formula_recognition_unavailable"],
}
BLOCKED_QUALITY_STATUSES = {
    "empty_text",
    "ocr_required",
    "ocr_unavailable",
    "parse_failed",
    "unsupported_file_type",
}
FORCE_REVIEW_RISK_LABELS = {
    "input_partial_text",
    "input_mixed_quality",
    "ocr_low_confidence",
    "formula_context_risk",
    "formula_recognition_unavailable",
}


def _loads_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [value]
        return parsed if isinstance(parsed, list) else []
    return []


def _status_from_record(parse_record: Any) -> str:
    if parse_record is None:
        return ""
    if isinstance(parse_record, dict):
        return str(parse_record.get("parse_quality_status") or parse_record.get("quality_status") or "").strip()
    return str(getattr(parse_record, "parse_quality_status", "") or getattr(parse_record, "quality_status", "") or "").strip()


def _flags_from_record(parse_record: Any) -> list[str]:
    if parse_record is None:
        return []
    if isinstance(parse_record, dict):
        value = parse_record.get("parse_quality_flags", parse_record.get("quality_flags", []))
    else:
        value = getattr(parse_record, "parse_quality_flags", None)
        if value is None:
            value = getattr(parse_record, "quality_flags", [])
    return normalize_labels(_loads_list(value))


def normalize_labels(labels: Any) -> list[str]:
    normalized = []
    seen = set()
    for label in _loads_list(labels):
        text = str(label or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def merge_risk_labels(existing_labels: Any, new_labels: Any) -> list[str]:
    return normalize_labels([*normalize_labels(existing_labels), *normalize_labels(new_labels)])


def parse_quality_to_risk_labels(parse_record: Any) -> list[str]:
    status = _status_from_record(parse_record)
    labels = []
    labels.extend(STATUS_RISK_LABELS.get(status, []))
    for flag in _flags_from_record(parse_record):
        labels.extend(FLAG_RISK_LABELS.get(flag, []))
    return normalize_labels(labels)


def parse_quality_to_review_status(parse_record: Any) -> str:
    status = _status_from_record(parse_record)
    if status in BLOCKED_QUALITY_STATUSES:
        return "blocked"
    if should_force_needs_review(parse_record):
        return "needs_review"
    return ""


def should_force_needs_review(parse_record: Any) -> bool:
    labels = set(parse_quality_to_risk_labels(parse_record))
    return bool(labels & FORCE_REVIEW_RISK_LABELS)


def should_block_downstream_creation(parse_record: Any) -> bool:
    return _status_from_record(parse_record) in BLOCKED_QUALITY_STATUSES


def build_parse_quality_metadata(parse_record: Any, block: Any = None) -> dict[str, Any]:
    block_uid = ""
    block_flags = []
    if block is not None:
        if isinstance(block, dict):
            block_uid = str(block.get("parse_block_uid") or block.get("block_uid") or "").strip()
            block_flags = _loads_list(block.get("quality_flags", []))
        else:
            block_uid = str(getattr(block, "parse_block_uid", "") or getattr(block, "block_uid", "") or "").strip()
            block_flags = _loads_list(getattr(block, "quality_flags", []))
    flags = merge_risk_labels(_flags_from_record(parse_record), block_flags)
    metadata = {
        "parse_uid": "",
        "parse_block_uid": block_uid,
        "parse_quality_status": _status_from_record(parse_record),
        "parse_quality_flags": flags,
    }
    if isinstance(parse_record, dict):
        metadata["parse_uid"] = str(parse_record.get("parse_uid", "") or "").strip()
        metadata["parse_block_uid"] = metadata["parse_block_uid"] or str(parse_record.get("parse_block_uid", "") or "").strip()
    elif parse_record is not None:
        metadata["parse_uid"] = str(getattr(parse_record, "parse_uid", "") or "").strip()
        metadata["parse_block_uid"] = metadata["parse_block_uid"] or str(getattr(parse_record, "parse_block_uid", "") or "").strip()
    metadata["input_risk_labels"] = parse_quality_to_risk_labels(metadata)
    return metadata
