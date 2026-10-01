from pathlib import Path

from scripts.evaluations.open_source_parser_eval import evaluate


def test_fixture_matrix_contains_required_safe_document_types(tmp_path):
    fixtures = evaluate.build_fixture_set(tmp_path / "fixtures")
    fixture_ids = {fixture.fixture_id for fixture in fixtures}

    assert {
        "single_column_born_digital",
        "two_column_born_digital",
        "bilingual_born_digital",
        "scanned_english",
        "scanned_chinese",
        "scanned_bilingual",
        "mixed_layout_blocker",
        "title_body_list",
        "plain_raster_image",
        "raster_formula",
        "born_digital_formula",
        "simple_table",
        "multi_column_table",
        "header_footer_page_number",
        "negative_no_terms",
    } <= fixture_ids
    assert all(fixture.privacy_classification == "SYNTHETIC" for fixture in fixtures)
    assert all(fixture.path.exists() and fixture.path.suffix == ".pdf" for fixture in fixtures)
    assert not any(str(fixture.path).startswith(str(Path.home())) for fixture in fixtures)


def test_baseline_evaluation_schema_is_safe_and_scores(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXIBRIDGE_10CP25_OCR_PROVIDER", "none")
    fixture = next(
        item
        for item in evaluate.build_fixture_set(tmp_path / "fixtures")
        if item.fixture_id == "single_column_born_digital"
    )

    result = evaluate.run_baseline_fixture(fixture)
    score = evaluate.score_fixture_result(fixture, result)

    assert result["parser_id"] == "baseline_native_tesseract_formula_region"
    assert result["source_hash"] == evaluate.sha256_file(fixture.path)
    assert result["blocks"]
    assert result["blocks"][0]["page_number"] == 1
    assert "Fourier Transform" in "\n".join(block["text"] for block in result["blocks"])
    assert score["anchor_recall"]["recall"] == 1.0
    assert "/Users/" not in str(result)


def test_formula_fixture_is_scored_as_detection_not_recognition(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXIBRIDGE_10CP25_OCR_PROVIDER", "none")
    fixture = next(
        item
        for item in evaluate.build_fixture_set(tmp_path / "fixtures")
        if item.fixture_id == "raster_formula"
    )

    result = evaluate.run_baseline_fixture(fixture)
    score = evaluate.score_fixture_result(fixture, result)
    formula_blocks = [block for block in result["blocks"] if block["block_type"] == "formula"]

    assert formula_blocks
    assert score["formula_detected"] is True
    assert formula_blocks[0]["formula_format"] == "unavailable"
    assert formula_blocks[0]["formula_text"] == ""


def test_candidate_probe_failure_is_structured_without_stopping_batch(tmp_path):
    fixture = next(
        item
        for item in evaluate.build_fixture_set(tmp_path / "fixtures")
        if item.fixture_id == "single_column_born_digital"
    )

    result = evaluate.run_probe_candidate(
        "docling",
        "missing-env-for-test",
        fixture,
        tmp_path / "artifacts",
        timeout=5,
    )

    assert result["parser_id"] == "docling"
    assert result["errors"]
    assert result["errors"][0]["code"] in {"PARSER_PROBE_FAILED", "CONDA_NOT_FOUND"}


def test_private_fixture_metadata_uses_logical_name_only(tmp_path):
    private_pdf = tmp_path / "course sample with spaces.pdf"
    fixture = next(
        item
        for item in evaluate.build_fixture_set(tmp_path / "fixtures")
        if item.fixture_id == "single_column_born_digital"
    )
    private_pdf.write_bytes(fixture.path.read_bytes())

    private_fixture = evaluate.build_private_fixture(private_pdf)
    metadata = evaluate.fixture_metadata(private_fixture)

    assert private_fixture.fixture_id == "local_private_course_sample"
    assert private_fixture.filename == "local-private-course-sample.pdf"
    assert metadata["privacy_classification"] == "LOCAL_ONLY_PRIVATE"
    assert str(tmp_path) not in str(metadata)


def test_selection_does_not_treat_baseline_as_open_source_parser():
    selection = evaluate.select_parser([
        {
            "parser_id": "baseline_native_tesseract_formula_region",
            "passed_hard_gate": True,
            "weighted_total": 80,
        },
        {
            "parser_id": "docling",
            "passed_hard_gate": False,
            "weighted_total": 20,
        },
    ])

    assert selection["selected_primary_parser"] is None
    assert selection["fallback_parser"] == "baseline_native_tesseract_formula_region"
