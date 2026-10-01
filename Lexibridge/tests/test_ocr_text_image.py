from io import BytesIO

from services.ocr import MockOCRProvider, TesseractOCRProvider, get_ocr_provider


def test_ocr_provider_none_and_mock_do_not_fabricate_text(tiny_png_bytes):
    none_result = get_ocr_provider("none").recognize_image("missing.png", language="bilingual")
    assert none_result.status == "ocr_unavailable"
    assert none_result.text == ""

    mock_result = MockOCRProvider().recognize_image("missing.png", language="zh")
    assert mock_result.status == "ocr_unavailable"
    assert mock_result.text == ""


def test_tesseract_unavailable_returns_clear_status(monkeypatch, tiny_png_bytes):
    monkeypatch.setenv("OCR_LANGS", "eng+chi_sim")
    monkeypatch.delenv("LEXIBRIDGE_TESSERACT_CMD", raising=False)
    monkeypatch.setattr("services.ocr.shutil.which", lambda _: None)
    provider = TesseractOCRProvider()
    result = provider.recognize_image("missing.png", language="en")
    assert result.status == "ocr_unavailable"
    assert "Tesseract" in result.error
    assert provider.ocr_langs == "eng+chi_sim"


def test_image_upload_with_no_ocr_returns_422_and_no_cards(app_module, client, teacher_token, test_course, tiny_png_bytes):
    app_module.OCR_PROVIDER = "none"
    app_module.FORMULA_OCR_PROVIDER = "none"
    response = client.post(
        "/api/documents/upload?sync=true",
        headers={"Authorization": f"Bearer {teacher_token}"},
        data={
            "scope_type": "course",
            "course_id": str(test_course.id),
            "language": "bilingual",
            "file": (BytesIO(tiny_png_bytes), "scan.png")
        },
        content_type="multipart/form-data"
    )
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["cards"] == []
    assert payload["document"]["ocr_status"] in {"ocr_unavailable", "empty_result"}
    assert "OCR_REQUIRED" not in str(payload)
