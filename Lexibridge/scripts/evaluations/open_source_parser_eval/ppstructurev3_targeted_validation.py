"""Evaluation-only PP-StructureV3 normalization and reporting helpers.

The helpers in this module intentionally do not import PaddleOCR or backend
application code. They normalize already-captured PP-StructureV3-like raw
blocks for Task 10C.P2.5G diagnostics and keep runtime-blocked evidence
explicit when the isolated PP-StructureV3 environment cannot initialize.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


STATUS_VALUES = {
    "PPSTRUCTUREV3_RUNTIME_BLOCKED",
    "PPSTRUCTUREV3_TARGETED_QUALITY_INSUFFICIENT",
    "PPSTRUCTUREV3_PARTIAL_CAPABILITY_VALIDATED",
    "PPSTRUCTUREV3_TARGETED_VALIDATION_PASSED",
}

VISUAL_BLOCK_TYPES = {
    "title",
    "heading",
    "paragraph",
    "list_item",
    "table",
    "image",
    "formula",
    "caption",
    "header",
    "footer",
    "unknown",
}


@dataclass(frozen=True)
class PPStructureBBox:
    left: float
    top: float
    right: float
    bottom: float
    width: float
    height: float
    origin: str = "TOP_LEFT"
    source_format: str = "xyxy"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PPStructureBlock:
    block_id: str
    source_index: int
    source_block_id: str
    block_type: str
    text: str
    page_number: int | None
    bbox: PPStructureBBox | None
    raw_label: str
    raw_order: int | None
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = self.bbox.to_dict() if self.bbox else None
        return payload


def normalize_ppstructure_blocks(raw_blocks: list[dict[str, Any]], *, page_width: float, page_height: float) -> list[PPStructureBlock]:
    blocks: list[PPStructureBlock] = []
    for index, raw in enumerate(raw_blocks):
        label = _safe_text(raw.get("block_label") or raw.get("label") or raw.get("type"))
        order = _to_int(raw.get("block_order", raw.get("order")))
        block_id = _safe_text(raw.get("block_id") or raw.get("id") or f"block-{index + 1}")
        page_number = _to_int(raw.get("page_number", raw.get("page_index")))
        if page_number is not None and raw.get("page_index") is not None and raw.get("page_number") is None:
            page_number += 1
        blocks.append(
            PPStructureBlock(
                block_id=block_id,
                source_index=index,
                source_block_id=block_id,
                block_type=_normalize_label(label),
                text=_safe_text(raw.get("block_content") or raw.get("text") or raw.get("content")),
                page_number=page_number,
                bbox=_parse_bbox(raw.get("block_bbox") or raw.get("bbox"), page_width=page_width, page_height=page_height),
                raw_label=label,
                raw_order=order,
                confidence=_to_float(raw.get("confidence") or raw.get("score")),
            )
        )
    return sorted(blocks, key=lambda block: (block.raw_order is None, block.raw_order or block.source_index, block.source_index))


def reading_order_metrics(text: str, fixture: Any) -> dict[str, Any]:
    anchors = list(getattr(fixture, "expected_anchors", ()) or ())
    folded = text.casefold()
    positions = {anchor.text: folded.find(anchor.text.casefold()) for anchor in anchors}
    found = [anchor for anchor in anchors if positions[anchor.text] >= 0]
    observed = [anchor.text for anchor in sorted(found, key=lambda anchor: positions[anchor.text])]
    expected = [anchor.text for anchor in anchors]
    pair_total = 0
    pair_correct = 0
    for left_index, left_anchor in enumerate(anchors):
        for right_anchor in anchors[left_index + 1 :]:
            left_pos = positions[left_anchor.text]
            right_pos = positions[right_anchor.text]
            if left_pos < 0 or right_pos < 0:
                continue
            pair_total += 1
            if left_pos < right_pos:
                pair_correct += 1
    return {
        "anchor_recall": round(len(found) / len(anchors), 4) if anchors else None,
        "exact_anchor_order_match": observed == expected,
        "pairwise_ordering_accuracy": round(pair_correct / pair_total, 4) if pair_total else None,
        "pairwise_correct": pair_correct,
        "pairwise_total": pair_total,
        "observed_anchor_order": observed,
        "expected_anchor_order": expected,
        "missing_anchors": [anchor.text for anchor in anchors if positions[anchor.text] < 0],
        "column_switch_count": _column_switch_count(observed),
        "block_order_none_count": 0,
    }


def bbox_metrics(blocks: list[PPStructureBlock], *, page_width: float, page_height: float) -> dict[str, Any]:
    visual = [block for block in blocks if block.block_type in VISUAL_BLOCK_TYPES]
    present = [block for block in visual if block.bbox and block.bbox.width > 0 and block.bbox.height > 0]
    invalid = [
        block
        for block in present
        if block.bbox is None
        or block.bbox.left < 0
        or block.bbox.top < 0
        or block.bbox.right > page_width
        or block.bbox.bottom > page_height
    ]
    zero_area = [block for block in visual if block.bbox and (block.bbox.width <= 0 or block.bbox.height <= 0)]
    return {
        "visual_block_count": len(visual),
        "visual_bbox_completeness": round(len(present) / len(visual), 4) if visual else None,
        "missing_bbox_count": len(visual) - len(present),
        "invalid_bbox_count": len(invalid),
        "zero_area_bbox_count": len(zero_area),
        "coordinate_system": "TOP_LEFT",
        "page_width": page_width,
        "page_height": page_height,
    }


def build_runtime_blocked_report(
    *,
    baseline_commit: str,
    branch: str,
    environment: dict[str, Any],
    package_manifest: dict[str, str],
    runtime: dict[str, Any],
    database: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task": "10C.P2.5G",
        "schema_version": "10C.P2.5G-ppstructurev3-targeted-validation-v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PPSTRUCTUREV3_RUNTIME_BLOCKED",
        "baseline_commit": baseline_commit,
        "branch": branch,
        "environment": environment,
        "package_manifest": package_manifest,
        "runtime": runtime,
        "targeted_quality": {"fixtures_evaluated": [], "quality_evaluation_completed": False},
        "network": {
            "package_download_requests": "pypi_and_conda_only",
            "model_download_requests": 0,
            "external_document_api_requests": 0,
            "provider_requests": 0,
            "document_egress": 0,
            "offline_rerun_network_requests": 0,
        },
        "database": database,
        "production": {
            "production_parser_changed": False,
            "formal_workflow_changed": False,
            "candidate_governance_changed": False,
            "database_schema_changed": False,
        },
        "decision": {
            "selected_for_adapter_design": False,
            "reason": "PP-StructureV3 isolated runtime did not reach import/initialization because the local inference engine was unavailable.",
        },
    }


def validate_report(report: dict[str, Any]) -> None:
    if report.get("status") not in STATUS_VALUES:
        raise ValueError("invalid PP-StructureV3 validation status")
    if not report.get("baseline_commit"):
        raise ValueError("missing baseline commit")
    if report.get("production", {}).get("production_parser_changed") is not False:
        raise ValueError("production parser change is not allowed")
    network = report.get("network") or {}
    for key in ("external_document_api_requests", "provider_requests", "document_egress"):
        if network.get(key) != 0:
            raise ValueError(f"{key} must be zero")


def _parse_bbox(value: Any, *, page_width: float, page_height: float) -> PPStructureBBox | None:
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        left, top, right, bottom = (_to_float(item) for item in value[:4])
    elif isinstance(value, dict):
        left = _to_float(value.get("left", value.get("x", value.get("l"))))
        top = _to_float(value.get("top", value.get("y", value.get("t"))))
        width = _to_float(value.get("width"))
        height = _to_float(value.get("height"))
        right = _to_float(value.get("right", value.get("r")))
        bottom = _to_float(value.get("bottom", value.get("b")))
        if right is None and left is not None and width is not None:
            right = left + width
        if bottom is None and top is not None and height is not None:
            bottom = top + height
    else:
        return None
    if left is None or top is None or right is None or bottom is None:
        return None
    canonical_left = max(0.0, min(left, right))
    canonical_top = max(0.0, min(top, bottom))
    canonical_right = min(float(page_width), max(left, right))
    canonical_bottom = min(float(page_height), max(top, bottom))
    return PPStructureBBox(
        left=canonical_left,
        top=canonical_top,
        right=canonical_right,
        bottom=canonical_bottom,
        width=canonical_right - canonical_left,
        height=canonical_bottom - canonical_top,
    )


def _normalize_label(label: str) -> str:
    lowered = label.casefold()
    if lowered in {"title"}:
        return "title"
    if lowered in {"section_header", "heading", "header"}:
        return "heading"
    if lowered in {"text", "paragraph"}:
        return "paragraph"
    if lowered in {"list", "list_item"}:
        return "list_item"
    if "table" in lowered:
        return "table"
    if "formula" in lowered or "equation" in lowered:
        return "formula"
    if "image" in lowered or "picture" in lowered or "figure" in lowered:
        return "image"
    if "footer" in lowered:
        return "footer"
    if lowered in {"group", "logical_group"}:
        return "group"
    return "unknown"


def _column_switch_count(observed: list[str]) -> int:
    left_terms = {"fourier transform", "impulse response", "convolution", "transfer function"}
    right_terms = {"voltage divider", "operational amplifier", "equivalent resistance", "boundary condition"}
    columns = []
    for value in observed:
        folded = value.casefold()
        if folded in left_terms:
            columns.append("left")
        elif folded in right_terms:
            columns.append("right")
        else:
            columns.append("other")
    return sum(1 for index in range(1, len(columns)) if columns[index] != columns[index - 1])


def _safe_text(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None
