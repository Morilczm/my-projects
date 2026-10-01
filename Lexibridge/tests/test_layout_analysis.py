import os
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services import layout_analysis
from services.layout_analysis import (
    BoundingBox,
    DocLayoutYoloOnnxLayoutAnalyzer,
    LayoutBlock,
    get_layout_analyzer,
    layout_blocks_to_text,
    parse_pdf_layout,
)


def _write_pdf(path, draw):
    pdf = canvas.Canvas(str(path), pagesize=letter)
    draw(pdf)
    pdf.save()
    return path


def _draw_line(pdf, x, y, text, size=11, font="Helvetica"):
    pdf.setFont(font, size)
    pdf.drawString(x, y, text)


def test_rule_based_layout_excludes_header_footer_from_text(tmp_path):
    pdf_path = _write_pdf(
        tmp_path / "header-footer.pdf",
        lambda pdf: (
            _draw_line(pdf, 72, 766, "Course Notes", size=9),
            _draw_line(pdf, 72, 710, "Fourier Transform", size=18, font="Helvetica-Bold"),
            _draw_line(pdf, 72, 680, "Maps signals into frequency components.", size=11),
            _draw_line(pdf, 280, 28, "Footer Marker 1", size=9),
            pdf.showPage(),
            _draw_line(pdf, 72, 766, "Course Notes", size=9),
            _draw_line(pdf, 72, 710, "Hash Table", size=18, font="Helvetica-Bold"),
            _draw_line(pdf, 72, 680, "Stores key value pairs for fast lookup.", size=11),
            _draw_line(pdf, 280, 28, "Footer Marker 2", size=9),
        ),
    )

    result = parse_pdf_layout(pdf_path)
    text = layout_blocks_to_text(result.blocks)

    assert result.ok
    assert result.provider == "rule_based"
    assert result.needs_ocr_engine is False
    assert "Fourier Transform" in text
    assert "Hash Table" in text
    assert "Course Notes" not in text
    assert "Footer Marker 1" not in text
    assert "Footer Marker 2" not in text


def test_rule_based_layout_reads_left_column_before_right_column(tmp_path):
    pdf_path = _write_pdf(
        tmp_path / "two-column.pdf",
        lambda pdf: (
            _draw_line(pdf, 72, 720, "Left column first.", size=11),
            _draw_line(pdf, 72, 700, "Left column second.", size=11),
            _draw_line(pdf, 330, 720, "Right column first.", size=11),
            _draw_line(pdf, 330, 700, "Right column second.", size=11),
        ),
    )

    text = layout_blocks_to_text(parse_pdf_layout(pdf_path).blocks)

    assert text.index("Left column first") < text.index("Right column first")
    assert text.index("Left column second") < text.index("Right column second")


def test_blank_pdf_is_marked_as_needing_ocr_engine(tmp_path):
    pdf_path = _write_pdf(
        tmp_path / "blank.pdf",
        lambda pdf: pdf.showPage(),
    )

    result = parse_pdf_layout(pdf_path)

    assert result.page_count == 1
    assert result.blocks == ()
    assert result.needs_ocr_engine is True
    assert "no_embedded_text_blocks" in result.warnings


def test_doclayout_onnx_without_model_path_falls_back_to_rule_based(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "doclayout_yolo_onnx")
    monkeypatch.delenv("LAYOUT_MODEL_PATH", raising=False)
    pdf_path = _write_pdf(
        tmp_path / "fallback.pdf",
        lambda pdf: _draw_line(pdf, 72, 710, "Fourier Transform", size=18, font="Helvetica-Bold"),
    )

    result = parse_pdf_layout(pdf_path)

    assert result.ok
    assert result.provider == "rule_based"
    assert result.needs_ocr_engine is False
    assert any("onnx_provider_unavailable" in warning for warning in result.warnings)
    assert any("LAYOUT_MODEL_PATH is not set" in warning for warning in result.warnings)


def test_unknown_layout_provider_falls_back_to_rule_based(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "not-a-real-provider")
    pdf_path = _write_pdf(
        tmp_path / "unknown-provider.pdf",
        lambda pdf: _draw_line(pdf, 72, 710, "Fourier Transform", size=18, font="Helvetica-Bold"),
    )

    result = parse_pdf_layout(pdf_path)

    assert result.ok
    assert result.provider == "rule_based"
    assert any("unknown_layout_provider:not-a-real-provider" in warning for warning in result.warnings)


def test_onnx_analyzer_reports_unavailable_without_model(monkeypatch):
    monkeypatch.delenv("LAYOUT_MODEL_PATH", raising=False)
    analyzer = DocLayoutYoloOnnxLayoutAnalyzer()

    assert analyzer.is_available() is False

    result = analyzer.analyze_pdf("unused.pdf")

    assert result.ok is False
    assert result.status == "layout_unavailable"
    assert result.blocks == ()
    assert "LAYOUT_MODEL_PATH is not set" in result.error


def test_onnx_analyzer_reports_unavailable_for_missing_model_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LAYOUT_MODEL_PATH", str(tmp_path / "missing.onnx"))
    analyzer = DocLayoutYoloOnnxLayoutAnalyzer()

    assert analyzer.is_available() is False
    assert analyzer.analyze_pdf("unused.pdf").status == "layout_unavailable"


