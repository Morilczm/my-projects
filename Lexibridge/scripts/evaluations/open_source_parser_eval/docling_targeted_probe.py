#!/usr/bin/env python3
"""Run a reduced Docling parse inside the isolated Docling environment."""

from __future__ import annotations

import argparse
import json
import re
import resource
import socket
import sys
import time
from pathlib import Path
from typing import Any


TEXT_LIMIT = 1200
LOCAL_PATH_RE = re.compile(r"(/Users/[^\s\"']+|/private/tmp/[^\s\"']+|file://[^\s\"']+)", re.IGNORECASE)
SECRET_RE = re.compile(r"(Authorization:|Cookie:|Bearer\s+|sk-[A-Za-z0-9_-]+)", re.IGNORECASE)


def safe_text(value: Any) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = LOCAL_PATH_RE.sub("<LOCAL_PRIVATE_PATH>", text)
    text = SECRET_RE.sub("[REDACTED]", text)
    return text[:TEXT_LIMIT]


def package_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return ""


def page_count(path: Path) -> int:
    try:
        import fitz

        with fitz.open(path) as document:
            return len(document)
    except Exception:
        return 0


def peak_memory_kb() -> int:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(raw / 1024)
    return int(raw)


class NetworkBlocker:
    def __init__(self) -> None:
        self.hosts: list[str] = []
        self._socket_connect = socket.socket.connect
        self._create_connection = socket.create_connection

    def __enter__(self) -> "NetworkBlocker":
        def guarded_socket_connect(sock, address):
            host = str(address[0]).casefold() if isinstance(address, tuple) and address else ""
            if host not in {"127.0.0.1", "localhost", "::1"}:
                self.hosts.append(host)
                raise AssertionError(f"network blocked: {host}")
            return self._socket_connect(sock, address)

        def guarded_create_connection(address, *args, **kwargs):
            host = str(address[0]).casefold() if isinstance(address, tuple) and address else ""
            if host not in {"127.0.0.1", "localhost", "::1"}:
                self.hosts.append(host)
                raise AssertionError(f"network blocked: {host}")
            return self._create_connection(address, *args, **kwargs)

        socket.socket.connect = guarded_socket_connect
        socket.create_connection = guarded_create_connection
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        socket.socket.connect = self._socket_connect
        socket.create_connection = self._create_connection


