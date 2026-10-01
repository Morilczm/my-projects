from __future__ import annotations

from types import SimpleNamespace

from scripts.evaluations.open_source_parser_eval import controlled_benchmark_14b as benchmark


def _block(
    block_id: str,
    text: str,
    *,
    block_type: str = "paragraph",
    page_number: int | None = 1,
    bbox: dict | None = None,
    reading_order: int = 1,
):
    return {
        "block_id": block_id,
        "block_type": block_type,
        "text": text,
        "page_number": page_number,
        "bbox": bbox if bbox is not None else {"x0": 10, "y0": 10, "x1": 90, "y1": 30},
        "reading_order": reading_order,
        "provenance": {"source_item_ref": block_id},
    }


def test_mineru_v2_normalizer_preserves_page_bbox_types_and_order():
    pages = [[
        {
            "type": "title",
            "content": {"title_content": [{"type": "text", "content": "Electric Charge"}], "level": 2},
            "bbox": [10, 20, 210, 50],
        },
        {
            "type": "paragraph",
            "content": {"paragraph_content": [{"type": "text", "content": "A conserved property of matter."}]},
            "bbox": [10, 60, 310, 100],
        },
    ]]

    blocks = benchmark.normalize_mineru_content_list_v2(pages, fixture_id="synthetic")

    assert [block["block_type"] for block in blocks] == ["heading", "paragraph"]
    assert [block["page_number"] for block in blocks] == [1, 1]
    assert [block["reading_order"] for block in blocks] == [1, 2]
    assert blocks[0]["bbox"] == {"x0": 10.0, "y0": 20.0, "x1": 210.0, "y1": 50.0}
    assert blocks[0]["provenance"]["source_parser"] == "mineru"


def test_controlled_fixture_set_is_synthetic_bilingual_and_covers_all_metrics(tmp_path):
    import fitz

    fixtures = benchmark.build_controlled_fixture_set(tmp_path / "fixtures")
    by_id = {fixture.fixture_id: fixture for fixture in fixtures}

    assert len(fixtures) == 11
    assert all(fixture.privacy_classification == "SYNTHETIC" for fixture in fixtures)
    assert all(fixture.path.is_file() and fixture.path.suffix == ".pdf" for fixture in fixtures)
    assert {fixture.language for fixture in fixtures} >= {"en", "zh"}
    assert "two_column_born_digital" in by_id
    assert "simple_table" in by_id
    assert "raster_formula" in by_id
    assert by_id["repeated_header_footer"].expected_noise
    assert by_id["retrieval_english"].expected_heading_definition_pairs
    assert by_id["retrieval_chinese"].expected_heading_definition_pairs
    with fitz.open(by_id["retrieval_chinese"].path) as document:
        chinese_text = "\n".join(page.get_text() for page in document).casefold()
    assert not any(
        concept.english_term.casefold() in chinese_text
        for concept in benchmark.RETRIEVAL_CONCEPTS
    )


def test_metric_contract_covers_required_quality_dimensions():
    fixture = SimpleNamespace(
        fixture_id="heading_definition",
        expected_anchors=(
            SimpleNamespace(text="Electric Charge", order=1),
            SimpleNamespace(text="A conserved property", order=2),
        ),
        expected_heading_definition_pairs=(("Electric Charge", "A conserved property"),),
        expected_noise=("Repeated course header", "Page 1"),
        expected_table_rows=0,
        expected_table_cols=0,
        expected_formula_count=0,
    )
    result = {
        "parser_id": "candidate",
        "errors": [],
        "parse_duration_ms": 12.0,
        "peak_rss_mb": 42.0,
        "blocks": [
            _block("h1", "Electric Charge", block_type="heading", reading_order=1),
            _block("p1", "A conserved property of matter.", reading_order=2),
        ],
    }

    metrics = benchmark.score_document(fixture, result)

    assert metrics["parse_success"] is True
    assert metrics["reading_order_accuracy"] == 1.0
    assert metrics["heading_definition_integrity"] == 1.0
    assert metrics["page_provenance_completeness"] == 1.0
    assert metrics["block_provenance_completeness"] == 1.0
    assert metrics["bbox_provenance_completeness"] == 1.0
    assert metrics["header_footer_filter_rate"] == 1.0
    assert metrics["duplicate_block_count"] == 0
    assert metrics["runtime_ms"] == 12.0
    assert metrics["peak_rss_mb"] == 42.0


