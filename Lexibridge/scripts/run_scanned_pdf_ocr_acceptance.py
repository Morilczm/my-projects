#!/usr/bin/env python3
"""Run scanned PDF OCR production-path acceptance checks.

This wrapper reuses the mainline capability runner, then evaluates only the OCR
closure criteria. It uses an isolated database and upload directory and never
writes OCR output to the repository database.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TMP_LABEL = "<LOCAL_PRIVATE_TMP>"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_mainline_core_capability_acceptance as mainline  # noqa: E402

FINAL_STATUS_CLOSED = "SCANNED_PDF_OCR_PRODUCTION_PATH_ESTABLISHED"
FINAL_STATUS_BLOCKED = "SCANNED_PDF_OCR_PRODUCTION_BLOCKED"


def _rate(item: dict[str, Any], language: str) -> float | None:
    key = "english_term_recall" if language == "en" else "chinese_term_recall"
    value = item.get("ocr", {}).get(key, {}).get("rate")
    return None if value is None else float(value)


def _fixture(result: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    return next((item for item in result.get("fixtures", []) if item.get("fixture_id") == fixture_id), {})


def _document_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": item.get("fixture_id", ""),
        "upload_status_code": item.get("upload", {}).get("status_code"),
        "governed_source_created": bool(item.get("upload", {}).get("source_uid")),
        "parse_status": item.get("parse", {}).get("parse_status", ""),
        "quality_status": item.get("parse", {}).get("quality_status", ""),
        "parser_types": item.get("parse", {}).get("parser_types", []),
        "ocr_required": item.get("ocr", {}).get("ocr_required"),
        "ocr_executed": item.get("ocr", {}).get("actual_ocr_executed"),
        "ocr_nonempty_text": item.get("ocr", {}).get("ocr_nonempty_text"),
        "english_recall": item.get("ocr", {}).get("english_term_recall"),
        "chinese_recall": item.get("ocr", {}).get("chinese_term_recall"),
        "page_locator_present": item.get("ocr", {}).get("page_locator_present"),
        "governed_chunk_count": item.get("candidate_governance", {}).get("knowledge_chunks", 0),
        "formal_item_count": item.get("formal", {}).get("item_count", 0),
        "formal_start_status_code": item.get("formal", {}).get("start_status_code"),
        "bilingual_evidence": item.get("bilingual_evidence", {}),
    }


def evaluate_ocr_acceptance(mainline_result: dict[str, Any]) -> dict[str, Any]:
    born = _fixture(mainline_result, "born-digital-text")
    english = _fixture(mainline_result, "scanned-english")
    chinese = _fixture(mainline_result, "scanned-chinese")
    bilingual = _fixture(mainline_result, "scanned-bilingual")
    mixed = _fixture(mainline_result, "mixed-layout")
    formula = _fixture(mainline_result, "formula-image")
    checks = {
        "born_digital_no_ocr_regression": (
            born.get("upload", {}).get("status_code") == 200
            and born.get("ocr", {}).get("actual_ocr_executed") is False
            and int(born.get("formal", {}).get("item_count") or 0) > 0
        ),
        "scanned_english_accepted": (
            english.get("upload", {}).get("status_code") == 200
            and english.get("ocr", {}).get("actual_ocr_executed") is True
            and (_rate(english, "en") or 0) >= 0.9
            and int(english.get("formal", {}).get("item_count") or 0) > 0
        ),
        "scanned_chinese_accepted": (
            chinese.get("upload", {}).get("status_code") == 200
            and chinese.get("ocr", {}).get("actual_ocr_executed") is True
            and (_rate(chinese, "zh") or 0) >= 0.85
            and int(chinese.get("candidate_governance", {}).get("knowledge_chunks") or 0) > 0
        ),
        "scanned_bilingual_accepted": (
            bilingual.get("upload", {}).get("status_code") == 200
            and bilingual.get("ocr", {}).get("actual_ocr_executed") is True
            and (_rate(bilingual, "en") or 0) >= 0.8
            and (_rate(bilingual, "zh") or 0) >= 0.8
            and int(bilingual.get("formal", {}).get("item_count") or 0) > 0
        ),
        "mixed_layout_regression": mixed.get("upload", {}).get("status_code") == 200,
        "formula_image_recognition_not_closed": (
            formula.get("formula", {}).get("formula_image_expected") is True
            and formula.get("formula", {}).get("formula_text_recognized") is False
        ),
        "external_requests_zero": int(mainline_result.get("external_requests") or 0) == 0,
        "real_provider_requests_zero": int(mainline_result.get("real_provider_requests") or 0) == 0,
        "private_course_provider_requests_zero": int(mainline_result.get("private_course_provider_requests") or 0) == 0,
        "main_database_unchanged": mainline_result.get("main_database", {}).get("mutated") is False,
    }
    final_status = FINAL_STATUS_CLOSED if all(checks.values()) else FINAL_STATUS_BLOCKED
    return {
        "evaluation_id": "lexibridge-10cp1-scanned-pdf-ocr-acceptance",
        "artifact_schema_version": "lexibridge-scanned-pdf-ocr-acceptance-v1",
        "git_commit": mainline_result.get("git_commit", ""),
        "mainline_final_status": mainline_result.get("final_status", ""),
        "mainline_main_blocker": mainline_result.get("main_blocker", ""),
        "checks": checks,
        "documents": {
            "born_digital_text": _document_summary(born),
            "scanned_english": _document_summary(english),
            "scanned_chinese": _document_summary(chinese),
            "scanned_bilingual": _document_summary(bilingual),
            "mixed_layout": _document_summary(mixed),
            "formula_image": _document_summary(formula),
        },
        "external_requests": mainline_result.get("external_requests", 0),
        "real_provider_requests": mainline_result.get("real_provider_requests", 0),
        "private_course_provider_requests": mainline_result.get("private_course_provider_requests", 0),
        "main_database": mainline_result.get("main_database", {}),
        "final_status": final_status,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="/private/tmp/lexibridge-10cp1-ocr-acceptance.db")
    parser.add_argument("--uploads", default="/private/tmp/lexibridge-10cp1-ocr-acceptance-uploads")
    parser.add_argument("--fixtures", default="/private/tmp/lexibridge-10cp1-ocr-acceptance-fixtures")
    parser.add_argument("--json-output", default="/private/tmp/lexibridge-10cp1-ocr-acceptance.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mainline_result = mainline.run_acceptance(
        database_path=Path(args.database),
        uploads_path=Path(args.uploads),
        artifact_path=Path(args.json_output),
        fixture_root=Path(args.fixtures),
    )
    result = evaluate_ocr_acceptance(mainline_result)
    output = Path(args.json_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "final_status": result["final_status"],
        "mainline_final_status": result["mainline_final_status"],
        "external_requests": result["external_requests"],
        "real_provider_requests": result["real_provider_requests"],
        "private_course_provider_requests": result["private_course_provider_requests"],
        "main_database_mutated": result["main_database"].get("mutated"),
        "artifact": f"{LOCAL_TMP_LABEL}/{output.name}",
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["final_status"] == FINAL_STATUS_CLOSED else 2


if __name__ == "__main__":
    raise SystemExit(main())
