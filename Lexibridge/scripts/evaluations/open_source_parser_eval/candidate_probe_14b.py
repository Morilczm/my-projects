#!/usr/bin/env python3
"""Process-isolated parser probe for the Task 14B controlled benchmark."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.open_source_parser_eval import controlled_benchmark_14b as benchmark  # noqa: E402


URL_RE = re.compile(r"https?://([^\s/:]+)(?::\d+)?", re.IGNORECASE)


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _peak_rss_mb(usage: resource.struct_rusage) -> float:
    value = float(usage.ru_maxrss or 0)
    # macOS reports bytes; Linux reports KiB.
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(value / divisor, 2)


def _network_metadata(log_text: str) -> dict[str, Any]:
    hosts = sorted(set(match.casefold() for match in URL_RE.findall(log_text or "")))
    external = [host for host in hosts if host not in {"127.0.0.1", "localhost", "::1"}]
    return {
        "observed_hosts": hosts,
        "external_hosts": external,
        "external_request_count": len(external),
    }


def _safe_error(value: Any) -> str:
    sanitized = benchmark.sanitize_artifact(str(value or ""))
    return str(sanitized)[-1200:]


def run_baseline(path: Path, fixture_id: str) -> dict[str, Any]:
    from scripts.evaluations.open_source_parser_eval import evaluate

    fixture = evaluate.ParserFixture(
        fixture_id=fixture_id,
        filename=path.name,
        path=path,
        privacy_classification="SYNTHETIC",
        domains=("controlled_benchmark",),
        expected_anchors=(),
    )
    result = evaluate.run_baseline_fixture(fixture)
    # The legacy evaluator stores a compact locator marker as bbox. Recover the
    # actual numeric coordinates for the common page:bbox:x0,y0,x1,y1 shape.
    for block in result.get("blocks") or []:
        locator = str((block.get("provenance") or {}).get("source_locator") or "")
        match = re.search(r"bbox:([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)", locator)
        if match:
            block["bbox"] = {
                "x0": float(match.group(1)),
                "y0": float(match.group(2)),
                "x1": float(match.group(3)),
                "y1": float(match.group(4)),
            }
        block.setdefault("provenance", {})["source_parser"] = "baseline_native_tesseract_formula_region"
        block["block_type"] = _baseline_block_type(block)
    result["peak_rss_mb"] = _peak_rss_mb(resource.getrusage(resource.RUSAGE_SELF))
    result["network"] = {"observed_hosts": [], "external_hosts": [], "external_request_count": 0}
    return result


def _baseline_block_type(block: dict[str, Any]) -> str:
    if str(block.get("block_type") or "") == "formula":
        return "formula"
    parser_type = str((block.get("provenance") or {}).get("parser_type") or "")
    # Production layout parse emits the original type in quality/locator only
    # in older records, so retain paragraph when no governed type exists.
    return "paragraph" if parser_type else str(block.get("block_type") or "paragraph")


def run_docling(path: Path, fixture_id: str, artifacts_path: Path) -> dict[str, Any]:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from scripts.evaluations.open_source_parser_eval import docling_failure_attribution

    options = PdfPipelineOptions(
        artifacts_path=artifacts_path,
        enable_remote_services=False,
        do_ocr=True,
        do_table_structure=True,
        do_formula_enrichment=True,
        do_picture_classification=False,
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    started = time.perf_counter()
    converted = converter.convert(str(path))
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    exported = converted.document.export_to_dict()
    canonical = docling_failure_attribution.canonicalize_docling_export(exported)
    blocks = docling_failure_attribution.canonical_blocks_to_evaluation_blocks(
        canonical, fixture_id, parser_id="docling"
    )
    return {
        "parser_id": "docling",
        "parser_version": _version("docling"),
        "fixture_id": fixture_id,
        "page_count": len(exported.get("pages") or {}),
        "blocks": blocks,
        "parse_duration_ms": duration_ms,
        "peak_rss_mb": _peak_rss_mb(resource.getrusage(resource.RUSAGE_SELF)),
        "warnings": [],
        "errors": [],
        "network": {"observed_hosts": [], "external_hosts": [], "external_request_count": 0},
    }


def _find_mineru_v2(output_root: Path) -> Path | None:
    candidates = sorted(output_root.rglob("*_content_list_v2.json"))
    return candidates[0] if candidates else None


def run_mineru(path: Path, fixture_id: str, runtime_root: Path) -> dict[str, Any]:
    mineru = shutil.which("mineru")
    if not mineru:
        raise RuntimeError("MINERU_CLI_NOT_FOUND")
    runtime_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mineru-14b-", dir=str(runtime_root)) as directory:
        output_root = Path(directory) / "output"
        command = [
            mineru,
            "--path",
            str(path),
            "--output",
            str(output_root),
            "--backend",
            "pipeline",
            "--method",
            "auto",
            "--formula",
            "true",
            "--table",
            "true",
        ]
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=240,
            env=os.environ.copy(),
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_text = f"{completed.stdout}\n{completed.stderr}"
        network = _network_metadata(log_text)
        if completed.returncode != 0:
            raise RuntimeError(f"MINERU_EXECUTION_FAILED: {_safe_error(log_text)}")
        content_path = _find_mineru_v2(output_root)
        if content_path is None:
            raise RuntimeError("MINERU_CONTENT_LIST_V2_MISSING")
        pages = json.loads(content_path.read_text(encoding="utf-8"))
        blocks = benchmark.normalize_mineru_content_list_v2(pages, fixture_id=fixture_id)
        return {
            "parser_id": "mineru",
            "parser_version": _version("mineru"),
            "fixture_id": fixture_id,
            "page_count": len(pages) if isinstance(pages, list) else 0,
            "blocks": blocks,
            "parse_duration_ms": duration_ms,
            "peak_rss_mb": max(
                _peak_rss_mb(resource.getrusage(resource.RUSAGE_SELF)),
                _peak_rss_mb(resource.getrusage(resource.RUSAGE_CHILDREN)),
            ),
            "warnings": [],
            "errors": [],
            "network": network,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parser", required=True, choices=benchmark.PARSER_IDS)
    parser.add_argument("--input", required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-root", default="")
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args(argv)
    path = Path(args.input)
    try:
        if args.parser == "baseline_native_tesseract_formula_region":
            payload = run_baseline(path, args.fixture_id)
        elif args.parser == "docling":
            if not args.model_root:
                raise RuntimeError("DOCLING_MODEL_ROOT_REQUIRED")
            payload = run_docling(path, args.fixture_id, Path(args.model_root))
        else:
            payload = run_mineru(path, args.fixture_id, Path(args.runtime_root))
    except Exception as exc:  # fail closed but keep the batch running
        payload = {
            "parser_id": args.parser,
            "parser_version": _version("mineru" if args.parser == "mineru" else args.parser),
            "fixture_id": args.fixture_id,
            "page_count": 0,
            "blocks": [],
            "parse_duration_ms": 0,
            "peak_rss_mb": max(
                _peak_rss_mb(resource.getrusage(resource.RUSAGE_SELF)),
                _peak_rss_mb(resource.getrusage(resource.RUSAGE_CHILDREN)),
            ),
            "warnings": [],
            "errors": [{"code": "PARSER_PROBE_FAILED", "message": _safe_error(f"{type(exc).__name__}: {exc}")}],
            "network": {"observed_hosts": [], "external_hosts": [], "external_request_count": 0},
        }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(benchmark.sanitize_artifact(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
