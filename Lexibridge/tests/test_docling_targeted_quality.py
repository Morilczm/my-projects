from scripts.evaluations.open_source_parser_eval import docling_targeted_probe as probe
from scripts.evaluations.open_source_parser_eval import docling_targeted_quality as quality


def test_targeted_fixture_selection_is_limited_to_safe_required_set(tmp_path):
    fixtures = quality.select_target_fixtures(tmp_path / "fixtures")

    assert [fixture.fixture_id for fixture in fixtures] == list(quality.TARGET_FIXTURE_IDS)
    assert len(fixtures) == 7
    assert all(fixture.privacy_classification == "SYNTHETIC" for fixture in fixtures)


def test_docling_offline_environment_uses_supplied_cache_without_network_flags(tmp_path):
    cache = tmp_path / "cache with spaces"
    env = quality.build_docling_env(cache)

    assert env["HF_HOME"] == str(cache / "huggingface")
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"
    assert "DOCLING" not in env


def test_sanitize_removes_local_paths_and_secret_shapes():
    payload = {
        "path": "/" + "Users/example/private.pdf",
        "tmp": "/" + "private/tmp/docling-cache",
        "secret": "Authorization:" + " Bearer " + "sk-" + "testvalue",
    }

    sanitized = quality.sanitize(payload)

    assert "/" + "Users/" not in str(sanitized)
    assert "/" + "private/tmp" not in str(sanitized)
    assert "Authorization:" not in str(sanitized)
    assert "sk-" + "testvalue" not in str(sanitized)


def test_docling_export_walker_preserves_page_bbox_and_table_shape():
    exported = {
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "Mixed Layout Fixture",
                "prov": [{"page_no": 1, "bbox": {"l": 10, "t": 20, "r": 110, "b": 40}}],
            }
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1, "bbox": {"l": 20, "t": 80, "r": 220, "b": 180}}],
                "data": {
                    "table_cells": [
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 0, "text": "Domain"},
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 1, "text": "Term"},
                        {"start_row_offset_idx": 1, "start_col_offset_idx": 0, "text": "Signals"},
                        {"start_row_offset_idx": 1, "start_col_offset_idx": 1, "text": "Impulse Response"},
                    ]
                },
            }
        ],
    }

    blocks = probe.walk_docling_export(exported)

    assert blocks[0]["block_type"] == "heading"
    assert blocks[0]["page_number"] == 1
    assert blocks[0]["bbox"]["width"] == 100
    table = next(block for block in blocks if block["block_type"] == "table")
    assert table["table_structure"]["rows"] == 2
    assert table["table_structure"]["cols"] == 2
    assert "Impulse Response" in table["text"]


def test_acceptance_is_insufficient_when_scanned_bilingual_recall_or_table_gate_fails():
    def score(parser_id, fixture_id, *, recall=1.0, content_blocks=2, bbox=1.0, table=False, rows=0, cols=0, formula=False, hallucinated=None):
        return {
            "parser_id": parser_id,
            "fixture_id": fixture_id,
            "parse_success": True,
            "content_block_count": content_blocks,
            "anchor_recall": {"recall": recall, "matched": int(recall * 10), "total": 10, "missing": []},
            "reading_order_errors": 0,
            "bbox_completeness": bbox,
            "table_detected": table,
            "table_rows": rows,
            "table_cols": cols,
            "formula_region_detected": formula,
            "hallucinated_terms": hallucinated or [],
        }

    scores = [
        score("baseline_native_tesseract_formula_region", "mixed_layout_blocker", content_blocks=1),
        score("docling", "single_column_born_digital"),
        score("docling", "mixed_layout_blocker", content_blocks=4),
        score("docling", "two_column_born_digital"),
        score("docling", "scanned_bilingual", recall=0.5),
        score("docling", "simple_table", table=True, rows=4, cols=3),
        score("docling", "raster_formula", formula=True),
        score("docling", "negative_no_terms", recall=0.0),
    ]

    result = quality.evaluate_acceptance(scores)

    assert result["conclusion"] == "DOCLING_TARGETED_QUALITY_INSUFFICIENT"
    assert result["gates"]["scanned_bilingual_recall_90"] is False
