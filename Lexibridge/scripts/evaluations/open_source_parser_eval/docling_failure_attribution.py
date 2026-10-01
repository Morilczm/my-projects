"""Evaluation-only Docling attribution and canonical normalization helpers.

This module is intentionally kept out of the production parser path.  It reads
Docling 2.117.0 export dictionaries for Task 10C.P2.5F diagnostics and keeps
source labels/provenance visible so parser limitations are not hidden by the
evaluation layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


ATTRIBUTIONS = {
    "FIXTURE_OR_GOLD_DEFECT",
    "PDF_BACKEND_DEFECT",
    "DOCLING_LAYOUT_DEFECT",
    "DOCLING_READING_ORDER_DEFECT",
    "DOCLING_ASSEMBLY_DEFECT",
    "LEXIBRIDGE_EXTRACTOR_DEFECT",
    "LEXIBRIDGE_NORMALIZATION_DEFECT",
    "COMPOSITE_FORMULA_ROUTE_REQUIRED",
    "UNRESOLVED_WITH_EVIDENCE",
}
LAYERS = {"L0", "L1", "L2", "L3"}
DECISION_STATUSES = {
    "DOCLING_EVALUATION_NORMALIZATION_VALIDATED",
    "DOCLING_MODEL_LIMITATIONS_CONFIRMED",
    "DOCLING_PARTIAL_CAPABILITY_ATTRIBUTED",
}

BODY_ROOT = "#/body"
FURNITURE_ROOT = "#/furniture"
TOP_LEFT = "TOP_LEFT"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class CanonicalBBox:
    page_number: int | None
    left: float
    top: float
    right: float
    bottom: float
    width: float
    height: float
    origin: str = TOP_LEFT
    source_origin: str = UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalProvenance:
    page_number: int | None
    bbox: CanonicalBBox | None
    source_bbox: dict[str, Any]
    source_origin: str
    source_item_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "source_bbox": dict(self.source_bbox),
            "source_origin": self.source_origin,
            "source_item_ref": self.source_item_ref,
        }


@dataclass(frozen=True)
class CanonicalBlock:
    block_id: str
    page_number: int | None
    block_type: str
    original_block_type: str
    text: str
    bbox: CanonicalBBox | None
    bbox_origin: str
    bbox_is_derived: bool
    reading_order: int
    parent_id: str
    children_ids: tuple[str, ...]
    source_parser: str
    source_item_ref: str
    provenance: tuple[CanonicalProvenance, ...] = field(default_factory=tuple)
    confidence: float | None = None
    table_structure: dict[str, Any] | None = None
    formula_route: dict[str, Any] = field(default_factory=dict)
    section: str = "body"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = self.bbox.to_dict() if self.bbox else None
        payload["provenance"] = [item.to_dict() for item in self.provenance]
        return payload


@dataclass(frozen=True)
class CanonicalDocument:
    blocks: tuple[CanonicalBlock, ...]
    source_parser: str
    page_dimensions: dict[int, dict[str, float]]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def body_blocks(self) -> list[CanonicalBlock]:
        return [block for block in self.blocks if block.section == "body"]

    def furniture_blocks(self) -> list[CanonicalBlock]:
        return [block for block in self.blocks if block.section == "furniture"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_parser": self.source_parser,
            "page_dimensions": self.page_dimensions,
            "diagnostics": self.diagnostics,
            "blocks": [block.to_dict() for block in self.blocks],
        }


def canonicalize_docling_export(exported: dict[str, Any], *, formula_regions: list[dict[str, Any]] | None = None) -> CanonicalDocument:
    ref_map = _build_ref_map(exported)
    page_dimensions = _extract_page_dimensions(exported)
    blocks: list[CanonicalBlock] = []
    seen: set[str] = set()

    for section, root_ref in (("body", BODY_ROOT), ("furniture", FURNITURE_ROOT)):
        root = ref_map.get(root_ref) or exported.get(section)
        if not isinstance(root, dict):
            continue
        for ref in _child_refs(root):
            _append_ref_block(
                ref,
                section=section,
                ref_map=ref_map,
                page_dimensions=page_dimensions,
                seen=seen,
                blocks=blocks,
            )

    blocks = _compose_formula_regions(blocks, formula_regions or [], page_dimensions)
    ordered = tuple(_renumber(blocks))
    return CanonicalDocument(
        blocks=ordered,
        source_parser="docling",
        page_dimensions=page_dimensions,
        diagnostics={
            "body_ref_count": len(_child_refs(ref_map.get(BODY_ROOT) or exported.get("body") or {})),
            "furniture_ref_count": len(_child_refs(ref_map.get(FURNITURE_ROOT) or exported.get("furniture") or {})),
            "ref_count": len(ref_map),
            "formula_region_count": len(formula_regions or []),
        },
    )


def visual_content_bbox_completeness(blocks: list[CanonicalBlock]) -> float:
    visual = [block for block in blocks if _requires_visual_bbox(block)]
    if not visual:
        return 0.0
    present = sum(1 for block in visual if block.bbox and block.bbox.width > 0 and block.bbox.height > 0)
    return round(present / len(visual), 4)


def failure_entry(*, attribution: str, first_incorrect_layer: str, evidence_refs: list[str], repairable: bool) -> dict[str, Any]:
    return {
        "attribution": attribution,
        "first_incorrect_layer": first_incorrect_layer,
        "evidence_refs": list(evidence_refs),
        "repairable_in_evaluation_normalizer": bool(repairable),
    }


def build_attribution_report(
    *,
    fixtures: list[dict[str, Any]],
    failures: dict[str, dict[str, Any]],
    decision_status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "task": "10C.P2.5F",
        "schema_version": "10C.P2.5F-attribution-v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "docling_version": "2.117.0",
        "baseline_commit": "01bddaa47b5e8d84feb929e7445b24d2f02b8f18",
        "fixtures": fixtures,
        "failures": failures,
        "decision": {"status": decision_status, "reason": reason},
    }


def validate_attribution_report(report: dict[str, Any]) -> None:
    if report.get("decision", {}).get("status") not in DECISION_STATUSES:
        raise ValueError("invalid decision status")
    failures = report.get("failures")
    if not isinstance(failures, dict) or not failures:
        raise ValueError("attribution report requires failures")
    for name, failure in failures.items():
        if failure.get("attribution") not in ATTRIBUTIONS:
            raise ValueError(f"invalid attribution for {name}")
        if failure.get("first_incorrect_layer") not in LAYERS:
            raise ValueError(f"invalid first incorrect layer for {name}")
        evidence_refs = failure.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(item, str) and item for item in evidence_refs):
            raise ValueError(f"missing evidence refs for {name}")


def canonical_blocks_to_evaluation_blocks(document: CanonicalDocument, fixture_id: str, *, parser_id: str = "docling_canonical") -> list[dict[str, Any]]:
    blocks = []
    for block in document.body_blocks():
        bbox = block.bbox.to_dict() if block.bbox else {}
        blocks.append(
            {
                "parser_id": parser_id,
                "fixture_id": fixture_id,
                "block_id": block.block_id,
                "parent_block_id": block.parent_id,
                "block_type": block.block_type,
                "original_block_type": block.original_block_type,
                "text": block.text,
                "bbox": bbox or {},
                "page_number": block.page_number,
                "reading_order": block.reading_order,
                "confidence": block.confidence,
                "language": "",
                "is_ocr": False,
                "table_structure": block.table_structure,
                "formula_text": "",
                "formula_format": block.formula_route.get("recognizer_status", "") if block.block_type == "formula" else "",
                "image_ref": block.formula_route.get("formula_region_uid", ""),
                "provenance": {
                    "source_parser": block.source_parser,
                    "source_item_ref": block.source_item_ref,
                    "bbox_is_derived": block.bbox_is_derived,
                    "original_block_type": block.original_block_type,
                    "formula_route": block.formula_route,
                },
            }
        )
    return blocks


def _build_ref_map(value: Any) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    seen: set[int] = set()

    def walk(node: Any) -> None:
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)
        if isinstance(node, dict):
            ref = node.get("self_ref")
            if isinstance(ref, str) and ref:
                refs[ref] = node
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return refs


def _extract_page_dimensions(exported: dict[str, Any]) -> dict[int, dict[str, float]]:
    dimensions: dict[int, dict[str, float]] = {}
    pages = exported.get("pages")
    if not isinstance(pages, dict):
        return dimensions
    for key, page in pages.items():
        if not isinstance(page, dict):
            continue
        page_number = _to_int(page.get("page_no") or page.get("page_number") or key)
        size = page.get("size") if isinstance(page.get("size"), dict) else page.get("dimension") if isinstance(page.get("dimension"), dict) else page
        width = _to_float(size.get("width") or size.get("w")) if isinstance(size, dict) else None
        height = _to_float(size.get("height") or size.get("h")) if isinstance(size, dict) else None
        if page_number and width and height:
            dimensions[page_number] = {"width": width, "height": height}
    return dimensions


def _child_refs(node: dict[str, Any]) -> list[str]:
    children = node.get("children")
    if not isinstance(children, list):
        return []
    refs = []
    for child in children:
        if isinstance(child, dict):
            ref = child.get("$ref") or child.get("self_ref")
            if isinstance(ref, str) and ref:
                refs.append(ref)
    return refs


def _append_ref_block(
    ref: str,
    *,
    section: str,
    ref_map: dict[str, dict[str, Any]],
    page_dimensions: dict[int, dict[str, float]],
    seen: set[str],
    blocks: list[CanonicalBlock],
) -> None:
    if ref in seen:
        return
    seen.add(ref)
    node = ref_map.get(ref)
    if not isinstance(node, dict):
        return
    label = str(node.get("label") or "")
    block_type = _normalize_label(label)
    child_refs = tuple(_child_refs(node))
    text = _node_text(node, block_type)
    provenance = tuple(_extract_provenance(node, ref, page_dimensions))
    bbox, bbox_is_derived = _canonical_bbox(provenance)
    is_visual = _is_visual_content(block_type, text, provenance, node)
    if is_visual:
        blocks.append(
            CanonicalBlock(
                block_id=ref,
                page_number=provenance[0].page_number if provenance else None,
                block_type=block_type,
                original_block_type=block_type,
                text=text,
                bbox=bbox,
                bbox_origin=TOP_LEFT if bbox else "",
                bbox_is_derived=bbox_is_derived,
                reading_order=len(blocks) + 1,
                parent_id=str((node.get("parent") or {}).get("$ref") or ""),
                children_ids=child_refs,
                source_parser="docling",
                source_item_ref=ref,
                provenance=provenance,
                table_structure=_extract_table_structure(node) if block_type == "table" else None,
                section=section,
            )
        )
    for child_ref in child_refs:
        _append_ref_block(
            child_ref,
            section=section,
            ref_map=ref_map,
            page_dimensions=page_dimensions,
            seen=seen,
            blocks=blocks,
        )


def _normalize_label(label: Any) -> str:
    lowered = str(label or "").casefold()
    if lowered == "title":
        return "title"
    if lowered in {"section_header", "heading"}:
        return "heading"
    if lowered in {"page_header"}:
        return "header"
    if lowered in {"page_footer"}:
        return "footer"
    if lowered in {"list_item"}:
        return "list_item"
    if lowered == "table":
        return "table"
    if lowered in {"picture", "figure", "image"}:
        return "image"
    if "formula" in lowered or lowered == "equation":
        return "formula"
    if lowered == "caption":
        return "caption"
    if lowered in {"text", "paragraph"}:
        return "paragraph"
    if lowered in {"table_cell", "cell", "group", "list", "ordered_list", "unordered_list"}:
        return lowered
    return UNKNOWN


def _node_text(node: dict[str, Any], block_type: str) -> str:
    text = node.get("text") or node.get("orig") or ""
    if block_type == "table":
        table = _extract_table_structure(node)
        if table:
            text = " | ".join(table.get("cell_text_preview") or [])
    return " ".join(str(text or "").replace("\x00", " ").split())[:1200]


def _extract_table_structure(node: dict[str, Any]) -> dict[str, Any] | None:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    cells = data.get("table_cells") or data.get("cells") or []
    if not isinstance(cells, list):
        return None
    rows = 0
    cols = 0
    texts: list[str] = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        text = cell.get("text") or cell.get("orig")
        if isinstance(text, str) and text.strip():
            texts.append(" ".join(text.split())[:120])
        row = cell.get("start_row_offset_idx", cell.get("row", cell.get("row_idx")))
        col = cell.get("start_col_offset_idx", cell.get("col", cell.get("col_idx")))
        rows = max(rows, (_to_int(row) or 0) + 1)
        cols = max(cols, (_to_int(col) or 0) + 1)
    if not rows and not cols and not texts:
        return None
    return {"rows": rows, "cols": cols, "cell_text_preview": texts[:12]}


def _extract_provenance(node: dict[str, Any], ref: str, page_dimensions: dict[int, dict[str, float]]) -> list[CanonicalProvenance]:
    prov = node.get("prov")
    if not isinstance(prov, list):
        return []
    results: list[CanonicalProvenance] = []
    for item in prov:
        if not isinstance(item, dict):
            continue
        page_number = _to_int(item.get("page_no") or item.get("page_number"))
        source_bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
        source_origin = str(source_bbox.get("coord_origin") or item.get("coord_origin") or UNKNOWN)
        bbox = _bbox_from_source(source_bbox, page_number, source_origin, page_dimensions)
        results.append(
            CanonicalProvenance(
                page_number=page_number,
                bbox=bbox,
                source_bbox=dict(source_bbox),
                source_origin=source_origin,
                source_item_ref=ref,
            )
        )
    return results


def _bbox_from_source(
    source_bbox: dict[str, Any],
    page_number: int | None,
    source_origin: str,
    page_dimensions: dict[int, dict[str, float]],
) -> CanonicalBBox | None:
    if not source_bbox:
        return None
    left = _to_float(source_bbox.get("left", source_bbox.get("l")))
    right = _to_float(source_bbox.get("right", source_bbox.get("r")))
    top = _to_float(source_bbox.get("top", source_bbox.get("t")))
    bottom = _to_float(source_bbox.get("bottom", source_bbox.get("b")))
    width = _to_float(source_bbox.get("width"))
    height = _to_float(source_bbox.get("height"))
    if left is None and right is not None and width is not None:
        left = right - width
    if right is None and left is not None and width is not None:
        right = left + width
    if top is None and bottom is not None and height is not None:
        top = bottom - height
    if bottom is None and top is not None and height is not None:
        bottom = top + height
    if left is None or right is None or top is None or bottom is None:
        return None
    raw_top = min(top, bottom)
    raw_bottom = max(top, bottom)
    page_height = page_dimensions.get(page_number or 0, {}).get("height")
    if source_origin.upper().endswith("BOTTOMLEFT") and page_height:
        canonical_top = page_height - raw_bottom
        canonical_bottom = page_height - raw_top
    else:
        canonical_top = raw_top
        canonical_bottom = raw_bottom
    canonical_left = min(left, right)
    canonical_right = max(left, right)
    return CanonicalBBox(
        page_number=page_number,
        left=canonical_left,
        top=canonical_top,
        right=canonical_right,
        bottom=canonical_bottom,
        width=canonical_right - canonical_left,
        height=canonical_bottom - canonical_top,
        source_origin=source_origin,
    )


def _canonical_bbox(provenance: tuple[CanonicalProvenance, ...]) -> tuple[CanonicalBBox | None, bool]:
    boxes = [item.bbox for item in provenance if item.bbox and item.bbox.width > 0 and item.bbox.height > 0]
    if not boxes:
        return None, False
    if len(boxes) == 1:
        return boxes[0], False
    left = min(box.left for box in boxes)
    top = min(box.top for box in boxes)
    right = max(box.right for box in boxes)
    bottom = max(box.bottom for box in boxes)
    return (
        CanonicalBBox(
            page_number=boxes[0].page_number,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            width=right - left,
            height=bottom - top,
            source_origin="derived_union",
        ),
        True,
    )


def _is_visual_content(block_type: str, text: str, provenance: tuple[CanonicalProvenance, ...], node: dict[str, Any]) -> bool:
    if block_type in {"group", "list", "ordered_list", "unordered_list", "table_cell", "cell"}:
        return False
    if block_type in {"table", "image", "formula"}:
        return True
    if text:
        return True
    return bool(provenance and block_type not in {UNKNOWN})


def _requires_visual_bbox(block: CanonicalBlock) -> bool:
    return block.block_type in {"title", "heading", "paragraph", "list_item", "table", "image", "formula", "caption", "header", "footer", "code", "footnote", UNKNOWN}


def _compose_formula_regions(
    blocks: list[CanonicalBlock],
    formula_regions: list[dict[str, Any]],
    page_dimensions: dict[int, dict[str, float]],
) -> list[CanonicalBlock]:
    if not formula_regions:
        return blocks
    updated = list(blocks)
    matched_regions: set[str] = set()
    for index, block in enumerate(list(updated)):
        best_region: dict[str, Any] | None = None
        best_iou = 0.0
        for region in formula_regions:
            region_bbox = _formula_region_bbox(region, page_dimensions)
            if not region_bbox or not block.bbox or block.page_number != region_bbox.page_number:
                continue
            iou = _iou(block.bbox, region_bbox)
            if iou > best_iou:
                best_iou = iou
                best_region = region
        if best_region and best_iou >= 0.15 and block.block_type in {"image", "formula", "paragraph", UNKNOWN}:
            region_uid = str(best_region.get("formula_region_uid") or best_region.get("region_uid") or f"formula-region-{index + 1}")
            matched_regions.add(region_uid)
            route = {
                "routing": "docling_region_plus_formula_region_overlap",
                "formula_region_uid": region_uid,
                "overlap_iou": round(best_iou, 4),
                "recognizer_status": str(best_region.get("recognizer_status") or "FORMULA_RECOGNIZER_UNAVAILABLE"),
                "latex_candidate": "",
                "mathml_candidate": "",
            }
            updated[index] = _replace_block(block, block_type="formula", formula_route=route)
    for region in formula_regions:
        region_uid = str(region.get("formula_region_uid") or region.get("region_uid") or "")
        if region_uid in matched_regions:
            continue
        bbox = _formula_region_bbox(region, page_dimensions)
        if not bbox:
            continue
        route = {
            "routing": "formula_region_only",
            "formula_region_uid": region_uid,
            "overlap_iou": 0.0,
            "recognizer_status": str(region.get("recognizer_status") or "FORMULA_RECOGNIZER_UNAVAILABLE"),
            "latex_candidate": "",
            "mathml_candidate": "",
        }
        provenance = (
            CanonicalProvenance(
                page_number=bbox.page_number,
                bbox=bbox,
                source_bbox=dict(region.get("bounding_box") or {}),
                source_origin=TOP_LEFT,
                source_item_ref=region_uid,
            ),
        )
        updated.append(
            CanonicalBlock(
                block_id=region_uid or f"formula-region-{len(updated) + 1}",
                page_number=bbox.page_number,
                block_type="formula",
                original_block_type="formula_region",
                text="",
                bbox=bbox,
                bbox_origin=TOP_LEFT,
                bbox_is_derived=False,
                reading_order=len(updated) + 1,
                parent_id="",
                children_ids=(),
                source_parser="lexibridge_formula_region",
                source_item_ref=region_uid,
                provenance=provenance,
                confidence=_to_float(region.get("detection_confidence")),
                formula_route=route,
                section="body",
            )
        )
    return updated


def _formula_region_bbox(region: dict[str, Any], page_dimensions: dict[int, dict[str, float]]) -> CanonicalBBox | None:
    raw = region.get("bounding_box") if isinstance(region.get("bounding_box"), dict) else region.get("bbox")
    if not isinstance(raw, dict):
        return None
    page_number = _to_int(region.get("page_number") or region.get("page_no"))
    if ({"left", "top", "width", "height"} <= set(raw)) or ({"x", "y", "width", "height"} <= set(raw)):
        left = _to_float(raw.get("left", raw.get("x")))
        top = _to_float(raw.get("top", raw.get("y")))
        width = _to_float(raw.get("width"))
        height = _to_float(raw.get("height"))
        if left is None or top is None or width is None or height is None:
            return None
        return CanonicalBBox(
            page_number=page_number,
            left=left,
            top=top,
            right=left + width,
            bottom=top + height,
            width=width,
            height=height,
            source_origin=TOP_LEFT,
        )
    return _bbox_from_source(raw, page_number, str(raw.get("coord_origin") or TOP_LEFT), page_dimensions)


def _replace_block(block: CanonicalBlock, **changes: Any) -> CanonicalBlock:
    payload = asdict(block)
    payload["provenance"] = block.provenance
    payload["bbox"] = block.bbox
    payload.update(changes)
    return CanonicalBlock(**payload)


def _renumber(blocks: list[CanonicalBlock]) -> list[CanonicalBlock]:
    result = []
    for index, block in enumerate(blocks, start=1):
        result.append(_replace_block(block, reading_order=index))
    return result


def _iou(left_box: CanonicalBBox, right_box: CanonicalBBox) -> float:
    x1 = max(left_box.left, right_box.left)
    y1 = max(left_box.top, right_box.top)
    x2 = min(left_box.right, right_box.right)
    y2 = min(left_box.bottom, right_box.bottom)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    left_area = left_box.width * left_box.height
    right_area = right_box.width * right_box.height
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


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
