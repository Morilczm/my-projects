from io import BytesIO

import pytest

from services import document_parse_quality


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def upload_parse_test(client, token, filename, content, request_id="doc-parse-test-request-id"):
    return client.post(
        "/api/document-parses/test",
        data={"file": (BytesIO(content), filename)},
        content_type="multipart/form-data",
        headers={**bearer(token), "X-Request-ID": request_id},
    )


def test_document_parse_tables_accept_record_and_block(app_module):
    with app_module.app.app_context():
        record = app_module.DocumentParseRecord(
            source_filename="quality.txt",
            file_type="txt",
            parser_name="native_text",
            parser_version="test",
            parse_status="success",
            quality_status="native_text_ok",
            quality_flags=["native_text_ok"],
            block_count=1,
            extracted_text_chars=12,
            warnings=["minor_warning"],
        )
        app_module.db.session.add(record)
        app_module.db.session.flush()
        block = app_module.DocumentParseBlock(
            parse_uid=record.parse_uid,
            block_index=1,
            block_type="text",
            text="hello world",
            confidence=1.0,
            parser_type="native",
            source_locator="block:1",
            quality_flags=["native_text_ok"],
        )
        app_module.db.session.add(block)
        app_module.db.session.commit()

        serialized = document_parse_quality.serialize_parse_record(record)
        serialized_block = document_parse_quality.serialize_parse_block(block)
        assert serialized["quality_flags"] == ["native_text_ok"]
        assert serialized["warnings"] == ["minor_warning"]
        assert serialized_block["quality_flags"] == ["native_text_ok"]


def test_non_empty_txt_is_native_text_ok(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Fourier Transform converts signals into frequency-domain representation.", encoding="utf-8")

    result = document_parse_quality.parse_document_with_quality(str(path), filename="notes.txt")

    assert result.parse_record_data["quality_status"] == "native_text_ok"
    assert result.parse_record_data["parse_status"] == "success"
    assert result.parse_record_data["block_count"] == 1
    assert document_parse_quality.should_allow_term_extraction(result.parse_record_data) is True


def test_empty_txt_is_empty_text(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    result = document_parse_quality.parse_document_with_quality(str(path), filename="empty.txt")

    assert result.parse_record_data["quality_status"] == "empty_text"
    assert result.parse_record_data["parse_status"] == "failed"
    assert document_parse_quality.should_allow_term_extraction(result.parse_record_data) is False


def test_unsupported_file_type_is_blocked(tmp_path):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"not course text")

    result = document_parse_quality.parse_document_with_quality(str(path), filename="payload.bin")

    assert result.parse_record_data["quality_status"] == "unsupported_file_type"
    assert result.parse_record_data["error_code"] == "unsupported_file_type"
    assert document_parse_quality.should_allow_term_extraction(result.parse_record_data) is False


def test_image_like_pdf_without_ocr_is_ocr_unavailable(monkeypatch, tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n% test\n")

    def fake_pdf_parser(file_path):
        return "", [], {"page_count": 1, "image_only_suspected": True, "partial_text": False}

    monkeypatch.setattr(document_parse_quality, "_parse_pdf_native", fake_pdf_parser)
    result = document_parse_quality.parse_document_with_quality(str(path), filename="scan.pdf", ocr_provider_name="none")

    assert result.parse_record_data["quality_status"] == "ocr_unavailable"
    assert result.parse_record_data["ocr_required"] is True
    assert result.parse_record_data["ocr_available"] is False
    assert document_parse_quality.should_allow_term_extraction(result.parse_record_data) is False


def test_parser_exception_is_parse_failed(monkeypatch, tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\n% broken\n")

    def broken_parser(file_path):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(document_parse_quality, "_parse_pdf_native", broken_parser)
    result = document_parse_quality.parse_document_with_quality(str(path), filename="broken.pdf")

    assert result.parse_record_data["quality_status"] == "parse_failed"
    assert result.parse_record_data["error_code"] == "parse_failed"
    assert "parser exploded" in result.parse_record_data["error_message"]
    assert document_parse_quality.should_allow_term_extraction(result.parse_record_data) is False


def test_document_parse_api_records_txt_success(client, teacher_token):
    request_id = "doc-parse-api-success-request-id"
    response = upload_parse_test(
        client,
        teacher_token,
        "api-notes.txt",
        b"Hash Table stores key value pairs for efficient lookup.",
        request_id=request_id,
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    record = payload["data"]["parse_record"]
    assert payload["request_id"] == request_id
    assert record["quality_status"] == "native_text_ok"
    assert record["allow_term_extraction"] is True
    assert payload["data"]["blocks"][0]["parser_type"] == "native"
    audit_response = client.get(f"/api/audit-records?request_id={request_id}", headers=bearer(teacher_token))
    audits = audit_response.get_json()["data"]["items"]
    assert audits[0]["event_type"] == "document_parse_created"
    assert audits[0]["target_uid"] == record["parse_uid"]


def test_document_parse_api_records_empty_txt(client, teacher_token):
    request_id = "doc-parse-api-empty-request-id"
    response = upload_parse_test(
        client,
        teacher_token,
        "api-empty.txt",
        b"",
        request_id=request_id,
    )

    assert response.status_code == 200
    record = response.get_json()["data"]["parse_record"]
    assert record["quality_status"] == "empty_text"
    assert record["allow_term_extraction"] is False
    audit_response = client.get(f"/api/audit-records?request_id={request_id}", headers=bearer(teacher_token))
    audits = audit_response.get_json()["data"]["items"]
    assert audits[0]["event_type"] == "document_parse_failed"
    assert audits[0]["error_code"] == "empty_text"


def test_document_parse_api_records_unsupported_file(client, teacher_token):
    response = upload_parse_test(
        client,
        teacher_token,
        "api-unsupported.bin",
        b"not a supported teaching file",
        request_id="doc-parse-api-unsupported-request-id",
    )

    assert response.status_code == 200
    record = response.get_json()["data"]["parse_record"]
    assert record["quality_status"] == "unsupported_file_type"
    assert record["allow_term_extraction"] is False


def test_document_parse_api_list_filter_and_detail(client, teacher_token):
    create_response = upload_parse_test(
        client,
        teacher_token,
        "api-filter-notes.txt",
        b"Binary Search Tree keeps ordered keys.",
        request_id="doc-parse-api-filter-request-id",
    )
    parse_uid = create_response.get_json()["data"]["parse_record"]["parse_uid"]

    list_response = client.get(
        "/api/document-parses?quality_status=native_text_ok&q=api-filter&per_page=20",
        headers=bearer(teacher_token),
    )
    detail_response = client.get(f"/api/document-parses/{parse_uid}", headers=bearer(teacher_token))

    assert list_response.status_code == 200
    assert any(item["parse_uid"] == parse_uid for item in list_response.get_json()["data"]["items"])
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"]["parse_record"]["parse_uid"] == parse_uid
    assert detail_response.get_json()["data"]["blocks"]


def test_document_parse_api_missing_parse_uid_returns_json_error(client, teacher_token):
    response = client.get(
        "/api/document-parses/not-a-real-parse-uid",
        headers={**bearer(teacher_token), "X-Request-ID": "doc-parse-api-missing-request-id"},
    )

    assert response.status_code == 404
    assert response.get_json()["status"] == "error"
    assert response.get_json()["request_id"] == "doc-parse-api-missing-request-id"
