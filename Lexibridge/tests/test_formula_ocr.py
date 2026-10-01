from io import BytesIO

from services.formula_ocr import get_formula_ocr_provider


def test_formula_ocr_none_and_mock_do_not_fabricate_latex():
    none_result = get_formula_ocr_provider("none").recognize_formula("formula.png")
    assert none_result.status == "needs_formula_ocr_engine"
    assert none_result.latex == ""

    mock_result = get_formula_ocr_provider("mock").recognize_formula("formula.png")
    assert mock_result.status == "needs_formula_ocr_engine"
    assert mock_result.latex == ""


def test_formula_image_creates_formula_block_without_terms(app_module, client, teacher_token, test_course, tiny_png_bytes):
    app_module.OCR_PROVIDER = "mock"
    app_module.FORMULA_OCR_PROVIDER = "none"
    response = client.post(
        "/api/documents/upload?sync=true",
        headers={"Authorization": f"Bearer {teacher_token}"},
        data={
            "scope_type": "course",
            "course_id": str(test_course.id),
            "language": "bilingual",
            "file": (BytesIO(tiny_png_bytes), "formula_equation.png")
        },
        content_type="multipart/form-data"
    )
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["cards"] == []
    assert payload["formula_status"] == "needs_formula_ocr_engine"
    assert len(payload["formula_blocks"]) == 1
    block = payload["formula_blocks"][0]
    assert block["document_id"]
    assert block["page_number"] == 1
    assert block["status"] == "needs_formula_ocr_engine"
    assert block["provider"] == "none"
    assert block["latex"] == ""


def test_formula_placeholders_and_latex_are_not_terms(app_module):
    text = "[FormulaBlock #12]\n\\frac{1}{2} + sqrt(x) = e^{-x^2}\nFourier Transform converts signals."
    terms = app_module.extract_terms_from_text(text)
    extracted = {item["english_term"].lower() for item in terms}
    assert "frac" not in extracted
    assert "sqrt" not in extracted
    assert "x^2" not in extracted
    assert "e" not in extracted
