from scripts.evaluations.open_source_parser_eval import evaluate
from scripts.evaluations.open_source_parser_eval import ppstructurev3_targeted_validation as ppv3


def test_normalizer_uses_block_order_and_preserves_raw_reference():
    raw = [
        {
            "block_id": "right-1",
            "block_label": "text",
            "block_content": "Voltage Divider",
            "block_bbox": [310, 120, 520, 150],
            "block_order": 2,
            "page_index": 0,
        },
        {
            "block_id": "left-1",
            "block_label": "text",
            "block_content": "Fourier Transform",
            "block_bbox": [72, 120, 280, 150],
            "block_order": 1,
            "page_index": 0,
        },
    ]

    blocks = ppv3.normalize_ppstructure_blocks(raw, page_width=612, page_height=792)

    assert [block.text for block in blocks] == ["Fourier Transform", "Voltage Divider"]
    assert blocks[0].source_index == 1
    assert blocks[0].source_block_id == "left-1"
    assert blocks[0].bbox is not None
    assert blocks[0].bbox.origin == "TOP_LEFT"


def test_reading_order_metrics_report_pairwise_and_column_switches():
    fixture = evaluate.ParserFixture(
        fixture_id="two_column_born_digital",
        filename="synthetic.pdf",
        path=None,
        privacy_classification="SYNTHETIC",
        domains=("signals",),
        expected_anchors=(
            evaluate.GoldAnchor("Fourier Transform", "paragraph", 1),
            evaluate.GoldAnchor("Impulse Response", "paragraph", 2),
            evaluate.GoldAnchor("Voltage Divider", "paragraph", 3),
        ),
    )

    metrics = ppv3.reading_order_metrics(
        "Fourier Transform\nVoltage Divider\nImpulse Response",
        fixture,
    )

    assert metrics["exact_anchor_order_match"] is False
    assert metrics["pairwise_ordering_accuracy"] < 1.0
    assert metrics["column_switch_count"] >= 1
    assert metrics["observed_anchor_order"] == [
        "Fourier Transform",
        "Voltage Divider",
        "Impulse Response",
    ]


def test_bbox_metrics_ignore_logical_groups_and_count_invalid_visual_blocks():
    blocks = [
        ppv3.PPStructureBlock(
            block_id="visual-ok",
            source_index=0,
            source_block_id="visual-ok",
            block_type="paragraph",
            text="Transfer Function",
            page_number=1,
            bbox=ppv3.PPStructureBBox(left=1, top=2, right=11, bottom=22, width=10, height=20),
            raw_label="text",
            raw_order=1,
        ),
        ppv3.PPStructureBlock(
            block_id="group",
            source_index=1,
            source_block_id="group",
            block_type="group",
            text="",
            page_number=1,
            bbox=None,
            raw_label="group",
            raw_order=2,
        ),
        ppv3.PPStructureBlock(
            block_id="visual-missing",
            source_index=2,
            source_block_id="visual-missing",
            block_type="image",
            text="",
            page_number=1,
            bbox=None,
            raw_label="image",
            raw_order=3,
        ),
    ]

    metrics = ppv3.bbox_metrics(blocks, page_width=612, page_height=792)

    assert metrics["visual_block_count"] == 2
    assert metrics["visual_bbox_completeness"] == 0.5
    assert metrics["missing_bbox_count"] == 1
    assert metrics["invalid_bbox_count"] == 0


def test_runtime_blocked_artifact_schema_is_safe_and_explicit():
    report = ppv3.build_runtime_blocked_report(
        baseline_commit="1ac7955009b8885a6444db3ee817652afc001968",
        branch="eval/ppstructurev3-targeted-validation-10c-p25g",
        environment={"python": "3.11.15", "architecture": "arm64"},
        package_manifest={"paddleocr": "3.7.0", "paddlex": "3.7.2", "paddlepaddle": "NOT_INSTALLED"},
        runtime={"import_status": "PPSTRUCTUREV3_IMPORT_TIMEOUT"},
        database={
            "before_sha256": "9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa",
            "after_sha256": "9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa",
        },
    )

    ppv3.validate_report(report)
    assert report["status"] == "PPSTRUCTUREV3_RUNTIME_BLOCKED"
    assert report["production"]["production_parser_changed"] is False
    assert report["network"]["external_document_api_requests"] == 0