def bbox_dict(value: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if isinstance(value, dict):
        raw = value
    elif hasattr(value, "model_dump"):
        try:
            raw = value.model_dump()
        except Exception:
            raw = {}
    elif hasattr(value, "dict"):
        try:
            raw = value.dict()
        except Exception:
            raw = {}
    if not raw:
        return {}
    converted: dict[str, Any] = {}
    for key in ("l", "t", "r", "b", "left", "top", "right", "bottom", "width", "height", "coord_origin"):
        if key in raw:
            converted[key] = raw[key]
    if {"l", "r"} <= converted.keys():
        try:
            converted["width"] = abs(float(converted["r"]) - float(converted["l"]))
        except Exception:
            pass
    if {"t", "b"} <= converted.keys():
        try:
            converted["height"] = abs(float(converted["t"]) - float(converted["b"]))
        except Exception:
            pass
    return converted


def first_provenance(node: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
    prov = node.get("prov")
    if not isinstance(prov, list) or not prov:
        return None, {}
    first = prov[0]
    if not isinstance(first, dict):
        return None, {}
    page_number = first.get("page_no") or first.get("page_number")
    try:
        page_number = int(page_number) if page_number is not None else None
    except Exception:
        page_number = None
    return page_number, bbox_dict(first.get("bbox"))


def normalize_label(label: Any) -> str:
    lowered = str(label or "").casefold()
    if lowered in {"title"}:
        return "title"
    if lowered in {"section_header", "heading", "header"}:
        return "heading"
    if lowered in {"list_item"}:
        return "list_item"
    if lowered in {"table"}:
        return "table"
    if "formula" in lowered or lowered in {"equation"}:
        return "formula"
    if lowered in {"picture", "figure", "image"}:
        return "image"
    if lowered in {"caption"}:
        return "caption"
    if lowered in {"page_header"}:
        return "header"
    if lowered in {"page_footer"}:
        return "footer"
    if lowered in {"text", "paragraph"}:
        return "paragraph"
    return "unknown"


def extract_table_structure(node: dict[str, Any]) -> dict[str, Any] | None:
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
            texts.append(safe_text(text)[:160])
        for key in ("row_span", "end_row_offset_idx", "row_header"):
            _ = cell.get(key)
        row = cell.get("start_row_offset_idx", cell.get("row", cell.get("row_idx")))
        col = cell.get("start_col_offset_idx", cell.get("col", cell.get("col_idx")))
        try:
            rows = max(rows, int(row) + 1)
        except Exception:
            pass
        try:
            cols = max(cols, int(col) + 1)
        except Exception:
            pass
    if not rows and not cols and not texts:
        return None
    return {"rows": rows, "cols": cols, "cell_text_preview": texts[:12]}


def walk_docling_export(exported: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add_node(node: dict[str, Any], label_hint: str = "") -> None:
        text = node.get("text") or node.get("orig") or ""
        label = node.get("label") or label_hint
        block_type = normalize_label(label)
        page_number, bbox = first_provenance(node)
        table = extract_table_structure(node) if block_type == "table" else None
        if block_type == "table" and not text and table:
            text = " | ".join(table.get("cell_text_preview") or [])
        if not text and block_type not in {"table", "image", "formula"}:
            return
        if str(text).strip() in {"_root_", "list"} and not bbox:
            return
        blocks.append(
            {
                "block_id": str(node.get("self_ref") or f"docling-{len(blocks) + 1}"),
                "parent_block_id": str((node.get("parent") or {}).get("$ref") or ""),
                "block_type": block_type,
                "text": safe_text(text),
                "bbox": bbox,
                "page_number": page_number,
                "reading_order": len(blocks) + 1,
                "confidence": None,
                "language": "",
                "is_ocr": bool(node.get("is_ocr", False)),
                "table_structure": table,
                "formula_text": safe_text(text) if block_type == "formula" else "",
                "formula_format": "docling" if block_type == "formula" and text else "",
                "image_ref": "",
                "provenance": {
                    "docling_label": str(label or ""),
                    "has_page_ref": page_number is not None,
                    "has_bbox": bool(bbox),
                },
            }
        )

    def walk(node: Any, key_hint: str = "") -> None:
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)
        if isinstance(node, dict):
            if any(key in node for key in ("text", "orig", "prov", "label", "data")):
                add_node(node, key_hint)
            for key, child in node.items():
                walk(child, str(key))
        elif isinstance(node, list):
            for child in node:
                walk(child, key_hint)

    walk(exported)
    return blocks


def convert(path: Path) -> dict[str, Any]:
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat

    options = PdfPipelineOptions()
    options.do_ocr = True
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    started = time.perf_counter()
    before = peak_memory_kb()
    result = converter.convert(str(path))
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    after = peak_memory_kb()
    document = result.document
    exported: Any
    if hasattr(document, "export_to_dict"):
        exported = document.export_to_dict()
    else:
        exported = {"markdown": document.export_to_markdown()}
    blocks = walk_docling_export(exported)
    inferred_page_count = max((int(block.get("page_number") or 0) for block in blocks), default=0)
    return {
        "status": "succeeded",
        "parser_version": package_version("docling"),
        "page_count": page_count(path) or inferred_page_count,
        "blocks": blocks,
        "parse_duration_ms": duration_ms,
        "peak_rss_kb": max(before, after),
        "warnings": [],
        "errors": [],
        "raw_output_ref": "docling_export_dict_reduced",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--block-network", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.input)
    network = NetworkBlocker() if args.block_network else None
    blocker: NetworkBlocker | None = None
    try:
        if network:
            blocker = network.__enter__()
        payload = convert(path)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "failed",
            "parser_version": package_version("docling"),
            "page_count": page_count(path),
            "blocks": [],
            "parse_duration_ms": 0,
            "peak_rss_kb": peak_memory_kb(),
            "warnings": [],
            "errors": [{"code": "DOCLING_PARSE_FAILED", "message": safe_text(f"{type(exc).__name__}: {exc}")}],
            "raw_output_ref": "",
        }
    finally:
        if network:
            network.__exit__(None, None, None)
    payload["network"] = {
        "external_request_count": len(blocker.hosts) if blocker else 0,
        "hosts": sorted(set(blocker.hosts)) if blocker else [],
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
