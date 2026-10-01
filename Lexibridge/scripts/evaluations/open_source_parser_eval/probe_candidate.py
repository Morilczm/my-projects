#!/usr/bin/env python3
"""Probe a third-party parser inside its isolated environment.

The output is intentionally reduced to the neutral evaluation schema. Raw parser
objects stay outside Git and are represented only by safe summaries.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
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


def run_command(command: list[str], *, timeout: int = 150) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": safe_text(completed.stdout),
            "stderr": safe_text(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": safe_text(getattr(exc, "stdout", "")),
            "stderr": "timeout",
        }


def page_count(path: Path) -> int:
    try:
        import fitz
        with fitz.open(path) as document:
            return len(document)
    except Exception:
        return 0


def block(block_id: str, block_type: str, text: str, *, page_number=None, bbox=None, order=None, table=None, formula_text="", formula_format="") -> dict[str, Any]:
    return {
        "block_id": block_id,
        "parent_block_id": "",
        "block_type": block_type,
        "text": safe_text(text),
        "bbox": bbox or {},
        "reading_order": order,
        "confidence": None,
        "language": "",
        "is_ocr": False,
        "table_structure": table,
        "formula_text": safe_text(formula_text),
        "formula_format": formula_format,
        "image_ref": "",
        "provenance": {},
    }


def flatten_text(value: Any) -> str:
    parts: list[str] = []
    seen = 0

    def walk(node: Any) -> None:
        nonlocal seen
        if seen > 2000:
            return
        seen += 1
        if isinstance(node, dict):
            for key in ("text", "orig", "content", "label", "name"):
                text = node.get(key)
                if isinstance(text, str) and text.strip():
                    parts.append(text)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, str):
            if len(node.strip()) > 2:
                parts.append(node)

    walk(value)
    return "\n".join(parts)


def run_docling(path: Path) -> dict[str, Any]:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(path))
    document = result.document
    exported: Any
    if hasattr(document, "export_to_dict"):
        exported = document.export_to_dict()
    else:
        exported = {"markdown": document.export_to_markdown()}
    text = flatten_text(exported)
    blocks = []
    paragraphs = [part.strip() for part in re.split(r"\n{2,}|\n", text) if part.strip()]
    for index, paragraph in enumerate(paragraphs[:80], start=1):
        lower = paragraph.casefold()
        block_type = "paragraph"
        if "|" in paragraph and paragraph.count("|") >= 2:
            block_type = "table"
        elif any(token in paragraph for token in ("=", "∫", "^", "_")) and len(paragraph) < 180:
            block_type = "formula"
        elif lower.startswith(("-", "•")):
            block_type = "list_item"
        blocks.append(block(f"docling-{index}", block_type, paragraph, order=index))
    return {
        "parser_version": package_version("docling"),
        "page_count": page_count(path),
        "blocks": blocks,
        "warnings": [],
        "errors": [],
        "raw_output_ref": "docling_export_dict_reduced",
    }


def run_paddle(path: Path) -> dict[str, Any]:
    import paddleocr

    version = package_version("paddleocr") or getattr(paddleocr, "__version__", "")
    pipeline_cls = getattr(paddleocr, "PPStructureV3", None) or getattr(paddleocr, "PPStructure", None)
    if pipeline_cls is None:
        return {
            "parser_version": version,
            "page_count": page_count(path),
            "blocks": [],
            "warnings": [],
            "errors": [{"code": "PADDLE_STRUCTURE_API_UNAVAILABLE", "message": "PPStructureV3/PPStructure class not importable"}],
            "raw_output_ref": "",
        }
    pipeline = pipeline_cls()
    output = pipeline.predict(str(path)) if hasattr(pipeline, "predict") else pipeline(str(path))
    text = flatten_text(output)
    blocks = [block(f"paddle-{index}", "paragraph", part, order=index) for index, part in enumerate(text.splitlines()[:80], start=1) if part.strip()]
    return {
        "parser_version": version,
        "page_count": page_count(path),
        "blocks": blocks,
        "warnings": [],
        "errors": [],
        "raw_output_ref": "paddle_structure_reduced",
    }


def run_mineru(path: Path) -> dict[str, Any]:
    version = package_version("mineru") or package_version("magic-pdf")
    scripts_dir = Path(sys.executable).resolve().parent
    executable_name = "mineru.exe" if sys.platform.startswith("win") else "mineru"
    env_mineru = scripts_dir / executable_name
    mineru = str(env_mineru) if env_mineru.exists() else shutil.which("mineru")
    if not mineru:
        return {
            "parser_version": version,
            "page_count": page_count(path),
            "blocks": [],
            "warnings": [],
            "errors": [{"code": "MINERU_CLI_NOT_FOUND", "message": "mineru console script not found"}],
            "raw_output_ref": "",
        }
    output_dir = path.parent / f"mineru-output-{path.stem}"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        mineru,
        "--path",
        str(path),
        "--output",
        str(output_dir),
        "--backend",
        "pipeline",
        "--method",
        "auto",
        "--formula",
        "true",
        "--table",
        "true",
    ]
    result = run_command(command, timeout=150)
    if not result["ok"]:
        return {
            "parser_version": version,
            "page_count": page_count(path),
            "blocks": [],
            "warnings": [],
            "errors": [{"code": "MINERU_EXECUTION_FAILED", "message": result.get("stderr") or result.get("stdout") or "mineru execution failed"}],
            "raw_output_ref": "",
        }
    text_parts: list[str] = []
    for candidate in sorted(output_dir.rglob("*.md"))[:4]:
        text_parts.append(candidate.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT])
    for candidate in sorted(output_dir.rglob("*.json"))[:4]:
        try:
            text_parts.append(flatten_text(json.loads(candidate.read_text(encoding="utf-8", errors="replace")))[:TEXT_LIMIT])
        except Exception:
            pass
    text = "\n".join(text_parts)
    if not text.strip():
        return {
            "parser_version": version,
            "page_count": page_count(path),
            "blocks": [],
            "warnings": ["mineru completed without readable markdown/json summary"],
            "errors": [],
            "raw_output_ref": "mineru_output_reduced_empty",
        }
    blocks = []
    for index, paragraph in enumerate([part.strip() for part in text.splitlines() if part.strip()][:80], start=1):
        block_type = "paragraph"
        if "|" in paragraph and paragraph.count("|") >= 2:
            block_type = "table"
        elif any(token in paragraph for token in ("=", "∫", "^", "_")) and len(paragraph) < 180:
            block_type = "formula"
        elif paragraph.startswith(("-", "•")):
            block_type = "list_item"
        blocks.append(block(f"mineru-{index}", block_type, paragraph, order=index))
    return {
        "parser_version": version,
        "page_count": page_count(path),
        "blocks": blocks,
        "warnings": [],
        "errors": [],
        "raw_output_ref": "mineru_markdown_json_reduced",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parser", required=True, choices=("docling", "paddle", "mineru"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    path = Path(args.input)
    started = time.perf_counter()
    try:
        if args.parser == "docling":
            payload = run_docling(path)
        elif args.parser == "paddle":
            payload = run_paddle(path)
        else:
            payload = run_mineru(path)
    except Exception as exc:
        payload = {
            "parser_version": package_version(args.parser),
            "page_count": page_count(path),
            "blocks": [],
            "warnings": [],
            "errors": [{"code": f"{args.parser.upper()}_EXECUTION_FAILED", "message": safe_text(exc)}],
            "raw_output_ref": "",
        }
    payload["parse_duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
