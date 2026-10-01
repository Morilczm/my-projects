from io import BytesIO
import uuid

from services import document_parse_quality


def auth_header(token, request_id="ingestion-quality-test-request"):
    return {
        "Authorization": f"Bearer {token}",
        "X-Request-ID": request_id,
    }


def make_parse_result(filename, quality_status, text="", *, flags=None, parse_status=None, error_code="", error_message=""):
    flags = list(flags or [quality_status])
    parse_status = parse_status or ("success" if quality_status == "native_text_ok" else "partial" if quality_status == "partial_text" else "failed")
    blocks = []
    if text:
        blocks.append({
            "block_uid": str(uuid.uuid4()),
            "page_number": 1,
            "slide_number": None,
            "block_index": 1,
            "block_type": "text",
            "text": text,
            "confidence": 1.0,
            "parser_type": "native",
            "source_locator": "page:1",
            "quality_flags": flags,
        })
    quality = {
        "parse_status": parse_status,
        "quality_status": quality_status,
        "quality_flags": document_parse_quality.normalize_quality_flags(flags),
        "warnings": document_parse_quality.normalize_quality_flags(flags if quality_status == "partial_text" else []),
        "errors": [error_message] if error_message else [],
        "ocr_required": quality_status in {"ocr_required", "ocr_unavailable"},
        "ocr_available": False,
        "formula_detected": False,
        "image_only_suspected": quality_status in {"ocr_required", "ocr_unavailable"},
    }
    record_data = document_parse_quality.build_parse_record_from_result(
        source_filename=filename,
        parser_name="pytest_fake_parser",
        file_type="txt",
        raw_text=text,
        blocks=blocks,
        quality=quality,
        error_code=error_code or quality_status,
        error_message=error_message,
    )
    return document_parse_quality.DocumentParseResult(
        parse_record_data=record_data,
        blocks=blocks,
        raw_text=text,
        warnings=quality["warnings"],
        errors=quality["errors"],
    )


def post_formal_document(client, token, course_id, content, filename="quality-gate.txt", request_id="formal-upload-quality"):
    return client.post(
        "/api/documents/upload?sync=true",
        headers=auth_header(token, request_id),
        data={
            "scope_type": "course",
            "course_id": str(course_id),
            "language": "en",
            "file": (BytesIO(content), filename),
        },
        content_type="multipart/form-data",
    )


def test_formal_upload_native_text_creates_parse_record_and_traceable_chunks(client, app_module, teacher_token, test_course):
    request_id = "formal-native-text-quality-gate"
    response = post_formal_document(
        client,
        teacher_token,
        test_course.id,
        b"Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        request_id=request_id,
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    parse_uid = payload["parse_uid"]
    assert payload["request_id"] == request_id
    assert payload["quality_status"] == "native_text_ok"
    assert payload["should_allow_term_extraction"] is True
    assert payload["ingestion_status"] == "ingested"
    assert payload["source_uid"]
    assert payload["chunk_count"] >= 1
    assert payload["chunk_uids"]
    with app_module.app.app_context():
        assert app_module.DocumentParseRecord.query.filter_by(parse_uid=parse_uid).count() == 1
        document = app_module.Document.query.filter_by(parse_uid=parse_uid).first()
        assert document is not None
        doc_chunk = app_module.DocumentChunk.query.filter_by(document_id=document.id).first()
        kb_chunk = app_module.KnowledgeChunk.query.filter_by(document_id=document.id).first()
        assert doc_chunk is not None
        assert kb_chunk is not None
        assert doc_chunk.parse_uid == parse_uid
        assert doc_chunk.parse_block_uid
        assert kb_chunk.source_uid == payload["source_uid"]
        assert kb_chunk.chunk_uid in payload["chunk_uids"]
        assert kb_chunk.parse_uid == parse_uid
        assert kb_chunk.parse_block_uid == doc_chunk.parse_block_uid
        assert kb_chunk.status == "active"
        audits = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type="document_ingestion_completed").all()
        assert audits
        assert app_module.AuditRecord.query.filter_by(request_id=request_id, event_type="knowledge_ingestion_completed").first()


