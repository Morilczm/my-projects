"""Governed production contract for the optional Docling parser adapter."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services import (
    docling_parser_adapter,
    document_parse_quality,
    knowledge_governance,
    layout_analysis,
)


def _pdf(path: Path, draw) -> Path:
    document = canvas.Canvas(str(path), pagesize=letter)
    draw(document)
    document.save()
    return path


def _simple_pdf(path: Path) -> Path:
    return _pdf(
        path,
        lambda pdf: (
            pdf.setFont("Helvetica-Bold", 18),
            pdf.drawString(72, 720, "Electric charge"),
            pdf.setFont("Helvetica", 11),
            pdf.drawString(72, 690, "A physical property governing electrical interactions."),
        ),
    )


def _simple_table_pdf(path: Path) -> Path:
    def draw(pdf):
        pdf.setFont("Helvetica", 10)
        for x in (72, 220, 368):
            pdf.line(x, 640, x, 720)
        for y in (640, 680, 720):
            pdf.line(72, y, 368, y)
        pdf.drawString(82, 696, "Quantity")
        pdf.drawString(230, 696, "Unit")
        pdf.drawString(82, 656, "Charge")
        pdf.drawString(230, 656, "coulomb")

    return _pdf(path, draw)


def _two_column_pdf(path: Path) -> Path:
    def draw(pdf):
        pdf.setFont("Helvetica", 10)
        pdf.drawString(72, 720, "Left concept definition begins here.")
        pdf.drawString(72, 700, "It continues in the left column.")
        pdf.drawString(330, 720, "Right concept definition begins here.")
        pdf.drawString(330, 700, "It continues in the right column.")

    return _pdf(path, draw)


def _scanned_like_pdf(path: Path) -> Path:
    def draw(pdf):
        pdf.setFillColorRGB(0.1, 0.1, 0.1)
        pdf.rect(72, 640, 420, 90, stroke=0, fill=1)

    return _pdf(path, draw)


def test_document_class_router_keeps_simple_digital_pdf_on_native(tmp_path):
    decision = docling_parser_adapter.classify_pdf_for_docling(
        _simple_pdf(tmp_path / "simple.pdf")
    )

    assert decision.document_class == "simple_digital_pdf"
    assert decision.selected_provider == "rule_based"
    assert decision.docling_allowed is False
    assert "DOCLING_ROUTE_SIMPLE_NATIVE" in decision.reason_codes


def test_document_class_router_selects_docling_for_scanned_pdf(tmp_path):
    decision = docling_parser_adapter.classify_pdf_for_docling(
        _scanned_like_pdf(tmp_path / "scan.pdf")
    )

    assert decision.document_class == "scanned_pdf"
    assert decision.selected_provider == "docling"
    assert decision.docling_allowed is True
    assert "DOCLING_ROUTE_SCANNED_PDF" in decision.reason_codes


def test_document_class_router_selects_docling_for_simple_table(tmp_path):
    decision = docling_parser_adapter.classify_pdf_for_docling(
        _simple_table_pdf(tmp_path / "table.pdf")
    )

    assert decision.document_class == "simple_table_pdf"
    assert decision.selected_provider == "docling"
    assert decision.docling_allowed is True
    assert decision.diagnostics["table_signal"] is True


def test_document_class_router_excludes_multi_column_pdf(tmp_path):
    decision = docling_parser_adapter.classify_pdf_for_docling(
        _two_column_pdf(tmp_path / "columns.pdf")
    )

    assert decision.document_class == "multi_column_pdf"
    assert decision.selected_provider == "rule_based"
    assert decision.docling_allowed is False
    assert "DOCLING_ROUTE_MULTI_COLUMN_EXCLUDED" in decision.reason_codes


def test_adapter_requires_explicit_offline_runtime_and_model(tmp_path):
    adapter = docling_parser_adapter.DoclingParserAdapter(
        python_executable="python",
        model_root=str(tmp_path / "missing-model"),
    )

    result = adapter.analyze_pdf(_simple_pdf(tmp_path / "simple.pdf"))

    assert result.status == "layout_unavailable"
    assert result.reason_code == "DOCLING_RUNTIME_NOT_ABSOLUTE"
    assert result.blocks == ()


def test_adapter_invokes_bounded_worker_without_credentials_or_network(
    tmp_path, monkeypatch
):
    runtime = tmp_path / "docling-python"
    runtime.write_text("", encoding="utf-8")
    runtime.chmod(0o755)
    model_root = tmp_path / "models"
    model_root.mkdir()
    worker = tmp_path / "worker.py"
    worker.write_text("", encoding="utf-8")
    input_path = _simple_table_pdf(tmp_path / "table.pdf")
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "contract_version": "docling-layout-worker@1.0.0",
                    "status": "ok",
                    "parser_version": "2.117.0",
                    "page_count": 1,
                    "external_request_count": 0,
                    "blocks": [
                        {
                            "page_number": 1,
                            "text": "Charge | coulomb",
                            "bbox": {"x0": 72, "y0": 72, "x1": 368, "y1": 152},
                            "layout_type": "table",
                            "reading_order": 1,
                            "page_width": 612,
                            "page_height": 792,
                            "confidence": 1.0,
                        }
                    ],
                    "warnings": [],
                    "error_code": "",
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(docling_parser_adapter.subprocess, "run", fake_run)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-propagate")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-propagate")
    adapter = docling_parser_adapter.DoclingParserAdapter(
        python_executable=str(runtime),
        model_root=str(model_root),
        worker_path=str(worker),
        timeout_seconds=12,
    )

    result = adapter.analyze_pdf(input_path)

    assert result.status == "ok"
    assert result.parser_version == "2.117.0"
    assert result.blocks[0].layout_type == "table"
    assert observed["kwargs"]["shell"] is False
    assert observed["kwargs"]["timeout"] == 12
    assert observed["kwargs"]["env"]["HF_HUB_OFFLINE"] == "1"
    assert "DEEPSEEK_API_KEY" not in observed["kwargs"]["env"]
    assert "OPENAI_API_KEY" not in observed["kwargs"]["env"]


def test_adapter_fails_closed_on_network_or_invalid_provenance(tmp_path, monkeypatch):
    runtime = tmp_path / "docling-python"
    runtime.write_text("", encoding="utf-8")
    runtime.chmod(0o755)
    model_root = tmp_path / "models"
    model_root.mkdir()
    worker = tmp_path / "worker.py"
    worker.write_text("", encoding="utf-8")

    def fake_run(command, **kwargs):
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "contract_version": "docling-layout-worker@1.0.0",
                    "status": "ok",
                    "parser_version": "2.117.0",
                    "page_count": 1,
                    "external_request_count": 1,
                    "blocks": [{"page_number": 1, "text": "unsafe"}],
                    "warnings": [],
                    "error_code": "",
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(docling_parser_adapter.subprocess, "run", fake_run)
    adapter = docling_parser_adapter.DoclingParserAdapter(
        python_executable=str(runtime),
        model_root=str(model_root),
        worker_path=str(worker),
    )

    result = adapter.analyze_pdf(_simple_pdf(tmp_path / "input.pdf"))

    assert result.status == "failed"
    assert result.reason_code == "DOCLING_EXTERNAL_REQUEST_DETECTED"
    assert result.blocks == ()


def test_adapter_fails_closed_when_block_provenance_is_missing(tmp_path, monkeypatch):
    runtime = tmp_path / "docling-python"
    runtime.write_text("", encoding="utf-8")
    runtime.chmod(0o755)
    model_root = tmp_path / "models"
    model_root.mkdir()
    worker = tmp_path / "worker.py"
    worker.write_text("", encoding="utf-8")

    def fake_run(command, **kwargs):
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "contract_version": "docling-layout-worker@1.0.0",
                    "status": "ok",
                    "parser_version": "2.117.0",
                    "page_count": 1,
                    "external_request_count": 0,
                    "blocks": [{"page_number": 1, "text": "missing bbox"}],
                    "warnings": [],
                    "error_code": "",
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(docling_parser_adapter.subprocess, "run", fake_run)
    result = docling_parser_adapter.DoclingParserAdapter(
        python_executable=str(runtime),
        model_root=str(model_root),
        worker_path=str(worker),
    ).analyze_pdf(_simple_pdf(tmp_path / "input.pdf"))

    assert result.status == "failed"
    assert result.reason_code == "DOCLING_PROVENANCE_INVALID"
    assert result.blocks == ()


def test_adapter_blocks_file_above_configured_bound_before_transport(
    tmp_path, monkeypatch
):
    runtime = tmp_path / "docling-python"
    runtime.write_text("", encoding="utf-8")
    runtime.chmod(0o755)
    model_root = tmp_path / "models"
    model_root.mkdir()
    worker = tmp_path / "worker.py"
    worker.write_text("", encoding="utf-8")
    input_path = _simple_pdf(tmp_path / "input.pdf")
    monkeypatch.setenv("DOCLING_PARSER_MAX_FILE_BYTES", "1024")

    def forbidden(*args, **kwargs):
        raise AssertionError("transport must not run after a size denial")

    monkeypatch.setattr(docling_parser_adapter.subprocess, "run", forbidden)
    result = docling_parser_adapter.DoclingParserAdapter(
        python_executable=str(runtime),
        model_root=str(model_root),
        worker_path=str(worker),
    ).analyze_pdf(input_path)

    assert input_path.stat().st_size > 1024
    assert result.status == "layout_unavailable"
    assert result.reason_code == "DOCLING_INPUT_SIZE_EXCEEDED"


def test_conditional_layout_provider_routes_and_audits_docling(tmp_path, monkeypatch):
    input_path = _simple_table_pdf(tmp_path / "table.pdf")

    class FakeAdapter:
        def analyze_pdf(self, path):
            return docling_parser_adapter.DoclingAdapterResult(
                status="ok",
                parser_version="2.117.0",
                page_count=1,
                blocks=(
                    docling_parser_adapter.DoclingAdapterBlock(
                        page_number=1,
                        text="Charge | coulomb",
                        bbox=(72.0, 72.0, 368.0, 152.0),
                        layout_type="table",
                        reading_order=1,
                        page_width=612.0,
                        page_height=792.0,
                        confidence=1.0,
                    ),
                ),
            )

    monkeypatch.setattr(layout_analysis, "DoclingParserAdapter", FakeAdapter)

    result = layout_analysis.parse_pdf_layout(
        str(input_path), provider="conditional_docling"
    )

    assert result.ok
    assert result.provider == "docling"
    assert result.blocks[0].layout_type == "table"
    assert "docling_policy_conditional_docling_parser_1_0_0" in result.quality_flags
    assert "docling_route_simple_table_pdf" in result.quality_flags


def test_conditional_provider_falls_back_to_rule_based_on_adapter_failure(
    tmp_path, monkeypatch
):
    input_path = _simple_table_pdf(tmp_path / "table.pdf")

    class FakeAdapter:
        def analyze_pdf(self, path):
            return docling_parser_adapter.DoclingAdapterResult(
                status="failed", reason_code="DOCLING_TIMEOUT"
            )

    monkeypatch.setattr(layout_analysis, "DoclingParserAdapter", FakeAdapter)

    result = layout_analysis.parse_pdf_layout(
        str(input_path), provider="conditional_docling"
    )

    assert result.ok
    assert result.provider == "rule_based"
    assert "docling_fallback:DOCLING_TIMEOUT" in result.warnings
    assert "docling_fallback_rule_based" in result.quality_flags


def test_environment_cannot_bypass_conditional_route_with_direct_docling(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LAYOUT_PROVIDER", "docling")

    class ForbiddenAdapter:
        def __init__(self):
            raise AssertionError("direct environment selection must be rejected")

    monkeypatch.setattr(layout_analysis, "DoclingParserAdapter", ForbiddenAdapter)
    result = document_parse_quality.parse_document_with_quality(
        str(_two_column_pdf(tmp_path / "columns.pdf")), filename="columns.pdf"
    )

    assert result.parse_record_data["parser_name"] == "pymupdf_layout_rule_based"
    assert "docling_conditional_policy_required" in result.parse_record_data["quality_flags"]
    assert "docling_direct_provider_rejected" in result.parse_record_data["warnings"]


def test_production_quality_router_preserves_native_for_simple_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "conditional_docling")

    result = document_parse_quality.parse_document_with_quality(
        str(_simple_pdf(tmp_path / "simple.pdf")), filename="simple.pdf"
    )

    assert result.parse_record_data["parser_name"] == "pymupdf_native"
    assert "docling_route_simple_native" in result.parse_record_data["quality_flags"]
    assert "layout_applied" not in result.parse_record_data["quality_flags"]


def test_production_docling_table_flows_into_existing_knowledge_chunk(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LAYOUT_PROVIDER", "conditional_docling")

    class FakeAdapter:
        def analyze_pdf(self, path):
            return docling_parser_adapter.DoclingAdapterResult(
                status="ok",
                parser_version="2.117.0",
                page_count=1,
                blocks=(
                    docling_parser_adapter.DoclingAdapterBlock(
                        page_number=1,
                        text="Electric quantity table",
                        bbox=(72.0, 72.0, 368.0, 152.0),
                        layout_type="title",
                        reading_order=1,
                        page_width=612.0,
                        page_height=792.0,
                    ),
                    docling_parser_adapter.DoclingAdapterBlock(
                        page_number=1,
                        text="Charge | coulomb",
                        bbox=(72.0, 160.0, 368.0, 240.0),
                        layout_type="table",
                        reading_order=2,
                        page_width=612.0,
                        page_height=792.0,
                    ),
                ),
            )

    monkeypatch.setattr(layout_analysis, "DoclingParserAdapter", FakeAdapter)
    result = document_parse_quality.parse_document_with_quality(
        str(_simple_table_pdf(tmp_path / "table.pdf")), filename="table.pdf"
    )
    chunks = knowledge_governance.build_knowledge_chunks_from_parse_blocks(
        SimpleNamespace(**result.parse_record_data),
        [SimpleNamespace(**block) for block in result.blocks],
        "source-docling-table",
        {"language": "en", "course": "Synthetic Physics"},
    )

    assert result.parse_record_data["parser_name"] == "docling_layout"
    assert result.parse_record_data["parser_version"] == "parse_quality_v1+docling@2.117.0"
    assert result.parse_record_data["table_detected"] is True
    assert any(block["block_type"] == "table" for block in result.blocks)
    assert all("bbox:" in block["source_locator"] for block in result.blocks)
    assert chunks
    assert "Charge | coulomb" in chunks[0]["text"]
    assert "layout_provider_docling" in chunks[0]["quality_flags"]


def test_docling_route_keeps_existing_formula_region_composition(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "conditional_docling")

    class FakeAdapter:
        def analyze_pdf(self, path):
            return docling_parser_adapter.DoclingAdapterResult(
                status="ok",
                parser_version="2.117.0",
                page_count=1,
                blocks=(
                    docling_parser_adapter.DoclingAdapterBlock(
                        page_number=1,
                        text="Charge | coulomb",
                        bbox=(72.0, 72.0, 368.0, 152.0),
                        layout_type="table",
                        reading_order=1,
                        page_width=612.0,
                        page_height=792.0,
                    ),
                ),
            )

    formula_region = SimpleNamespace(page_number=1, region_uid="formula-region-1")
    monkeypatch.setattr(layout_analysis, "DoclingParserAdapter", FakeAdapter)
    monkeypatch.setattr(
        document_parse_quality,
        "detect_pdf_formula_regions",
        lambda path: [formula_region],
    )

    result = document_parse_quality.parse_document_with_quality(
        str(_simple_table_pdf(tmp_path / "formula-table.pdf")),
        filename="formula-table.pdf",
    )

    assert result.formula_regions == [formula_region]
    assert result.parse_record_data["formula_detected"] is True
    assert "formula_region_detected" in result.parse_record_data["quality_flags"]


def test_docling_scanned_route_records_ocr_without_reinvoking_tesseract(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LAYOUT_PROVIDER", "conditional_docling")
    monkeypatch.setenv("OCR_PROVIDER", "none")

    class FakeAdapter:
        def analyze_pdf(self, path):
            return docling_parser_adapter.DoclingAdapterResult(
                status="ok",
                parser_version="2.117.0",
                page_count=1,
                blocks=(
                    docling_parser_adapter.DoclingAdapterBlock(
                        page_number=1,
                        text="Scanned electric charge definition",
                        bbox=(72.0, 72.0, 368.0, 152.0),
                        layout_type="text",
                        reading_order=1,
                        page_width=612.0,
                        page_height=792.0,
                    ),
                ),
            )

    monkeypatch.setattr(layout_analysis, "DoclingParserAdapter", FakeAdapter)
    result = document_parse_quality.parse_document_with_quality(
        str(_scanned_like_pdf(tmp_path / "scan.pdf")), filename="scan.pdf"
    )

    assert result.parse_record_data["parser_name"] == "docling_layout"
    assert result.parse_record_data["quality_status"] == "ocr_text_ok"
    assert result.parse_record_data["ocr_required"] is True
    assert result.parse_record_data["ocr_available"] is False
    assert "docling_ocr_completed" in result.parse_record_data["quality_flags"]
    assert "tesseract" not in result.parse_record_data["parser_name"]
