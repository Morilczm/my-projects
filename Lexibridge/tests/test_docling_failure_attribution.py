from scripts.evaluations.open_source_parser_eval import docling_failure_attribution as attribution
from scripts.evaluations.open_source_parser_eval import docling_failure_attribution_runner as runner
from scripts.evaluations.open_source_parser_eval import evaluate


def _bbox(l=10, t=20, r=110, b=60):
    return {"l": l, "t": t, "r": r, "b": b, "coord_origin": "BOTTOMLEFT"}


def test_body_tree_traversal_is_used_instead_of_texts_collection_order():
    exported = {
        "body": {
            "self_ref": "#/body",
            "children": [{"$ref": "#/texts/1"}, {"$ref": "#/texts/0"}],
        },
        "furniture": {
            "self_ref": "#/furniture",
            "children": [{"$ref": "#/texts/2"}],
        },
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Second body item",
                "prov": [{"page_no": 1, "bbox": _bbox(10, 40, 110, 60)}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "First body item",
                "prov": [{"page_no": 1, "bbox": _bbox(10, 70, 110, 90)}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "page_footer",
                "text": "Footer item",
                "prov": [{"page_no": 1, "bbox": _bbox(10, 10, 110, 20)}],
            },
        ],
    }

    document = attribution.canonicalize_docling_export(exported)

    assert [block.text for block in document.body_blocks()] == ["First body item", "Second body item"]
    assert [block.text for block in document.furniture_blocks()] == ["Footer item"]
    assert all(block.source_item_ref != "#/texts/2" for block in document.body_blocks())


def test_provenance_bbox_is_extracted_and_logical_table_cells_do_not_break_content_completeness():
    exported = {
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1, "bbox": _bbox(20, 100, 220, 200)}],
                "data": {
                    "table_cells": [
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 0, "text": "Domain"},
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 1, "text": "Term"},
                    ]
                },
                "children": [{"$ref": "#/groups/0"}],
            }
        ],
        "groups": [{"self_ref": "#/groups/0", "label": "table_cell", "text": "Domain"}],
    }

    document = attribution.canonicalize_docling_export(exported)
    table = document.body_blocks()[0]

    assert table.block_type == "table"
    assert table.bbox is not None
    assert table.bbox.width == 200
    assert table.bbox.height == 100
    assert table.table_structure["rows"] == 1
    assert table.table_structure["cols"] == 2
    assert attribution.visual_content_bbox_completeness(document.body_blocks()) == 1.0


def test_multiple_provenance_bboxes_are_union_bboxes_marked_derived():
    exported = {
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/texts/0"}]},
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Wrapped paragraph",
                "prov": [
                    {"page_no": 1, "bbox": _bbox(10, 20, 110, 40)},
                    {"page_no": 1, "bbox": _bbox(20, 50, 160, 80)},
                ],
            }
        ],
    }

    document = attribution.canonicalize_docling_export(exported)
    block = document.body_blocks()[0]

    assert block.bbox is not None
    assert block.bbox_is_derived is True
    assert block.bbox.left == 10
    assert block.bbox.right == 160
    assert len(block.provenance) == 2


def test_formula_region_overlap_routes_picture_to_formula_without_latex():
    exported = {
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/pictures/0"}]},
        "pictures": [
            {
                "self_ref": "#/pictures/0",
                "label": "picture",
                "prov": [{"page_no": 1, "bbox": _bbox(70, 320, 500, 430)}],
            }
        ],
    }
    formula_regions = [
        {
            "formula_region_uid": "formula-region-1",
            "page_number": 1,
            "bounding_box": {"x": 72, "y": 320, "width": 420, "height": 110},
            "detection_confidence": 0.91,
            "recognizer_status": "FORMULA_RECOGNIZER_UNAVAILABLE",
        }
    ]

    document = attribution.canonicalize_docling_export(exported, formula_regions=formula_regions)
    block = document.body_blocks()[0]

    assert block.block_type == "formula"
    assert block.original_block_type == "image"
    assert block.formula_route["recognizer_status"] == "FORMULA_RECOGNIZER_UNAVAILABLE"
    assert block.formula_route["latex_candidate"] == ""
    assert block.formula_route["overlap_iou"] > 0.8
    assert block.source_item_ref == "#/pictures/0"


def test_attribution_report_schema_requires_stable_evidence_refs():
    report = attribution.build_attribution_report(
        fixtures=[],
        failures={
            "two_column_reading_order": attribution.failure_entry(
                attribution="DOCLING_ASSEMBLY_DEFECT",
                first_incorrect_layer="L2",
                evidence_refs=["artifact:two-column:L2:body_order"],
                repairable=False,
            )
        },
        decision_status="DOCLING_PARTIAL_CAPABILITY_ATTRIBUTED",
        reason="At least one failure is model-level and one is repairable in evaluation.",
    )

    attribution.validate_attribution_report(report)
    report["database_integrity"] = dict(runner.DATABASE_INTEGRITY)
    assert report["failures"]["two_column_reading_order"]["evidence_refs"]
    assert report["decision"]["status"] == "DOCLING_PARTIAL_CAPABILITY_ATTRIBUTED"
    assert report["database_integrity"]["incident_investigation_status"] == "DATABASE_INTEGRITY_INCIDENT_INVESTIGATED"
    assert report["database_integrity"]["accepted_as_new_normal_baseline"] is False


def test_sequence_metrics_uses_observed_text_order_not_gold_iteration_order(tmp_path):
    fixture = evaluate.ParserFixture(
        fixture_id="two_column_born_digital",
        filename="synthetic.pdf",
        path=tmp_path / "synthetic.pdf",
        privacy_classification="SYNTHETIC",
        domains=("signals",),
        expected_anchors=(
            evaluate.GoldAnchor("Left A", "paragraph", 1),
            evaluate.GoldAnchor("Left B", "paragraph", 2),
            evaluate.GoldAnchor("Right A", "paragraph", 3),
        ),
    )

    metrics = runner._sequence_metrics("Left A\nRight A\nLeft B", fixture)

    assert metrics["exact_sequence_match"] is False
    assert metrics["pairwise_ordering_accuracy"] < 1.0
    assert metrics["observed_order"] == ["Left A", "Right A", "Left B"]
