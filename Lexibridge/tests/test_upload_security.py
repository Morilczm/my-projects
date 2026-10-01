from io import BytesIO


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def upload(client, token, filename, content, **fields):
    data = {
        "file": (BytesIO(content), filename),
        **fields,
    }
    return client.post(
        "/api/documents/upload?sync=true",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header(token),
    )


def test_allowed_text_upload_succeeds_and_uses_safe_filename(client, app_module, student_token):
    response = upload(
        client,
        student_token,
        "../../private-notes.txt",
        b"Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        scope_type="personal",
        language="en",
    )

    assert response.status_code == 200
    with app_module.app.app_context():
        document = app_module.Document.query.order_by(app_module.Document.id.desc()).first()
        assert document is not None
        assert ".." not in document.filename
        assert "/" not in document.filename
        assert document.saved_filename.startswith("document_")


def test_dangerous_extensions_are_rejected(client, student_token):
    for extension in ["exe", "bat", "sh", "js", "html", "php", "docm", "xlsm", "zip"]:
        response = upload(
            client,
            student_token,
            f"payload.{extension}",
            b"not a teaching file",
            scope_type="personal",
        )
        assert response.status_code == 415, extension
        assert response.get_json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_file_too_large_returns_413(client, app_module, student_token):
    previous_limit = app_module.app.config.get("MAX_CONTENT_LENGTH")
    app_module.app.config["MAX_CONTENT_LENGTH"] = 10
    try:
        response = upload(
            client,
            student_token,
            "large.txt",
            b"x" * 1024,
            scope_type="personal",
        )
    finally:
        app_module.app.config["MAX_CONTENT_LENGTH"] = previous_limit

    assert response.status_code == 413
    assert response.get_json()["error_code"] == "FILE_TOO_LARGE"


def test_extension_spoofing_is_rejected(client, student_token):
    response = upload(
        client,
        student_token,
        "spoofed.pdf",
        b"This is plain text with a fake pdf extension.",
        scope_type="personal",
    )

    assert response.status_code == 415
    assert response.get_json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_rejected_upload_does_not_create_cards(client, app_module, student_token):
    with app_module.app.app_context():
        before = app_module.TerminologyCard.query.count()
    response = upload(
        client,
        student_token,
        "blocked.exe",
        b"Fourier Transform",
        scope_type="personal",
    )
    with app_module.app.app_context():
        after = app_module.TerminologyCard.query.count()

    assert response.status_code == 415
    assert after == before


def test_png_with_ocr_unavailable_returns_422_not_500(client, student_token, tiny_png_bytes):
    response = upload(
        client,
        student_token,
        "scan.png",
        tiny_png_bytes,
        scope_type="personal",
        language="bilingual",
    )

    assert response.status_code == 422
    assert response.get_json()["error_code"] in {"OCR_UNAVAILABLE", "PARSING_FAILED"}


def test_formula_ocr_unavailable_path_returns_structured_error(client, app_module, student_token, tiny_png_bytes):
    previous = app_module.os.environ.get("FORMULA_OCR_PROVIDER")
    app_module.os.environ["FORMULA_OCR_PROVIDER"] = "none"
    try:
        response = upload(
            client,
            student_token,
            "formula.png",
            tiny_png_bytes,
            scope_type="personal",
            language="en",
        )
    finally:
        if previous is None:
            app_module.os.environ.pop("FORMULA_OCR_PROVIDER", None)
        else:
            app_module.os.environ["FORMULA_OCR_PROVIDER"] = previous

    assert response.status_code in {200, 422}
    if response.status_code == 422:
        assert response.get_json()["error_code"] in {"OCR_UNAVAILABLE", "FORMULA_OCR_UNAVAILABLE", "PARSING_FAILED"}
