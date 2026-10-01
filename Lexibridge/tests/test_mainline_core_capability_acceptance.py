import json
from pathlib import Path

from scripts import run_mainline_core_capability_acceptance as acceptance


def test_fixture_generator_covers_required_mainline_document_types(tmp_path):
    fixtures = acceptance.build_fixture_set(tmp_path / "fixtures")

    fixture_ids = {fixture.fixture_id for fixture in fixtures}
    assert {
        "born-digital-text",
        "scanned-english",
        "scanned-chinese",
        "scanned-bilingual",
        "mixed-layout",
        "formula-image",
        "explicit-bilingual-pair",
        "ambiguous-context",
    } <= fixture_ids
    for fixture in fixtures:
        assert fixture.path.exists()
        assert fixture.path.suffix == ".pdf"
        assert fixture.privacy_classification == "SYNTHETIC"
        assert not str(fixture.path).startswith(str(Path.home()))


def test_acceptance_runner_uses_isolated_database_and_reports_ocr_blocker(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER", "none")
    monkeypatch.setenv("FORMULA_OCR_PROVIDER", "none")
    monkeypatch.setenv("LEXIBRIDGE_10CP0_OCR_PROVIDER", "none")
    main_db = Path("backend/lexibridge.db")
    before = acceptance.sha256_file(main_db)
    output = tmp_path / "acceptance.json"

    result = acceptance.run_acceptance(
        database_path=tmp_path / "acceptance.db",
        uploads_path=tmp_path / "uploads",
        artifact_path=output,
        fixture_root=tmp_path / "fixtures",
    )

    after = acceptance.sha256_file(main_db)
    assert after == before
    assert output.exists()
    assert result["final_status"] == "SCANNED_PDF_OCR_BLOCKS_MAINLINE"
    assert result["main_database"]["mutated"] is False
    assert result["external_requests"] == 0
    assert result["real_provider_requests"] == 0
    assert result["private_course_provider_requests"] == 0

    by_id = {fixture["fixture_id"]: fixture for fixture in result["fixtures"]}
    scanned = by_id["scanned-english"]
    assert scanned["upload"]["status_code"] == 422
    assert scanned["ocr"]["text_layer_detected"] is False
    assert scanned["ocr"]["ocr_required"] is True
    assert scanned["ocr"]["ocr_nonempty_text"] is False
    assert scanned["formal"]["run_uid"] == ""

    second = acceptance.run_acceptance(
        database_path=tmp_path / "acceptance.db",
        uploads_path=tmp_path / "uploads",
        artifact_path=output,
        fixture_root=tmp_path / "fixtures",
    )
    assert second["final_status"] == result["final_status"]
    assert acceptance.sha256_file(main_db) == before


def test_acceptance_distinguishes_formula_image_detection_from_formula_text_recognition(monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_PROVIDER", "none")
    monkeypatch.setenv("FORMULA_OCR_PROVIDER", "none")
    monkeypatch.setenv("LEXIBRIDGE_10CP0_OCR_PROVIDER", "auto")
    result = acceptance.run_acceptance(
        database_path=tmp_path / "acceptance.db",
        uploads_path=tmp_path / "uploads",
        artifact_path=tmp_path / "acceptance.json",
        fixture_root=tmp_path / "fixtures",
    )

    formula = {fixture["fixture_id"]: fixture for fixture in result["fixtures"]}["formula-image"]
    assert formula["upload"]["status_code"] == 200
    assert formula["formula"]["formula_image_expected"] is True
    assert formula["formula"]["formula_image_detected"] is True
    assert formula["formula"]["formula_text_recognized"] is False
    assert formula["formula"]["formula_context_linked"] is True
    assert formula["formula"]["formula_statuses"] == ["FORMULA_RECOGNIZER_UNAVAILABLE"]


def test_acceptance_artifact_is_redacted_and_structured(monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_PROVIDER", "none")
    monkeypatch.setenv("FORMULA_OCR_PROVIDER", "none")
    monkeypatch.setenv("LEXIBRIDGE_10CP0_OCR_PROVIDER", "none")
    output = tmp_path / "acceptance.json"
    result = acceptance.run_acceptance(
        database_path=tmp_path / "acceptance.db",
        uploads_path=tmp_path / "uploads",
        artifact_path=output,
        fixture_root=tmp_path / "fixtures",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["evaluation_id"] == result["evaluation_id"]
    assert "/Users/" not in serialized
    assert "file://" not in serialized
    assert "LEXIBRIDGE_SENTINEL" not in serialized
    assert "<LOCAL_PRIVATE_TMP>" in serialized