def test_heading_definition_integrity_requires_same_or_adjacent_block():
    pair = ("Electric Charge", "A conserved property")
    adjacent = [
        _block("h", "Electric Charge", block_type="heading", reading_order=1),
        _block("p", "A conserved property of matter.", reading_order=2),
    ]
    split = adjacent + [
        _block("noise", "Unrelated chapter", block_type="heading", reading_order=2),
    ]
    split[1]["reading_order"] = 3

    assert benchmark.heading_definition_integrity(adjacent, (pair,)) == 1.0
    assert benchmark.heading_definition_integrity(split, (pair,)) == 0.0


def test_duplicate_metric_ignores_empty_and_counts_repeated_body_text():
    blocks = [
        _block("a", "Repeated definition"),
        _block("b", "  repeated   definition ", reading_order=2),
        _block("c", ""),
    ]

    assert benchmark.duplicate_block_count(blocks) == 1


def test_parser_blocks_reuse_existing_knowledge_chunk_builder():
    parse_record, parse_blocks = benchmark.parser_result_to_ingestion_contract(
        parser_id="docling",
        parser_version="2.117.0",
        fixture_id="retrieval_zh",
        blocks=[
            _block("h-charge", "电荷", block_type="heading", reading_order=1),
            _block("p-charge", "物质的一种守恒属性。", reading_order=2),
        ],
        language="zh",
    )

    chunks = benchmark.build_existing_pipeline_chunks(
        parse_record=parse_record,
        parse_blocks=parse_blocks,
        source_uid="source-zh-docling",
        language="zh",
    )

    assert len(chunks) == 1
    assert chunks[0]["source_section"] == "电荷"
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["parse_block_uid"] == "h-charge"
    assert "parser_backend_docling" in chunks[0]["quality_flags"]


def test_retrieval_metrics_are_rank_based_and_not_parser_claims():
    rankings = {
        "charge": ["charge", "field", "potential"],
        "field": ["potential", "charge", "field"],
        "missing": [],
    }

    metrics = benchmark.rank_metrics(rankings)

    assert metrics == {
        "denominator": 3,
        "hit_at_1": 0.3333,
        "hit_at_3": 0.6667,
        "mrr": 0.4444,
        "no_result_count": 1,
        "average_correct_rank": 2.0,
    }


