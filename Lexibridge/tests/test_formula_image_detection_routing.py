import json
from pathlib import Path

import pytest

from scripts import run_mainline_core_capability_acceptance as acceptance
from services import document_parse_quality, formula_detection, ocr


def _fixture_pdf(tmp_path: Path, fixture_id: str) -> Path:
    fixtures = {fixture.fixture_id: fixture for fixture in acceptance.build_fixture_set(tmp_path / "fixtures")}
    return fixtures[fixture_id].path


def _write_image_pdf(path: Path, image_specs: list[tuple[str, list[str], tuple[int, int, int, int]]]) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    document = canvas.Canvas(str(path), pagesize=letter)
    for index, (kind, lines, box) in enumerate(image_specs, start=1):
        image_path = path.with_name(f"{path.stem}-{index}.png")
        image = Image.new("RGB", (900, 240), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        if kind == "plain":
            draw.rectangle((40, 40, 860, 200), outline="black", width=4)
            draw.line((40, 40, 860, 200), fill="gray", width=3)
        else:
            y = 40
            for line in lines:
                draw.text((48, y), line, fill="black", font=font)
                y += 64
        image.save(image_path)
        x, y, width, height = box
        document.drawImage(ImageReader(str(image_path)), x, y, width=width, height=height)
    document.save()


def test_formula_region_contract_serializes_without_recognition_success():
    region = formula_detection.FormulaRegion(
        formula_region_uid="region-1",
        source_uid="source-a",
        document_uid="document-a",
        page_number=2,
        bounding_box={"x": 10, "y": 20, "width": 300, "height": 90},
        region_image_hash="a" * 64,
        detection_method="pdf_raster_image_formula_heuristic",
        detection_confidence=0.82,
        surrounding_text_refs=["page:2;block:1"],
        source_page_ref="page:2",
        recognizer_status="FORMULA_RECOGNIZER_UNAVAILABLE",
        recognizer_provider="none",
        recognizer_model="none",
        recognition_confidence=None,
        latex_candidate="",
        mathml_candidate="",
        abstention_reason="Formula recognizer is not configured.",
        provenance={"render_dpi": 180},
        created_at="2026-07-30T00:00:00Z",
    )

    payload = region.to_safe_dict()

    assert payload["formula_region_uid"] == "region-1"
    assert payload["recognizer_status"] == "FORMULA_RECOGNIZER_UNAVAILABLE"
    assert payload["latex_candidate"] == ""
    assert payload["mathml_candidate"] == ""
    assert payload["bounding_box"]["width"] == 300
    assert "image_path" not in payload


def test_formula_detector_finds_raster_formula_region_and_provenance(tmp_path):
    pdf_path = _fixture_pdf(tmp_path, "formula-image")

    regions = formula_detection.detect_pdf_formula_regions(str(pdf_path), surrounding_text_refs=["page:1;block:1"])

    assert regions
    region = regions[0]
    assert region.page_number == 1
    assert region.region_image_hash
    assert region.bounding_box["width"] > 0
    assert region.bounding_box["height"] > 0
    assert region.detection_method == "pdf_raster_image_formula_heuristic"
    assert region.recognizer_status == "FORMULA_RECOGNIZER_UNAVAILABLE"
    assert region.surrounding_text_refs == ["page:1;block:1"]


def test_formula_detector_rejects_plain_scanned_text_and_born_digital_text(tmp_path):
    scanned_text = _fixture_pdf(tmp_path, "scanned-english")
    born_digital = _fixture_pdf(tmp_path, "born-digital-text")
    plain_image = tmp_path / "fixtures" / "plain-image.pdf"
    _write_image_pdf(plain_image, [("plain", [], (72, 300, 300, 100))])

    assert formula_detection.detect_pdf_formula_regions(str(scanned_text)) == []
    assert formula_detection.detect_pdf_formula_regions(str(born_digital)) == []
    assert formula_detection.detect_pdf_formula_regions(str(plain_image)) == []


def test_formula_detector_handles_multiple_formula_images(tmp_path):
    multi_pdf = tmp_path / "fixtures" / "multi-formula.pdf"
    _write_image_pdf(
        multi_pdf,
        [
            ("formula", ["H(s) = int h(t)e^{-st} dt", "alpha_i = beta_i / gamma_i"], (72, 420, 360, 95)),
            ("formula", ["V_out = V_in * R2 / (R1 + R2)", "x_i^2 + y_i^2 = r^2"], (96, 250, 360, 95)),
        ],
    )

    regions = formula_detection.detect_pdf_formula_regions(str(multi_pdf))

    assert len(regions) == 2
    assert all(region.region_image_hash for region in regions)
    assert [region.source_page_ref for region in regions] == ["page:1", "page:1"]


def test_formula_recognizer_unavailable_and_fake_contract(tmp_path):
    region = formula_detection.FormulaRegion(
        formula_region_uid="region-1",
        document_uid="document-a",
        page_number=1,
        bounding_box={"x": 1, "y": 2, "width": 3, "height": 4},
        region_image_hash="b" * 64,
        detection_method="test",
        detection_confidence=0.9,
        source_page_ref="page:1",
    )

    unavailable = formula_detection.UnavailableFormulaRecognizer().recognize(region)
    fake = formula_detection.DeterministicTestFormulaRecognizer({"region-1": "\\\\frac{1}{2}"}).recognize(region)
    malformed = formula_detection.DeterministicTestFormulaRecognizer({"region-1": {"unexpected": "shape"}}).recognize(region)
    timeout = formula_detection.DeterministicTestFormulaRecognizer({"region-1": "__TIMEOUT__"}).recognize(region)

    assert unavailable.status == "FORMULA_RECOGNIZER_UNAVAILABLE"
    assert unavailable.abstention_reason
    assert fake.status == "FORMULA_RECOGNIZED_BY_TEST_FAKE"
    assert fake.latex_candidate == "\\\\frac{1}{2}"
    assert malformed.status == "FORMULA_RECOGNIZER_MALFORMED_RESULT"
    assert timeout.status == "FORMULA_RECOGNIZER_TIMEOUT"


def test_upload_persists_formula_region_without_latex_or_formal_item_pollution(app_module, client, teacher_token, test_course, tmp_path):
    app_module.FORMULA_OCR_PROVIDER = "none"
    fixture_path = _fixture_pdf(tmp_path, "formula-image")
    with fixture_path.open("rb") as handle:
        response = client.post(
            "/api/documents/upload?sync=true",
            headers={"Authorization": f"Bearer {teacher_token}"},
            data={
                "scope_type": "course",
                "course_id": str(test_course.id),
                "language": "en",
                "source_type": "course_material",
                "file": (handle, "formula-image.pdf"),
            },
            content_type="multipart/form-data",
        )

    assert response.status_code == 200
    payload = response.get_json()
    payload = payload.get("data", payload)
    assert payload["formula_status"] == "FORMULA_RECOGNIZER_UNAVAILABLE"
    assert payload["formula_blocks_created"] == 1
    block = payload["formula_blocks"][0]
    assert block["formula_region_uid"]
    assert block["status"] == "FORMULA_RECOGNIZER_UNAVAILABLE"
    assert block["latex"] == ""
    assert block["plain_text"] == ""
    assert block["bbox"]
    assert block["image_sha256"]
    assert "FormulaBlock" not in json.dumps(payload["cards"], ensure_ascii=False)


class _DeterministicAcceptanceOCRProvider:
    provider_name = "deterministic-acceptance-ocr"

    def is_available(self):
        return True

    def supports_language(self, language=""):
        return True

    def recognize_image(self, image_path, language=""):
        return ocr.OCRTextResult(
            status="ok",
            text=(
                "Fourier Transform Laplace Transform Impulse Response Convolution "
                "Voltage Divider Operational Amplifier Equivalent Resistance "
                "Boundary Condition Eigenvalue Time Complexity "
                "傅里叶变换 拉普拉斯变换 冲激响应 卷积 分压器 运算放大器 "
                "等效电阻 边界条件 特征值 时间复杂度"
            ),
            confidence=100,
            provider=self.provider_name,
            language=language or "mixed",
            blocks=[
                {
                    "text": "Deterministic synthetic OCR fixture",
                    "confidence": 100,
                    "page_number": 1,
                    "bbox": [0, 0, 100, 20],
                }
            ],
        )


@pytest.mark.parametrize("host_tesseract_available", [False, True])
def test_acceptance_recheck_reports_formula_region_detection_without_recognition(
    monkeypatch,
    tmp_path,
    host_tesseract_available,
):
    discovery = ocr.TesseractExecutableDiscovery(
        executable_path="synthetic-tesseract" if host_tesseract_available else "",
        discovery_source="path" if host_tesseract_available else "not_found",
        safe_error_code=None if host_tesseract_available else "TESSERACT_EXECUTABLE_NOT_FOUND",
    )
    monkeypatch.setattr(ocr, "discover_tesseract_executable", lambda **kwargs: discovery)
    monkeypatch.setattr(ocr, "get_ocr_provider", lambda *args, **kwargs: _DeterministicAcceptanceOCRProvider())
    monkeypatch.setattr(
        document_parse_quality,
        "get_ocr_provider",
        lambda *args, **kwargs: _DeterministicAcceptanceOCRProvider(),
    )
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
    assert formula["formula"]["formula_image_expected"] is True
    assert formula["formula"]["formula_image_detected"] is True
    assert formula["formula"]["formula_text_recognized"] is False
    assert formula["formula"]["formula_statuses"] == ["FORMULA_RECOGNIZER_UNAVAILABLE"]
    assert formula["formula"]["formula_detection_methods"] == ["pdf_raster_image_formula_heuristic"]
    assert formula["formula"]["formula_region_hashes_present"] is True
    assert formula["formula"]["formula_provenance_present"] is True
    assert result["final_status"] == "BILINGUAL_EVIDENCE_PIPELINE_BLOCKS_MAINLINE"
