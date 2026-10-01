"""Tests for wiring layout analysis into the document parse pipeline."""

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services import document_parse_quality
from services.document_parse_quality import parse_document_with_quality


def _write_pdf(path, draw):
    pdf = canvas.Canvas(str(path), pagesize=letter)
    draw(pdf)
    pdf.save()
    return path


def _draw_line(pdf, x, y, text, size=11, font="Helvetica"):
    pdf.setFont(font, size)
    pdf.drawString(x, y, text)


def _header_footer_pdf(path):
    return _write_pdf(
        path,
        lambda pdf: (
            _draw_line(pdf, 72, 766, "Course Notes", size=9),
            _draw_line(pdf, 72, 710, "Fourier Transform", size=18, font="Helvetica-Bold"),
            _draw_line(pdf, 72, 680, "Maps signals into frequency components.", size=11),
            _draw_line(pdf, 280, 28, "Footer Marker 1", size=9),
        ),
    )


def test_layout_disabled_by_default_preserves_native_path(tmp_path, monkeypatch):
    monkeypatch.delenv("LAYOUT_PROVIDER", raising=False)
    pdf_path = _header_footer_pdf(tmp_path / "plain.pdf")

    result = parse_document_with_quality(str(pdf_path), filename="plain.pdf")

    record = result.parse_record_data
    assert record["parser_name"] == "pymupdf_native"
    assert "layout_applied" not in record["quality_flags"]
    assert record["parse_status"] == "success"


def test_rule_based_layout_filters_header_footer(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")
    pdf_path = _header_footer_pdf(tmp_path / "layout.pdf")

    result = parse_document_with_quality(str(pdf_path), filename="layout.pdf")

    record = result.parse_record_data
    assert record["parser_name"] == "pymupdf_layout_rule_based"
    assert record["parse_status"] == "success"
    assert "layout_applied" in record["quality_flags"]
    assert "layout_provider_rule_based" in record["quality_flags"]
    assert "Fourier Transform" in result.raw_text
    assert "Course Notes" not in result.raw_text
    assert "Footer Marker 1" not in result.raw_text


def test_rule_based_layout_orders_two_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")
    pdf_path = _write_pdf(
        tmp_path / "two-column.pdf",
        lambda pdf: (
            _draw_line(pdf, 72, 720, "Left column first.", size=11),
            _draw_line(pdf, 72, 700, "Left column second.", size=11),
            _draw_line(pdf, 330, 720, "Right column first.", size=11),
            _draw_line(pdf, 330, 700, "Right column second.", size=11),
        ),
    )

    result = parse_document_with_quality(str(pdf_path), filename="two-column.pdf")

    assert result.raw_text.index("Left column first") < result.raw_text.index("Right column first")
    assert result.raw_text.index("Left column second") < result.raw_text.index("Right column second")


def test_layout_blocks_carry_layout_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")
    pdf_path = _header_footer_pdf(tmp_path / "blocks.pdf")

    result = parse_document_with_quality(str(pdf_path), filename="blocks.pdf")

    assert result.blocks
    for block in result.blocks:
        assert block["parser_type"] == "layout_rule_based"
        assert "bbox:" in block["source_locator"]
        assert "layout" in block["quality_flags"]
        assert any(flag.startswith("layout_type_") for flag in block["quality_flags"])
    assert any(block["block_type"] == "title" for block in result.blocks)


def test_layout_failure_falls_back_to_native(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")

    def _boom(path):
        raise RuntimeError("layout exploded")

    monkeypatch.setattr(document_parse_quality, "parse_pdf_layout", _boom)
    pdf_path = _header_footer_pdf(tmp_path / "fallback.pdf")

    result = parse_document_with_quality(str(pdf_path), filename="fallback.pdf")

    record = result.parse_record_data
    assert record["parse_status"] == "success"
    assert record["parser_name"] == "pymupdf_native"
    assert "layout_fallback_native" in record["warnings"]
    assert "Fourier Transform" in result.raw_text


def test_unknown_layout_provider_degrades_without_breaking_parse(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "not-a-real-provider")
    pdf_path = _header_footer_pdf(tmp_path / "unknown.pdf")

    result = parse_document_with_quality(str(pdf_path), filename="unknown.pdf")

    record = result.parse_record_data
    assert record["parse_status"] == "success"
    assert record["parser_name"] == "pymupdf_layout_rule_based"
    assert any("unknown_layout_provider" in warning for warning in record["warnings"])


def test_blank_pdf_with_layout_still_requires_ocr(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")
    monkeypatch.setenv("OCR_PROVIDER", "none")
    pdf_path = _write_pdf(tmp_path / "blank.pdf", lambda pdf: pdf.showPage())

    result = parse_document_with_quality(str(pdf_path), filename="blank.pdf")

    record = result.parse_record_data
    assert record["parse_status"] == "failed"
    assert record["quality_status"] == "ocr_unavailable"
    assert record["ocr_required"] is True
    assert "layout_applied" in record["quality_flags"]