def test_selection_is_scoped_rejects_nonstandard_license_and_does_not_authorize_production():
    aggregates = [
        {
            "parser_id": "baseline_native_tesseract_formula_region",
            "parse_success_rate": 1.0,
            "reading_order_accuracy": 0.8,
            "heading_definition_integrity": 0.7,
            "bbox_provenance_completeness": 0.2,
            "retrieval_hit_at_3": 0.75,
            "license_gate": "pass",
            "critical_fixture_gates": {
                "two_column_reading_order_accuracy": 1.0,
                "scanned_english_parse_success": False,
                "scanned_chinese_parse_success": False,
                "mixed_layout_table_retention": 0.0,
                "simple_table_retention": 0.0,
                "formula_retention": 0.0,
                "repeated_header_footer_filter_rate": 1.0,
            },
        },
        {
            "parser_id": "docling",
            "parse_success_rate": 1.0,
            "reading_order_accuracy": 1.0,
            "heading_definition_integrity": 1.0,
            "bbox_provenance_completeness": 1.0,
            "retrieval_hit_at_3": 0.875,
            "license_gate": "pass",
            "critical_fixture_gates": {
                "two_column_reading_order_accuracy": 0.82,
                "scanned_english_parse_success": True,
                "scanned_chinese_parse_success": True,
                "mixed_layout_table_retention": 0.0,
                "simple_table_retention": 1.0,
                "formula_retention": 0.0,
                "repeated_header_footer_filter_rate": 1.0,
            },
        },
        {
            "parser_id": "mineru",
            "parse_success_rate": 1.0,
            "reading_order_accuracy": 1.0,
            "heading_definition_integrity": 1.0,
            "bbox_provenance_completeness": 1.0,
            "retrieval_hit_at_3": 1.0,
            "license_gate": "blocked_nonstandard_license",
            "critical_fixture_gates": {
                "two_column_reading_order_accuracy": 1.0,
                "scanned_english_parse_success": True,
                "scanned_chinese_parse_success": True,
                "mixed_layout_table_retention": 1.0,
                "simple_table_retention": 1.0,
                "formula_retention": 1.0,
                "repeated_header_footer_filter_rate": 1.0,
            },
        },
    ]

    selected = benchmark.select_candidate(aggregates)

    assert selected["selected_parser_id"] == "docling"
    assert selected["selected_role"] == "conditional_complex_document_parser_candidate"
    assert selected["fallback_parser_id"] == "baseline_native_tesseract_formula_region"
    assert selected["mineru_eligible"] is False
    assert selected["production_adapter_authorized"] is False
    assert selected["recommended_scope"] == ["scanned_pdf", "simple_table_pdf"]
    assert selected["excluded_scope"] == [
        "multi_column_pdf",
        "mixed_layout_table_pdf",
        "formula_pdf_without_existing_formula_region",
    ]
    assert "existing_formula_region" in selected["composition_requirements"]


def test_aggregate_preserves_critical_fixture_gates_instead_of_hiding_them_in_average():
    scores = [
        {
            "parser_id": "docling",
            "fixture_id": "two_column_born_digital",
            "parse_success": True,
            "reading_order_accuracy": 0.82,
            "heading_definition_integrity": None,
            "page_provenance_completeness": 1.0,
            "block_provenance_completeness": 1.0,
            "bbox_provenance_completeness": 1.0,
            "table_retention": None,
            "formula_retention": None,
            "header_footer_filter_rate": None,
            "duplicate_block_count": 0,
            "runtime_ms": 100,
            "peak_rss_mb": 500,
        },
        {
            "parser_id": "docling",
            "fixture_id": "raster_formula",
            "parse_success": True,
            "reading_order_accuracy": None,
            "heading_definition_integrity": None,
            "page_provenance_completeness": 1.0,
            "block_provenance_completeness": 1.0,
            "bbox_provenance_completeness": 1.0,
            "table_retention": None,
            "formula_retention": 0.0,
            "header_footer_filter_rate": None,
            "duplicate_block_count": 0,
            "runtime_ms": 100,
            "peak_rss_mb": 500,
        },
    ]

    aggregate = benchmark.aggregate_parser(
        "docling",
        scores,
        {"hit_at_1": 0.5, "hit_at_3": 0.6, "mrr": 0.55, "chinese_chunk_count": 11},
        license_gate="pass",
    )

    assert aggregate["critical_fixture_gates"]["two_column_reading_order_accuracy"] == 0.82
    assert aggregate["critical_fixture_gates"]["formula_retention"] == 0.0
    assert aggregate["retrieval_chinese_chunk_count"] == 11


def test_sanitized_artifact_rejects_paths_source_bodies_and_secrets():
    payload = {
        "path": "file:///synthetic/private.pdf",
        "authorization": "Bearer secret-token",
        "request_body": "private source body",
        "result": {"parser_id": "docling", "fixture_id": "synthetic"},
    }

    sanitized = benchmark.sanitize_artifact(payload)

    assert "file://" not in str(sanitized)
    assert "secret-token" not in str(sanitized)
    assert "request_body" not in sanitized
    assert sanitized["result"]["parser_id"] == "docling"