def test_formal_upload_empty_text_is_blocked_before_chunks_and_terms(client, app_module, teacher_token, test_course):
    request_id = "formal-empty-text-quality-gate"
    with app_module.app.app_context():
        before_doc_chunks = app_module.DocumentChunk.query.count()
        before_kb_chunks = app_module.KnowledgeChunk.query.count()
        before_cards = app_module.TerminologyCard.query.count()

    response = post_formal_document(
        client,
        teacher_token,
        test_course.id,
        b"",
        request_id=request_id,
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["request_id"] == request_id
    assert payload["quality_status"] == "empty_text"
    assert payload["blocked_by_quality_gate"] is True
    assert payload["should_allow_term_extraction"] is False
    with app_module.app.app_context():
        document = app_module.Document.query.filter_by(parse_uid=payload["parse_uid"]).first()
        assert document.parsing_status == "blocked_by_quality_gate"
        assert app_module.DocumentChunk.query.count() == before_doc_chunks
        assert app_module.KnowledgeChunk.query.count() == before_kb_chunks
        assert app_module.TerminologyCard.query.count() == before_cards
        audits = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type="document_ingestion_blocked").all()
        assert audits


def test_formal_upload_ocr_unavailable_is_blocked(monkeypatch, client, app_module, teacher_token, test_course):
    def fake_parse(file_path, filename=None, mime_type=None, **kwargs):
        return make_parse_result(
            filename or "scan.txt",
            "ocr_unavailable",
            "",
            flags=["ocr_required", "ocr_unavailable"],
            error_code="ocr_unavailable",
            error_message="OCR is required before reliable text extraction.",
        )

    monkeypatch.setattr(app_module.document_parse_quality_service, "parse_document_with_quality", fake_parse)
    response = post_formal_document(
        client,
        teacher_token,
        test_course.id,
        b"placeholder bytes",
        request_id="formal-ocr-unavailable-quality-gate",
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["error_code"] == "OCR_UNAVAILABLE"
    assert payload["quality_status"] == "ocr_unavailable"
    assert payload["blocked_by_quality_gate"] is True


def test_formal_upload_parse_failed_is_blocked(monkeypatch, client, app_module, teacher_token, test_course):
    def fake_parse(file_path, filename=None, mime_type=None, **kwargs):
        return make_parse_result(
            filename or "broken.txt",
            "parse_failed",
            "",
            error_code="parse_failed",
            error_message="parser exploded",
        )

    monkeypatch.setattr(app_module.document_parse_quality_service, "parse_document_with_quality", fake_parse)
    response = post_formal_document(
        client,
        teacher_token,
        test_course.id,
        b"parser input",
        request_id="formal-parse-failed-quality-gate",
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["quality_status"] == "parse_failed"
    assert payload["blocked_by_quality_gate"] is True
    assert "parser exploded" in payload["blocked_reason"]


def test_formal_upload_partial_text_continues_with_risk_flags(monkeypatch, client, app_module, teacher_token, test_course):
    def fake_parse(file_path, filename=None, mime_type=None, **kwargs):
        return make_parse_result(
            filename or "partial.txt",
            "partial_text",
            "Fourier Transform converts a time-domain signal.",
            flags=["partial_text"],
        )

    request_id = "formal-partial-text-quality-gate"
    monkeypatch.setattr(app_module.document_parse_quality_service, "parse_document_with_quality", fake_parse)
    response = post_formal_document(
        client,
        teacher_token,
        test_course.id,
        b"partial input",
        request_id=request_id,
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["quality_status"] == "partial_text"
    assert payload["ingestion_status"] == "partial"
    assert "partial_text" in payload["quality_flags"]
    assert payload["source_uid"]
    with app_module.app.app_context():
        chunk = app_module.DocumentChunk.query.filter_by(parse_uid=payload["parse_uid"]).first()
        assert "partial_text" in app_module.safe_json_loads(chunk.quality_flags_json, [])
        kb_chunk = app_module.KnowledgeChunk.query.filter_by(parse_uid=payload["parse_uid"]).first()
        assert kb_chunk.status == "needs_review"
        assert kb_chunk.trust_level == "low_quality"
        card = app_module.TerminologyCard.query.filter_by(parse_uid=payload["parse_uid"]).first()
        assert card is not None
        assert card.status != "auto_approved"
        assert "input_partial_text" in app_module.safe_json_loads(card.input_risk_labels, [])
        assert "input_partial_text" in app_module.safe_json_loads(card.quality_flags_json, [])
        assert card.confidence_score <= 79
        audits = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type="document_ingestion_completed").all()
        assert audits


def test_knowledge_upload_native_text_uses_parse_blocks(client, app_module, teacher_token, test_course):
    request_id = "knowledge-native-text-quality-gate"
    response = client.post(
        "/api/knowledge/upload",
        headers=auth_header(teacher_token, request_id),
        data={
            "course": test_course.name,
            "title": "Knowledge Notes",
            "language": "en",
            "file": (BytesIO(b"Convolution combines two signals into one output signal."), "knowledge-notes.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    parse_uid = payload["parse_uid"]
    assert payload["quality_status"] == "native_text_ok"
    assert payload["should_allow_term_extraction"] is True
    assert payload["source_uid"]
    assert payload["chunk_count"] >= 1
    assert payload["chunk_uids"]
    assert payload["embedding_count"] == 0
    assert payload["document"]["parse_uid"] == parse_uid
    assert payload["sample_chunks"][0]["parse_uid"] == parse_uid
    assert payload["sample_chunks"][0]["parse_block_uid"]
    assert payload["sample_chunks"][0]["source_uid"] == payload["source_uid"]
    with app_module.app.app_context():
        audits = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type="document_ingestion_completed").all()
        assert audits
        assert app_module.AuditRecord.query.filter_by(request_id=request_id, event_type="knowledge_ingestion_completed").first()


def test_knowledge_upload_empty_text_is_blocked_before_knowledge_records(client, app_module, teacher_token, test_course):
    request_id = "knowledge-empty-text-quality-gate"
    with app_module.app.app_context():
        before_docs = app_module.KnowledgeDocument.query.count()
        before_chunks = app_module.KnowledgeChunk.query.count()
    response = client.post(
        "/api/knowledge/upload",
        headers=auth_header(teacher_token, request_id),
        data={
            "course": test_course.name,
            "title": "Empty Notes",
            "language": "en",
            "file": (BytesIO(b""), "empty-knowledge.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["quality_status"] == "empty_text"
    assert payload["blocked_by_quality_gate"] is True
    with app_module.app.app_context():
        assert app_module.KnowledgeDocument.query.count() == before_docs
        assert app_module.KnowledgeChunk.query.count() == before_chunks
        audits = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type="document_ingestion_blocked").all()
        assert audits


def test_legacy_courseware_empty_text_blocks_term_extraction(client, app_module, teacher_token, test_course):
    request_id = "legacy-empty-text-quality-gate"
    with app_module.app.app_context():
        before_terms = app_module.Term.query.count()
    response = client.post(
        "/api/upload",
        headers=auth_header(teacher_token, request_id),
        data={
            "course": test_course.name,
            "chapter": "Quality Gate",
            "file": (BytesIO(b""), "empty-courseware.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["quality_status"] == "empty_text"
    assert payload["terms"] == []
    with app_module.app.app_context():
        assert app_module.Term.query.count() == before_terms


def test_legacy_courseware_partial_text_creates_pending_risk_marked_terms(monkeypatch, client, app_module, teacher_token, test_course):
    def fake_parse(file_path, filename=None, mime_type=None, **kwargs):
        return make_parse_result(
            filename or "partial-courseware.txt",
            "partial_text",
            "Fourier Transform is defined as a frequency-domain representation.",
            flags=["partial_text"],
        )

    monkeypatch.setattr(app_module.document_parse_quality_service, "parse_document_with_quality", fake_parse)
    response = client.post(
        "/api/upload",
        headers=auth_header(teacher_token, "legacy-partial-text-quality-gate"),
        data={
            "course": test_course.name,
            "chapter": "Quality Gate Partial",
            "file": (BytesIO(b"partial"), "partial-courseware.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["quality_status"] == "partial_text"
    assert payload["ingestion_status"] == "partial"
    assert "input_partial_text" in payload["risk_labels"]
    assert payload["source_uid"]
    assert payload["chunk_count"] >= 1
    assert payload["chunk_uids"]
    assert payload["terms"]
    with app_module.app.app_context():
        upload = app_module.CoursewareUpload.query.filter_by(parse_uid=payload["parse_uid"]).first()
        assert upload is not None
        term = app_module.Term.query.filter_by(chapter="Quality Gate Partial").first()
        assert term is not None
        assert term.status == "pending"
        assert term.parse_uid == payload["parse_uid"]
        assert term.parse_quality_status == "partial_text"
        assert term.source_uid == payload["source_uid"]
        assert term.chunk_uid in payload["chunk_uids"]
        assert "input_partial_text" in app_module.safe_json_loads(term.input_risk_labels, [])
        assert term.confidence <= 79
        assert "partial_text" in term.risk_note
