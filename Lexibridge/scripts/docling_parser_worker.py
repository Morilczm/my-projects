#!/usr/bin/env python3
"""Offline Docling worker for the governed production parser adapter.

The worker writes only the bounded layout interchange contract requested by
the parent application.  It does not emit a Markdown export or persist source
content outside the parent-owned temporary directory.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import socket
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "docling-layout-worker@1.0.0"
TEXT_LIMIT = 20_000


class NetworkBlocker:
    def __init__(self) -> None:
        self.requests = 0
        self._connect = socket.socket.connect
        self._create = socket.create_connection

    def __enter__(self):
        def blocked_connect(sock, address):
            host = str(address[0]).casefold() if isinstance(address, tuple) and address else ""
            if host not in {"127.0.0.1", "localhost", "::1"}:
                self.requests += 1
                raise RuntimeError("EXTERNAL_NETWORK_BLOCKED")
            return self._connect(sock, address)

        def blocked_create(address, *args, **kwargs):
            host = str(address[0]).casefold() if isinstance(address, tuple) and address else ""
            if host not in {"127.0.0.1", "localhost", "::1"}:
                self.requests += 1
                raise RuntimeError("EXTERNAL_NETWORK_BLOCKED")
            return self._create(address, *args, **kwargs)

        socket.socket.connect = blocked_connect
        socket.create_connection = blocked_create
        return self

    def __exit__(self, exc_type, exc, traceback):
        socket.socket.connect = self._connect
        socket.create_connection = self._create


def _version() -> str:
    try:
        return importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        return ""


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ref_map(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    seen: set[int] = set()

    def walk(node: Any) -> None:
        identity = id(node)
        if identity in seen:
            return
        seen.add(identity)
        if isinstance(node, dict):
            reference = node.get("self_ref")
            if isinstance(reference, str) and reference:
                result[reference] = node
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return result


def _child_refs(node: dict[str, Any]) -> list[str]:
    result = []
    for child in node.get("children", []) if isinstance(node.get("children"), list) else []:
        if not isinstance(child, dict):
            continue
        reference = child.get("$ref") or child.get("self_ref")
        if isinstance(reference, str) and reference:
            result.append(reference)
    return result


def _page_dimensions(exported: dict[str, Any]) -> dict[int, tuple[float, float]]:
    result = {}
    pages = exported.get("pages") if isinstance(exported.get("pages"), dict) else {}
    for key, page in pages.items():
        if not isinstance(page, dict):
            continue
        number = _to_int(page.get("page_no") or page.get("page_number") or key)
        size = page.get("size") if isinstance(page.get("size"), dict) else page
        width = _to_float(size.get("width") or size.get("w"))
        height = _to_float(size.get("height") or size.get("h"))
        if number and width and height:
            result[number] = (width, height)
    return result


def _block_type(value: Any) -> str:
    label = str(value or "").casefold()
    if label in {"title", "section_header", "heading"}:
        return "title"
    if label in {"list_item"}:
        return "list"
    if label == "table":
        return "table"
    if label in {"picture", "figure", "image"}:
        return "figure"
    if "formula" in label or label == "equation":
        return "formula"
    if label == "caption":
        return "caption"
    if label in {"page_header", "page_footer"}:
        return "header_footer"
    return "text"


def _table_text(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    cells = data.get("table_cells") or data.get("cells") or []
    if not isinstance(cells, list):
        return ""
    values = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        value = " ".join(str(cell.get("text") or cell.get("orig") or "").split())
        if value:
            values.append(value[:240])
    return " | ".join(values)


def _text(node: dict[str, Any], block_type: str) -> str:
    value = _table_text(node) if block_type == "table" else ""
    value = value or str(node.get("text") or node.get("orig") or "")
    return " ".join(value.replace("\x00", " ").split())[:TEXT_LIMIT]


def _provenance(
    node: dict[str, Any], dimensions: dict[int, tuple[float, float]]
) -> tuple[int, dict[str, float], float, float] | None:
    provenance = node.get("prov")
    if not isinstance(provenance, list) or not provenance:
        return None
    item = provenance[0]
    if not isinstance(item, dict):
        return None
    page_number = _to_int(item.get("page_no") or item.get("page_number"))
    bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
    if not page_number or page_number not in dimensions or not bbox:
        return None
    page_width, page_height = dimensions[page_number]
    left = _to_float(bbox.get("left", bbox.get("l")))
    right = _to_float(bbox.get("right", bbox.get("r")))
    top = _to_float(bbox.get("top", bbox.get("t")))
    bottom = _to_float(bbox.get("bottom", bbox.get("b")))
    if None in {left, right, top, bottom}:
        return None
    raw_top = min(top, bottom)
    raw_bottom = max(top, bottom)
    origin = str(bbox.get("coord_origin") or item.get("coord_origin") or "").upper()
    if origin.endswith("BOTTOMLEFT"):
        y0 = page_height - raw_bottom
        y1 = page_height - raw_top
    else:
        y0, y1 = raw_top, raw_bottom
    return (
        page_number,
        {
            "x0": min(left, right),
            "y0": y0,
            "x1": max(left, right),
            "y1": y1,
        },
        page_width,
        page_height,
    )


def _layout_blocks(exported: dict[str, Any]) -> list[dict[str, Any]]:
    references = _ref_map(exported)
    dimensions = _page_dimensions(exported)
    root = references.get("#/body") or exported.get("body")
    if not isinstance(root, dict):
        return []
    result = []
    seen: set[str] = set()

    def append(reference: str) -> None:
        if reference in seen:
            return
        seen.add(reference)
        node = references.get(reference)
        if not isinstance(node, dict):
            return
        block_type = _block_type(node.get("label"))
        text = _text(node, block_type)
        provenance = _provenance(node, dimensions)
        if text and provenance:
            page_number, bbox, page_width, page_height = provenance
            result.append(
                {
                    "page_number": page_number,
                    "text": text,
                    "bbox": bbox,
                    "layout_type": block_type,
                    "reading_order": len(result) + 1,
                    "page_width": page_width,
                    "page_height": page_height,
                    "confidence": 1.0,
                }
            )
        for child in _child_refs(node):
            append(child)

    for child in _child_refs(root):
        append(child)
    return result


def _convert(path: Path, model_root: Path, max_pages: int) -> dict[str, Any]:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        artifacts_path=model_root,
        enable_remote_services=False,
        do_ocr=True,
        do_table_structure=True,
        do_formula_enrichment=False,
        do_picture_classification=False,
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    converted = converter.convert(str(path))
    exported = converted.document.export_to_dict()
    pages = exported.get("pages") if isinstance(exported.get("pages"), dict) else {}
    page_count = len(pages)
    if page_count <= 0 or page_count > max_pages:
        raise RuntimeError("DOCLING_PAGE_LIMIT_EXCEEDED")
    blocks = _layout_blocks(exported)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "ok" if blocks else "failed",
        "parser_version": _version(),
        "page_count": page_count,
        "blocks": blocks,
        "warnings": [],
        "error_code": "" if blocks else "DOCLING_EMPTY_OUTPUT",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--max-pages", type=int, required=True)
    parser.add_argument("--block-network", action="store_true")
    args = parser.parse_args(argv)
    blocker = NetworkBlocker()
    try:
        if args.block_network:
            blocker.__enter__()
        payload = _convert(
            Path(args.input), Path(args.model_root), max(1, min(args.max_pages, 200))
        )
    except Exception as exc:
        code = str(exc) if str(exc).startswith("DOCLING_") else "DOCLING_PARSE_FAILED"
        payload = {
            "contract_version": CONTRACT_VERSION,
            "status": "failed",
            "parser_version": _version(),
            "page_count": 0,
            "blocks": [],
            "warnings": [],
            "error_code": code,
        }
    finally:
        if args.block_network:
            blocker.__exit__(None, None, None)
    payload["external_request_count"] = blocker.requests
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
