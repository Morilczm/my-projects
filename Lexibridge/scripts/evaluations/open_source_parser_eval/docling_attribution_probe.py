#!/usr/bin/env python3
"""Run a reduced Docling attribution probe inside the isolated Docling env."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.open_source_parser_eval import docling_failure_attribution as attribution
from scripts.evaluations.open_source_parser_eval.docling_targeted_probe import (
    NetworkBlocker,
    package_version,
    page_count,
    peak_memory_kb,
    safe_text,
)


def _safe_text(value: Any, limit: int = 1200) -> str:
    return safe_text(value)[:limit]


def convert(path: Path, formula_regions: list[dict[str, Any]]) -> dict[str, Any]:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = True
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    started = time.perf_counter()
    before = peak_memory_kb()
    result = converter.convert(str(path))
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    after = peak_memory_kb()
    document = result.document
    exported = document.export_to_dict() if hasattr(document, "export_to_dict") else {"markdown": document.export_to_markdown()}
    canonical = attribution.canonicalize_docling_export(exported, formula_regions=formula_regions)
    blocks = attribution.canonical_blocks_to_evaluation_blocks(canonical, path.stem, parser_id="docling")
    return {
        "status": "succeeded",
        "parser_version": package_version("docling"),
        "page_count": page_count(path) or _inferred_page_count(blocks),
        "parse_duration_ms": duration_ms,
        "peak_rss_kb": max(before, after),
        "warnings": [],
        "errors": [],
        "l2": _reduced_l2(exported),
        "l3": {
            "canonical": canonical.to_dict(),
            "evaluation_blocks": blocks,
        },
    }


def _inferred_page_count(blocks: list[dict[str, Any]]) -> int:
    return max((int(block.get("page_number") or 0) for block in blocks), default=0)


def _reduced_l2(exported: dict[str, Any]) -> dict[str, Any]:
    ref_map = _build_ref_map(exported)
    return {
        "available_fields": sorted(key for key in exported.keys() if key in {"body", "furniture", "texts", "tables", "pictures", "groups", "pages"}),
        "page_dimensions": _safe_pages(exported.get("pages")),
        "collections": {
            name: [_summarize_node(node) for node in exported.get(name, []) if isinstance(node, dict)]
            for name in ("texts", "tables", "pictures", "groups")
            if isinstance(exported.get(name), list)
        },
        "body_traversal": _traverse_tree(exported.get("body"), ref_map),
        "furniture_traversal": _traverse_tree(exported.get("furniture"), ref_map),
    }


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


def _traverse_tree(root: Any, ref_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(root, dict):
        return []
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk_ref(ref: str) -> None:
        if ref in seen:
            return
        seen.add(ref)
        node = ref_map.get(ref)
        if not isinstance(node, dict):
            return
        if _is_reportable(node):
            output.append(_summarize_node(node))
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    child_ref = child.get("$ref") or child.get("self_ref")
                    if isinstance(child_ref, str):
                        walk_ref(child_ref)

    children = root.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                ref = child.get("$ref") or child.get("self_ref")
                if isinstance(ref, str):
                    walk_ref(ref)
    return output


def _is_reportable(node: dict[str, Any]) -> bool:
    text = node.get("text") or node.get("orig") or ""
    return bool(text or node.get("prov") or node.get("label") in {"table", "picture", "formula"})


def _summarize_node(node: dict[str, Any]) -> dict[str, Any]:
    prov = node.get("prov") if isinstance(node.get("prov"), list) else []
    return {
        "self_ref": _safe_text(node.get("self_ref"), 160),
        "label": _safe_text(node.get("label"), 80),
        "text": _safe_text(node.get("text") or node.get("orig"), 240),
        "child_refs": [
            _safe_text(child.get("$ref") or child.get("self_ref"), 160)
            for child in node.get("children", [])
            if isinstance(child, dict)
        ],
        "prov": [_summarize_prov(item) for item in prov[:4] if isinstance(item, dict)],
        "table_shape": _table_shape(node),
    }


def _summarize_prov(item: dict[str, Any]) -> dict[str, Any]:
    bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
    return {
        "page_no": item.get("page_no") or item.get("page_number"),
        "bbox": {
            key: bbox.get(key)
            for key in ("l", "t", "r", "b", "left", "top", "right", "bottom", "width", "height", "coord_origin")
            if key in bbox
        },
    }


def _table_shape(node: dict[str, Any]) -> dict[str, Any] | None:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    cells = data.get("table_cells") or data.get("cells") or []
    if not isinstance(cells, list):
        return None
    rows = 0
    cols = 0
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        try:
            rows = max(rows, int(cell.get("start_row_offset_idx", 0)) + 1)
        except Exception:
            pass
        try:
            cols = max(cols, int(cell.get("start_col_offset_idx", 0)) + 1)
        except Exception:
            pass
    return {"rows": rows, "cols": cols, "cell_count": len(cells)}


def _safe_pages(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    pages: dict[str, Any] = {}
    for key, page in value.items():
        if not isinstance(page, dict):
            continue
        size = page.get("size") if isinstance(page.get("size"), dict) else page.get("dimension") if isinstance(page.get("dimension"), dict) else page
        pages[str(key)] = {
            "page_no": page.get("page_no") or page.get("page_number") or key,
            "width": size.get("width") or size.get("w") if isinstance(size, dict) else None,
            "height": size.get("height") or size.get("h") if isinstance(size, dict) else None,
        }
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--formula-regions-json", default="")
    parser.add_argument("--block-network", action="store_true")
    args = parser.parse_args(argv)
    formula_regions = []
    if args.formula_regions_json:
        formula_regions = json.loads(Path(args.formula_regions_json).read_text(encoding="utf-8"))
    blocker: NetworkBlocker | None = None
    try:
        if args.block_network:
            blocker = NetworkBlocker()
            blocker.__enter__()
        payload = convert(Path(args.input), formula_regions)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "failed",
            "parser_version": package_version("docling"),
            "page_count": page_count(Path(args.input)),
            "parse_duration_ms": 0,
            "peak_rss_kb": peak_memory_kb(),
            "warnings": [],
            "errors": [{"code": "DOCLING_ATTRIBUTION_PROBE_FAILED", "message": _safe_text(f"{type(exc).__name__}: {exc}")}],
            "l2": {},
            "l3": {"canonical": {}, "evaluation_blocks": []},
        }
    finally:
        if blocker:
            blocker.__exit__(None, None, None)
    payload["network"] = {
        "external_request_count": len(blocker.hosts) if blocker else 0,
        "hosts": sorted(set(blocker.hosts)) if blocker else [],
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