def test_get_layout_analyzer_provider_names(monkeypatch):
    monkeypatch.delenv("LAYOUT_PROVIDER", raising=False)

    assert get_layout_analyzer().provider_name == "rule_based"
    assert get_layout_analyzer("doclayout-yolo").provider_name == "doclayout_yolo_onnx"
    assert get_layout_analyzer("unknown").provider_name == "none"


def test_invalid_model_score_threshold_env_uses_default(monkeypatch):
    monkeypatch.setenv("LAYOUT_MODEL_SCORE_THRESHOLD", "not-a-number")
    monkeypatch.delenv("LAYOUT_MODEL_PATH", raising=False)

    assert DocLayoutYoloOnnxLayoutAnalyzer().score_threshold == 0.25


def test_model_block_dedup_removes_contained_text_duplicate():
    parent = LayoutBlock(
        page_number=1,
        text="The Fourier Transform maps a signal into frequency components. It is used in signal processing.",
        bbox=BoundingBox(70, 118, 395, 156),
        layout_type="text",
        reading_order=1,
        page_width=612,
        page_height=792,
        provider="doclayout_yolo_onnx",
        confidence=0.29,
    )
    child = LayoutBlock(
        page_number=1,
        text="The Fourier Transform maps a signal into frequency components.",
        bbox=BoundingBox(71, 119, 393, 133),
        layout_type="text",
        reading_order=2,
        page_width=612,
        page_height=792,
        provider="doclayout_yolo_onnx",
        confidence=0.73,
    )

    blocks = layout_analysis._deduplicate_model_blocks([parent, child])

    assert len(blocks) == 1
    assert blocks[0].text == parent.text
    assert blocks[0].bbox == parent.bbox
    assert blocks[0].confidence == 0.73


def test_normalize_model_output_shapes():
    np = pytest.importorskip("numpy")

    detections = np.array([[1, 2, 30, 40, 0.9, 1]], dtype=np.float32)
    assert layout_analysis._normalize_model_output(detections[None, :, :], np).shape == (1, 6)
    assert layout_analysis._normalize_model_output(detections.T, np).shape == (1, 6)

    with pytest.raises(layout_analysis.UnsupportedModelOutput):
        layout_analysis._normalize_model_output(np.zeros((2, 3, 4, 5)), np)

    with pytest.raises(layout_analysis.UnsupportedModelOutput):
        layout_analysis._normalize_model_output(np.zeros((7, 7), dtype=np.float32), np)


def test_decode_raw_yolo_output_applies_nms():
    np = pytest.importorskip("numpy")
    class_count = len(layout_analysis.DOCLAYOUT_YOLO_CLASSES)
    prediction_count = 2
    predictions = np.zeros((prediction_count, 4 + class_count), dtype=np.float32)
    # Two nearly identical boxes; NMS must keep only the higher-scored one.
    predictions[0, :4] = [100, 100, 50, 40]
    predictions[0, 4 + 1] = 0.9
    predictions[1, :4] = [102, 101, 50, 40]
    predictions[1, 4 + 1] = 0.6

    decoded = layout_analysis._decode_raw_yolo_output(predictions, np)

    assert decoded.shape == (1, 6)
    assert decoded[0, 4] == pytest.approx(0.9)
    assert decoded[0, 5] == 1


def test_doclayout_onnx_with_real_model_smoke(tmp_path, monkeypatch):
    model_path = os.environ.get("LAYOUT_MODEL_PATH", "").strip()

    if not model_path:
        pytest.skip("Set LAYOUT_MODEL_PATH to run the real DocLayout-YOLO ONNX smoke test.")

    if not Path(model_path).exists():
        pytest.fail(f"LAYOUT_MODEL_PATH does not exist: {model_path}")

    pytest.importorskip("numpy")
    pytest.importorskip("onnxruntime")
    monkeypatch.setenv("LAYOUT_PROVIDER", "doclayout_yolo_onnx")
    pdf_path = _write_pdf(
        tmp_path / "real-model-smoke.pdf",
        lambda pdf: (
            _draw_line(pdf, 72, 766, "Course Notes", size=9),
            _draw_line(pdf, 72, 710, "Fourier Transform", size=18, font="Helvetica-Bold"),
            _draw_line(pdf, 72, 680, "Maps signals into frequency components.", size=11),
            _draw_line(pdf, 72, 630, "Hash Table", size=18, font="Helvetica-Bold"),
            _draw_line(pdf, 72, 600, "Stores key value pairs for fast lookup.", size=11),
            _draw_line(pdf, 280, 28, "Footer Marker", size=9),
        ),
    )

    result = parse_pdf_layout(pdf_path)
    text = layout_blocks_to_text(result.blocks)

    assert result.provider == "doclayout_yolo_onnx"
    assert result.needs_ocr_engine is False
    assert result.warnings == ()
    assert "Fourier Transform" in text
    assert "Hash Table" in text
    assert "Course Notes" not in text
    assert "Footer Marker" not in text
    assert len(text.split("Fourier Transform")) == 2
    assert len(text.split("Hash Table")) == 2
