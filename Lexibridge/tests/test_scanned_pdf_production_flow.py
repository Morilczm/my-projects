import os
import re

import pytest

from scripts import run_mainline_core_capability_acceptance as acceptance
from services import document_parse_quality, ocr


def _normalized_text(text):
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _term_recall(text, terms):
    if not terms:
        return 1.0
    normalized = _normalized_text(text)
    hits = sum(1 for term in terms if _normalized_text(term) in normalized)
    return hits / len(terms)


def _require_local_tesseract():
    if not os.environ.get("LEXIBRIDGE_TESSERACT_CMD"):
        pytest.skip("real Tesseract OCR smoke requires LEXIBRIDGE_TESSERACT_CMD")
    health = ocr.check_tesseract_health()
    if not health.ready:
        pytest.skip(f"real Tesseract OCR smoke unavailable: {health.safe_error_code}")


def _fixture_by_id(tmp_path, fixture_id):
    fixtures = acceptance.build_fixture_set(tmp_path / "fixtures")
    return {fixture.fixture_id: fixture for fixture in fixtures}[fixture_id]


def test_scanned_english_pdf_uses_real_ocr_and_preserves_page_provenance(tmp_path):
    _require_local_tesseract()
    fixture = _fixture_by_id(tmp_path, "scanned-english")

    result = document_parse_quality.parse_document_with_quality(
        str(fixture.path),
        filename=fixture.filename,
        ocr_provider_name="auto",
        language_hint=fixture.source_language,
    )

    assert result.parse_record_data["ocr_required"] is True
    assert result.parse_record_data["ocr_available"] is True
    assert result.parse_record_data["quality_status"] in {"ocr_text_ok", "ocr_low_confidence"}
    assert result.parse_record_data["error_code"] == ""
    assert document_parse_quality.should_allow_term_extraction(result.parse_record_data) is True
    assert _term_recall(result.raw_text, fixture.expected_english_terms) >= 0.9
    assert any(block["parser_type"] == "ocr" for block in result.blocks)
    assert all(block["page_number"] == 1 for block in result.blocks if block["parser_type"] == "ocr")
    assert any("bbox:" in block["source_locator"] for block in result.blocks)


def test_scanned_chinese_pdf_uses_real_ocr(tmp_path):
    _require_local_tesseract()
    fixture = _fixture_by_id(tmp_path, "scanned-chinese")

    result = document_parse_quality.parse_document_with_quality(
        str(fixture.path),
        filename=fixture.filename,
        ocr_provider_name="auto",
        language_hint=fixture.source_language,
    )

    assert result.parse_record_data["ocr_required"] is True
    assert result.parse_record_data["ocr_available"] is True
    assert result.parse_record_data["quality_status"] in {"ocr_text_ok", "ocr_low_confidence"}
    assert _term_recall(result.raw_text, fixture.expected_chinese_terms) >= 0.85


def test_scanned_bilingual_pdf_recovers_explicit_pair_text(tmp_path):
    _require_local_tesseract()
    fixture = _fixture_by_id(tmp_path, "scanned-bilingual")

    result = document_parse_quality.parse_document_with_quality(
        str(fixture.path),
        filename=fixture.filename,
        ocr_provider_name="auto",
        language_hint=fixture.source_language,
    )

    recovered_pairs = 0
    normalized = _normalized_text(result.raw_text)
    for english, chinese in fixture.expected_pairs:
        if _normalized_text(english) in normalized and _normalized_text(chinese) in normalized:
            recovered_pairs += 1

    assert result.parse_record_data["quality_status"] in {"ocr_text_ok", "ocr_low_confidence"}
    assert recovered_pairs >= 4


def test_born_digital_pdf_remains_native_without_ocr(tmp_path):
    _require_local_tesseract()
    fixture = _fixture_by_id(tmp_path, "born-digital-text")

    result = document_parse_quality.parse_document_with_quality(
        str(fixture.path),
        filename=fixture.filename,
        ocr_provider_name="auto",
        language_hint=fixture.source_language,
    )

    assert result.parse_record_data["ocr_required"] is False
    assert result.parse_record_data["quality_status"] == "native_text_ok"
    assert {block["parser_type"] for block in result.blocks} == {"native"}
    assert _term_recall(result.raw_text, fixture.expected_english_terms) >= 0.9
