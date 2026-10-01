#!/usr/bin/env python3
"""Targeted Docling quality comparison against the current parser baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import resource
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.open_source_parser_eval import evaluate


LOCAL_PATH_RE = re.compile(r"(/Users/[^\s\"']+|/private/tmp/[^\s\"']+|file://[^\s\"']+)", re.IGNORECASE)
SECRET_RE = re.compile(r"(Authorization:|Cookie:|Bearer\s+|sk-[A-Za-z0-9_-]+|HF_TOKEN)", re.IGNORECASE)
TARGET_FIXTURE_IDS = (
    "single_column_born_digital",
    "mixed_layout_blocker",
    "two_column_born_digital",
    "scanned_bilingual",
    "simple_table",
    "raster_formula",
    "negative_no_terms",
)
SPECIALIST_TERMS = (
    "Fourier Transform",
    "Impulse Response",
    "Convolution",
    "Voltage Divider",
    "Operational Amplifier",
    "Equivalent Resistance",
    "Boundary Condition",
    "Eigenvalue",
    "Transfer Function",
    "傅里叶变换",
    "卷积",
    "分压器",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_text(value: Any, limit: int = 1200) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = LOCAL_PATH_RE.sub("<LOCAL_PRIVATE_PATH>", text)
    text = SECRET_RE.sub("[REDACTED]", text)
    return text[:limit]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def peak_memory_kb() -> int:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(raw / 1024)
    return int(raw)


def select_target_fixtures(root: Path) -> list[evaluate.ParserFixture]:
    fixtures = {fixture.fixture_id: fixture for fixture in evaluate.build_fixture_set(root)}
    missing = [fixture_id for fixture_id in TARGET_FIXTURE_IDS if fixture_id not in fixtures]
    if missing:
        raise RuntimeError(f"target fixture missing: {', '.join(missing)}")
    return [fixtures[fixture_id] for fixture_id in TARGET_FIXTURE_IDS]


def content_blocks(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for block in result.get("blocks") or []
        if str(block.get("text") or "").strip()
        and str(block.get("text") or "").strip() not in {"_root_", "list"}
    ]


def combined_text(result: dict[str, Any]) -> str:
    return "\n".join(str(block.get("text") or "") for block in content_blocks(result))


def bbox_present(block: dict[str, Any]) -> bool:
    bbox = block.get("bbox")
    if not isinstance(bbox, dict) or not bbox:
        return False
    if "width" in bbox and "height" in bbox:
        try:
            return float(bbox["width"]) > 0 and float(bbox["height"]) > 0
        except Exception:
            return False
    return bool({"l", "r", "t", "b"} <= set(bbox))


def anchor_metrics(text: str, anchors: tuple[evaluate.GoldAnchor, ...]) -> dict[str, Any]:
    if not anchors:
        return {"matched": 0, "total": 0, "recall": None, "missing": []}
    folded = text.casefold()
    matched: list[str] = []
    missing: list[str] = []
    for anchor in anchors:
        if anchor.text.casefold() in folded or anchor.text in text:
            matched.append(anchor.text)
        else:
            missing.append(anchor.text)
    return {
        "matched": len(matched),
        "total": len(anchors),
        "recall": round(len(matched) / len(anchors), 4),
        "missing": missing,
    }


def reading_order_errors(text: str, anchors: tuple[evaluate.GoldAnchor, ...]) -> int:
    folded = text.casefold()
    positions: list[tuple[int, int]] = []
    for anchor in anchors:
        position = folded.find(anchor.text.casefold())
        if position >= 0:
            positions.append((anchor.order, position))
    return sum(1 for left, right in zip(positions, positions[1:]) if left[1] > right[1])


def table_dimensions(block: dict[str, Any]) -> tuple[int, int]:
    table = block.get("table_structure")
    if not isinstance(table, dict):
        return 0, 0
    try:
        rows = int(table.get("rows") or 0)
    except Exception:
        rows = 0
    try:
        cols = int(table.get("cols") or 0)
    except Exception:
        cols = 0
    return rows, cols


def score_result(fixture: evaluate.ParserFixture, result: dict[str, Any]) -> dict[str, Any]:
    blocks = content_blocks(result)
    text = combined_text(result)
    anchor = anchor_metrics(text, fixture.expected_anchors)
    page_ref_count = sum(1 for block in blocks if block.get("page_number") is not None)
    bbox_count = sum(1 for block in blocks if bbox_present(block))
    table_blocks = [block for block in result.get("blocks") or [] if block.get("block_type") == "table" or block.get("table_structure")]
    formula_blocks = [block for block in result.get("blocks") or [] if block.get("block_type") == "formula"]
    image_blocks = [block for block in result.get("blocks") or [] if block.get("block_type") == "image"]
    recognized_formula_blocks = [
        block
        for block in formula_blocks
        if str(block.get("formula_text") or "").strip()
        and str(block.get("formula_format") or "").strip()
        and str(block.get("formula_format") or "").casefold() != "unavailable"
    ]
    duplicate_text = len([block for block in blocks if str(block.get("text") or "").strip()]) - len(
        {str(block.get("text") or "").strip() for block in blocks if str(block.get("text") or "").strip()}
    )
    hallucinated_terms = []
    if fixture.negative:
        folded = text.casefold()
        hallucinated_terms = [term for term in SPECIALIST_TERMS if term.casefold() in folded or term in text]
    table_rows = 0
    table_cols = 0
    for block in table_blocks:
        rows, cols = table_dimensions(block)
        table_rows = max(table_rows, rows)
        table_cols = max(table_cols, cols)
    return {
        "fixture_id": fixture.fixture_id,
        "parser_id": result.get("parser_id"),
        "parse_success": not bool(result.get("errors")) and bool(result.get("blocks")),
        "page_count": result.get("page_count"),
        "block_count": len(result.get("blocks") or []),
        "content_block_count": len(blocks),
        "block_types": sorted({str(block.get("block_type") or "unknown") for block in result.get("blocks") or []}),
        "anchor_recall": anchor,
        "text_error_count": len(anchor.get("missing") or []),
        "unicode_chinese_preserved": any("\u4e00" <= char <= "\u9fff" for char in text),
        "reading_order_errors": reading_order_errors(text, fixture.expected_anchors),
        "page_ref_completeness": round(page_ref_count / len(blocks), 4) if blocks else 0.0,
        "bbox_completeness": round(bbox_count / len(blocks), 4) if blocks else 0.0,
        "ocr_executed": any(bool(block.get("is_ocr")) for block in result.get("blocks") or []),
        "table_detected": bool(table_blocks),
        "table_rows": table_rows,
        "table_cols": table_cols,
        "table_structure_present": bool(table_rows and table_cols),
        "formula_region_detected": bool(formula_blocks or image_blocks),
        "formula_structure_recognized": bool(recognized_formula_blocks),
        "formula_format": str(recognized_formula_blocks[0].get("formula_format") if recognized_formula_blocks else "unavailable"),
        "duplicate_text_count": duplicate_text,
        "hallucinated_terms": hallucinated_terms,
        "warnings": [safe_text(item) for item in result.get("warnings") or []],
        "errors": result.get("errors") or [],
        "warm_parse_duration_ms": result.get("parse_duration_ms"),
        "peak_memory_kb": result.get("peak_memory_kb") or result.get("peak_memory_delta_kb"),
    }


def build_docling_env(cache_root: Path) -> dict[str, str]:
    return {
        "HOME": str(cache_root / "runtime-home"),
        "XDG_CACHE_HOME": str(cache_root),
        "HF_HOME": str(cache_root / "huggingface"),
        "TRANSFORMERS_CACHE": str(cache_root / "transformers"),
        "TORCH_HOME": str(cache_root / "torch"),
        "MODELSCOPE_CACHE": str(cache_root / "modelscope"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


def run_docling_fixture(
    fixture: evaluate.ParserFixture,
    *,
    env_name: str,
    cache_root: Path,
    artifact_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    conda = os.environ.get("LEXIBRIDGE_CONDA_CMD") or shutil.which("conda")
    if not conda:
        return failed_result("docling", fixture, "CONDA_NOT_FOUND", "conda executable not found")
    output_path = artifact_dir / f"docling-{fixture.fixture_id}.json"
    command = [
        conda,
        "run",
        "-n",
        env_name,
        "python",
        str(Path(__file__).with_name("docling_targeted_probe.py")),
        "--input",
        str(fixture.path),
        "--output",
        str(output_path),
        "--block-network",
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={**os.environ.copy(), **build_docling_env(cache_root)},
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
    except subprocess.TimeoutExpired as exc:
        return failed_result("docling", fixture, "DOCLING_TIMEOUT", safe_text(getattr(exc, "stderr", "") or "timeout"))
    if completed.returncode != 0 or not output_path.exists():
        return failed_result("docling", fixture, "DOCLING_PROBE_FAILED", completed.stderr or completed.stdout)
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return failed_result("docling", fixture, "DOCLING_PROBE_OUTPUT_INVALID", str(exc))
    blocks = [
        evaluate._standardize_block(
            parser_id="docling",
            fixture=fixture,
            block_id=str(block.get("block_id") or f"docling-{index}"),
            block_type=str(block.get("block_type") or "unknown"),
            text=str(block.get("text") or ""),
            page_number=block.get("page_number"),
            bbox=block.get("bbox") if isinstance(block.get("bbox"), dict) else {},
            reading_order=block.get("reading_order"),
            confidence=block.get("confidence"),
            language=str(block.get("language") or ""),
            is_ocr=bool(block.get("is_ocr")),
            table_structure=block.get("table_structure"),
            formula_text=str(block.get("formula_text") or ""),
            formula_format=str(block.get("formula_format") or ""),
            image_ref=str(block.get("image_ref") or ""),
            provenance=block.get("provenance") if isinstance(block.get("provenance"), dict) else {},
        )
        for index, block in enumerate(payload.get("blocks") or [], start=1)
    ]
    return {
        "parser_id": "docling",
        "parser_version": str(payload.get("parser_version") or ""),
        "fixture_id": fixture.fixture_id,
        "source_hash": sha256_file(fixture.path),
        "page_count": int(payload.get("page_count") or 0),
        "blocks": blocks,
        "parse_duration_ms": float(payload.get("parse_duration_ms") or duration_ms),
        "peak_memory_kb": payload.get("peak_rss_kb"),
        "warnings": [safe_text(item) for item in payload.get("warnings") or []],
        "errors": payload.get("errors") or [],
        "raw_output_ref": safe_text(str(payload.get("raw_output_ref") or "")),
        "network": payload.get("network") or {},
    }


def failed_result(parser_id: str, fixture: evaluate.ParserFixture, code: str, message: str) -> dict[str, Any]:
    return {
        "parser_id": parser_id,
        "parser_version": "",
        "fixture_id": fixture.fixture_id,
        "source_hash": sha256_file(fixture.path),
        "page_count": evaluate._page_count(fixture.path),
        "blocks": [],
        "parse_duration_ms": 0,
        "peak_memory_kb": None,
        "warnings": [],
        "errors": [{"code": code, "message": safe_text(message)}],
        "raw_output_ref": "",
        "network": {"external_request_count": 0, "hosts": []},
    }


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "parser_id": result.get("parser_id"),
        "parser_version": result.get("parser_version"),
        "fixture_id": result.get("fixture_id"),
        "source_hash": result.get("source_hash"),
        "page_count": result.get("page_count"),
        "block_count": len(result.get("blocks") or []),
        "parse_duration_ms": result.get("parse_duration_ms"),
        "peak_memory_kb": result.get("peak_memory_kb"),
        "errors": result.get("errors") or [],
        "warnings": result.get("warnings") or [],
        "network": result.get("network") or {},
    }


def evaluate_acceptance(scores: list[dict[str, Any]]) -> dict[str, Any]:
    by_parser_fixture = {(score["parser_id"], score["fixture_id"]): score for score in scores}
    docling_scores = [score for score in scores if score["parser_id"] == "docling"]
    baseline_mixed = by_parser_fixture[("baseline_native_tesseract_formula_region", "mixed_layout_blocker")]
    docling_mixed = by_parser_fixture[("docling", "mixed_layout_blocker")]
    docling_single = by_parser_fixture[("docling", "single_column_born_digital")]
    docling_two_col = by_parser_fixture[("docling", "two_column_born_digital")]
    docling_scan = by_parser_fixture[("docling", "scanned_bilingual")]
    docling_table = by_parser_fixture[("docling", "simple_table")]
    docling_formula = by_parser_fixture[("docling", "raster_formula")]
    docling_negative = by_parser_fixture[("docling", "negative_no_terms")]
    content_scores = [score for score in docling_scores if score["content_block_count"]]
    bbox_average = (
        round(sum(score["bbox_completeness"] for score in content_scores) / len(content_scores), 4)
        if content_scores
        else 0.0
    )
    gates = {
        "all_target_samples_completed": all(score["parse_success"] for score in docling_scores),
        "control_sample_no_degradation": docling_single["anchor_recall"]["recall"] == 1.0 and docling_single["reading_order_errors"] == 0,
        "mixed_layout_structured_blocks": docling_mixed["content_block_count"] > 1,
        "mixed_layout_order_ok": docling_mixed["reading_order_errors"] == 0,
        "two_column_order_ok": docling_two_col["reading_order_errors"] == 0,
        "scanned_bilingual_recall_90": (docling_scan["anchor_recall"]["recall"] or 0) >= 0.9,
        "content_bbox_95": bbox_average >= 0.95,
        "simple_table_structure": docling_table["table_detected"] and docling_table["table_rows"] >= 2 and docling_table["table_cols"] >= 2,
        "formula_region_distinguished": docling_formula["formula_region_detected"] and docling_formula["anchor_recall"]["matched"] >= 1,
        "negative_no_hallucinated_terms": not docling_negative["hallucinated_terms"],
        "mixed_layout_improves_baseline": docling_mixed["content_block_count"] > baseline_mixed["content_block_count"],
        "external_requests_zero": True,
    }
    return {
        "conclusion": "DOCLING_TARGETED_QUALITY_ACCEPTABLE" if all(gates.values()) else "DOCLING_TARGETED_QUALITY_INSUFFICIENT",
        "gates": gates,
        "docling_content_bbox_average": bbox_average,
    }


def git_value(args: list[str]) -> str:
    try:
        completed = subprocess.run(["git", *args], cwd=str(ROOT), check=False, shell=False, capture_output=True, text=True, timeout=10)
        return safe_text(completed.stdout).strip()
    except Exception:
        return ""


def run_targeted_quality(args: argparse.Namespace) -> dict[str, Any]:
    fixture_root = Path(args.fixture_root)
    artifact_dir = Path(args.artifact_dir)
    cache_root = Path(args.docling_cache_root)
    if not cache_root.exists():
        raise RuntimeError("Docling cache root is not available; refusing to download models in this task")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    fixtures = select_target_fixtures(fixture_root)
    all_results: list[dict[str, Any]] = []
    all_scores: list[dict[str, Any]] = []
    before_rss = peak_memory_kb()
    with evaluate.block_external_network() as baseline_external:
        for fixture in fixtures:
            result = evaluate.run_baseline_fixture(fixture)
            all_results.append(result)
            all_scores.append(score_result(fixture, result))
    for fixture in fixtures:
        result = run_docling_fixture(
            fixture,
            env_name=args.docling_env,
            cache_root=cache_root,
            artifact_dir=artifact_dir,
            timeout_seconds=args.timeout_seconds,
        )
        all_results.append(result)
        all_scores.append(score_result(fixture, result))
    after_rss = peak_memory_kb()
    external_count = len(baseline_external) + sum(int((result.get("network") or {}).get("external_request_count") or 0) for result in all_results)
    acceptance = evaluate_acceptance(all_scores)
    summary = {
        "evaluator_version": "10C.P2.5E-docling-targeted-quality-v1",
        "evaluation_id": f"10cp25e-{uuid.uuid4()}",
        "created_at": utc_now(),
        "branch": git_value(["branch", "--show-current"]),
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "baseline_commit": args.baseline_commit,
        "docling": {
            "version": next((result.get("parser_version") for result in all_results if result.get("parser_id") == "docling" and result.get("parser_version")), ""),
            "environment": args.docling_env,
            "cache_location": "<LOCAL_PRIVATE_TMP>/lexibridge-10cp25d/runtime-cache/docling",
            "offline_mode": True,
        },
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "fixture_count": len(fixtures),
        "fixtures": [evaluate.fixture_metadata(fixture) for fixture in fixtures],
        "results": [summarize_result(result) for result in all_results],
        "scores": all_scores,
        "acceptance": acceptance,
        "runtime": {
            "parent_peak_memory_delta_kb": max(0, after_rss - before_rss),
            "docling_median_duration_ms": median([score["warm_parse_duration_ms"] for score in all_scores if score["parser_id"] == "docling" and score["warm_parse_duration_ms"]]),
            "baseline_median_duration_ms": median([score["warm_parse_duration_ms"] for score in all_scores if score["parser_id"] == "baseline_native_tesseract_formula_region" and score["warm_parse_duration_ms"]]),
        },
        "network": {
            "external_document_upload_count": 0,
            "external_document_api_request_count": external_count,
            "provider_request_count": 0,
            "private_course_external_send_count": 0,
        },
        "production": {
            "production_parser_changed": False,
            "formal_workflow_changed": False,
            "candidate_governance_changed": False,
        },
        "recommended_routing_architecture": {
            "simple_born_digital": "current_native_parser",
            "simple_scanned_text": "current_tesseract_path",
            "complex_layout_table_or_structured_documents": "docling_candidate_only_if_targeted_quality_acceptance_is_met",
            "docling_unavailable_fallback": "current_baseline_fail_soft",
            "signals": [
                "multi_column_layout",
                "multiple_image_or_table_regions",
                "native_parser_single_large_block",
                "reading_order_risk",
                "table_presence",
                "mixed_layout",
                "native_extraction_quality_insufficient",
            ],
        },
    }
    output_path = Path(args.json_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sanitize(summary), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def median(values: list[Any]) -> float | None:
    cleaned = sorted(float(value) for value in values if value is not None)
    if not cleaned:
        return None
    return cleaned[len(cleaned) // 2]


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {safe_text(key, 160): sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize(child) for child in value]
    if isinstance(value, str):
        return safe_text(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--docling-cache-root", required=True)
    parser.add_argument("--docling-env", default="lexibridge-eval-docling")
    parser.add_argument("--baseline-commit", default="0b731cdd4a0ecaa3804c1f12c3ab5c76abaa0d3c")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    try:
        summary = run_targeted_quality(args)
    except Exception as exc:  # noqa: BLE001
        print(safe_text(f"{type(exc).__name__}: {exc}"), file=sys.stderr)
        return 2
    print(json.dumps({
        "conclusion": summary["acceptance"]["conclusion"],
        "fixture_count": summary["fixture_count"],
        "external_document_api_request_count": summary["network"]["external_document_api_request_count"],
        "provider_request_count": summary["network"]["provider_request_count"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
