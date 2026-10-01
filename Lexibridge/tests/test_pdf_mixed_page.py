from services.ocr import OCRTextResult


class FakeOCRProvider:
    provider_name = "fake"

    def recognize_image(self, image_path, language=""):
        return OCRTextResult(
            status="ok",
            text="Embedded region text E = mc^2",
            confidence=88,
            provider="fake",
            language=language
        )


def test_mixed_pdf_processes_digital_text_and_image_regions(app_module, monkeypatch, tmp_path, tiny_png_bytes):
    import fitz

    pdf_path = tmp_path / "mixed.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    page.insert_text((72, 72), "Fourier Transform converts a time-domain signal.")
    page.insert_image(fitz.Rect(72, 130, 240, 220), stream=tiny_png_bytes)
    doc.save(str(pdf_path))
    doc.close()

    app_module.OCR_PROVIDER = "fake"
    app_module.FORMULA_OCR_PROVIDER = "none"
    app_module.PDF_MIXED_PAGE_IMAGE_OCR = True
    app_module.OCR_ENABLE_REGION_EXTRACTION = True
    app_module.PDF_IMAGE_MIN_WIDTH = 10
    app_module.PDF_IMAGE_MIN_HEIGHT = 10
    monkeypatch.setattr(app_module, "get_ocr_provider", lambda *args, **kwargs: FakeOCRProvider())

    chunks, parsed_text, ocr_required, ocr_meta, formula_blocks = app_module.extract_document_chunks(
        str(pdf_path),
        language="en",
        source_type="test",
        document_id=999
    )

    contents = "\n".join(chunk["content"] for chunk in chunks)
    assert "Fourier Transform" in contents
    assert "Embedded region text" in contents
    assert ocr_required is True
    assert ocr_meta["ocr_status"] == "ok"
    assert formula_blocks
    assert formula_blocks[0]["status"] == "needs_formula_ocr_engine"
    assert "OCR_REQUIRED" not in contents
    assert app_module.extract_terms_from_text("[FormulaBlock #1]\n\\sqrt{x}") == []
