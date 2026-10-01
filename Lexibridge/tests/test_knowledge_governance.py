from services import audit_records
from services import knowledge_governance


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_parse_record(app_module, quality_status="native_text_ok", text="Fourier Transform maps time to frequency."):
    record = app_module.DocumentParseRecord(
        source_filename=f"governance-{quality_status}.txt",
        file_type="txt",
        parser_name="pytest_governance_parser",
        parser_version="test",
        parse_status="success" if quality_status in {"native_text_ok", "partial_text"} else "failed",
        quality_status=quality_status,
        quality_flags=[quality_status],
        block_count=1 if text else 0,
        extracted_text_chars=len(text),
        warnings=[quality_status] if quality_status == "partial_text" else [],
        error_code=quality_status if quality_status not in {"native_text_ok", "partial_text"} else "",
        error_message="blocked parse quality" if quality_status not in {"native_text_ok", "partial_text"} else "",
    )
    app_module.db.session.add(record)
    app_module.db.session.flush()
    if text:
        app_module.db.session.add(app_module.DocumentParseBlock(
            parse_uid=record.parse_uid,
            block_index=1,
            block_type="text",
            text=text,
            confidence=1.0,
            parser_type="native",
            source_locator="page:1",
            page_number=1,
            quality_flags=[quality_status],
        ))
    app_module.db.session.commit()
    return record


def create_source(app_module, **overrides):
    data = {
        "title": "Governed Signals Notes",
        "course": "Knowledge Governance Course",
        "chapter": "Signals",
        "language": "en",
        "source_type": "teacher_upload",
        "source_role": "english_course_material",
        "owner_type": "teacher",
        "visibility": "course",
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "quality_flags": ["native_text_ok"],
    }
    data.update(overrides)
    return knowledge_governance.create_knowledge_source(
        app_module.db.session,
        app_module.KnowledgeSource,
        data,
        version_model=app_module.KnowledgeVersion,
        audit_model=app_module.AuditRecord,
        now_fn=app_module.current_time_text,
    )


def test_knowledge_governance_models_accept_source_chunk_version_permission(app_module):
    with app_module.app.app_context():
        source = create_source(app_module, quality_flags=["native_text_ok", "teacher_verified"])
        chunks = knowledge_governance.create_knowledge_chunks(
            app_module.db.session,
            app_module.KnowledgeChunk,
            source,
            [{
                "text": "Fourier Transform converts signals into frequency components.",
                "parse_uid": "parse-model-test",
                "parse_block_uid": "block-model-test",
                "source_locator": "page:1",
                "quality_status": "native_text_ok",
                "quality_flags": ["native_text_ok"],
            }],
            audit_model=app_module.AuditRecord,
            now_fn=app_module.current_time_text,
        )
        permission = knowledge_governance.create_permission(
            app_module.db.session,
            app_module.KnowledgePermission,
            source.source_uid,
            principal_type="role",
            principal_id="teacher",
            access_level="read",
            now_fn=app_module.current_time_text,
        )

        serialized_source = knowledge_governance.serialize_knowledge_source(source)
        serialized_chunk = knowledge_governance.serialize_knowledge_chunk(chunks[0])
        version = app_module.KnowledgeVersion.query.filter_by(source_uid=source.source_uid, change_type="created").first()

        assert serialized_source["source_uid"]
        assert serialized_source["quality_flags"] == ["native_text_ok", "teacher_verified"]
        assert serialized_chunk["chunk_uid"]
        assert serialized_chunk["parse_block_uid"] == "block-model-test"
        assert serialized_chunk["quality_flags"] == ["native_text_ok"]
        assert version is not None
        assert version.version_number == 1
        assert permission.access_level == "read"


def test_list_knowledge_sources_filters_course_language_trust_status(app_module):
    with app_module.app.app_context():
        source = create_source(
            app_module,
            title="Filterable Governance Source",
            course="Filter Course",
            language="zh",
            trust_level="official_course",
            status="active",
        )

        result = knowledge_governance.list_knowledge_sources(
            app_module.db.session,
            app_module.KnowledgeSource,
            {
                "course": "Filter Course",
                "language": "zh",
                "trust_level": "official_course",
                "status": "active",
                "q": "Filterable",
            },
        )

        assert any(item.source_uid == source.source_uid for item in result.items)


def test_create_knowledge_chunks_marks_duplicate_content_hash(app_module):
    with app_module.app.app_context():
        source = create_source(app_module, title="Duplicate Governance Source")
        chunks = knowledge_governance.create_knowledge_chunks(
            app_module.db.session,
            app_module.KnowledgeChunk,
            source,
            [
                {"text": "Duplicate governed text.", "quality_status": "native_text_ok"},
                {"text": "Duplicate governed text.", "quality_status": "native_text_ok"},
            ],
            now_fn=app_module.current_time_text,
        )

        assert len(chunks) == 2
        assert chunks[1].is_duplicate is True
        assert chunks[1].duplicate_of_chunk_id == chunks[0].id


def test_build_source_and_chunks_from_parse_record_preserves_parse_trace(app_module):
    with app_module.app.app_context():
        parse_record = create_parse_record(
            app_module,
            quality_status="partial_text",
            text="Partial but useful course text.",
        )
        parse_blocks = app_module.DocumentParseBlock.query.filter_by(parse_uid=parse_record.parse_uid).all()
        source_data = knowledge_governance.build_knowledge_source_from_parse_record(
            parse_record,
            {
                "course": "Parse Trace Course",
                "chapter": "Partial",
                "language": "en",
                "source_type": "teacher_upload",
                "source_role": "english_course_material",
            },
        )
        chunk_data = knowledge_governance.build_knowledge_chunks_from_parse_blocks(
            parse_record,
            parse_blocks,
            "source-parse-trace",
            {"course": "Parse Trace Course", "chapter": "Partial", "language": "en"},
        )

        assert source_data["parse_uid"] == parse_record.parse_uid
        assert source_data["quality_status"] == "partial_text"
        assert source_data["status"] == "needs_review"
        assert source_data["trust_level"] == "low_quality"
        assert chunk_data[0]["parse_block_uid"]
        assert chunk_data[0]["source_locator"] == "page:1"
        assert chunk_data[0]["status"] == "needs_review"
        assert "partial_text" in chunk_data[0]["quality_flags"]


def test_blocked_parse_does_not_build_active_chunks(app_module):
    with app_module.app.app_context():
        parse_record = create_parse_record(app_module, quality_status="parse_failed", text="")
        chunk_data = knowledge_governance.build_knowledge_chunks_from_parse_blocks(
            parse_record,
            [],
            "blocked-source",
            {"course": "Blocked Course"},
        )

        assert chunk_data == []


def test_knowledge_governance_api_lists_sources_and_chunks(client, app_module, teacher_token):
    with app_module.app.app_context():
        source = create_source(app_module, title="API Governance Source", course="API Governance Course")
        chunk = knowledge_governance.create_knowledge_chunks(
            app_module.db.session,
            app_module.KnowledgeChunk,
            source,
            [{"text": "Governed API chunk.", "quality_status": "native_text_ok"}],
            now_fn=app_module.current_time_text,
        )[0]
        source_uid = source.source_uid
        chunk_uid = chunk.chunk_uid

    list_sources = client.get(
        "/api/knowledge-sources?course=API%20Governance%20Course&q=API",
        headers=bearer(teacher_token),
    )
    get_source = client.get(f"/api/knowledge-sources/{source_uid}", headers=bearer(teacher_token))
    list_chunks = client.get(f"/api/knowledge-chunks?source_uid={source_uid}", headers=bearer(teacher_token))
    get_chunk = client.get(f"/api/knowledge-chunks/{chunk_uid}", headers=bearer(teacher_token))

    assert list_sources.status_code == 200
    assert any(item["source_uid"] == source_uid for item in list_sources.get_json()["data"]["items"])
    assert get_source.status_code == 200
    assert get_source.get_json()["data"]["chunk_count"] >= 1
    assert list_chunks.status_code == 200
    assert any(item["chunk_uid"] == chunk_uid for item in list_chunks.get_json()["data"]["items"])
    assert get_chunk.status_code == 200
    assert get_chunk.get_json()["data"]["chunk"]["chunk_uid"] == chunk_uid


def test_knowledge_governance_api_missing_records_return_json(client, teacher_token):
    source_response = client.get(
        "/api/knowledge-sources/not-a-real-source",
        headers={**bearer(teacher_token), "X-Request-ID": "kg-missing-source"},
    )
    chunk_response = client.get(
        "/api/knowledge-chunks/not-a-real-chunk",
        headers={**bearer(teacher_token), "X-Request-ID": "kg-missing-chunk"},
    )

    assert source_response.status_code == 404
    assert source_response.get_json()["status"] == "error"
    assert source_response.get_json()["request_id"] == "kg-missing-source"
    assert chunk_response.status_code == 404
    assert chunk_response.get_json()["status"] == "error"
    assert chunk_response.get_json()["request_id"] == "kg-missing-chunk"


def test_from_parse_api_creates_governed_source_chunks_and_audit(client, app_module, teacher_token):
    request_id = "kg-from-parse-native"
    with app_module.app.app_context():
        parse_record = create_parse_record(app_module, quality_status="native_text_ok", text="Binary Search halves a sorted search space.")
        parse_uid = parse_record.parse_uid

    response = client.post(
        f"/api/knowledge-sources/from-parse/{parse_uid}",
        json={
            "title": "Governed Binary Search Notes",
            "course": "Knowledge API Course",
            "chapter": "Search",
            "language": "en",
            "source_type": "teacher_upload",
            "source_role": "english_course_material",
            "trust_level": "teacher_verified",
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["request_id"] == request_id
    assert payload["data"]["source"]["parse_uid"] == parse_uid
    assert payload["data"]["chunk_count"] == 1
    assert payload["data"]["chunks"][0]["parse_block_uid"]
    with app_module.app.app_context():
        audits = [
            audit_records.serialize_audit_record(record)
            for record in app_module.AuditRecord.query.filter_by(request_id=request_id).all()
        ]
        event_types = {record["event_type"] for record in audits}
        assert {"knowledge_source_created", "knowledge_chunks_created"} <= event_types
        chunks_audit = next(record for record in audits if record["event_type"] == "knowledge_chunks_created")
        assert "Governed API chunk." not in str(chunks_audit["output_payload"])


def test_from_parse_api_blocks_empty_text_and_records_audit(client, app_module, teacher_token):
    request_id = "kg-from-parse-empty"
    with app_module.app.app_context():
        parse_record = create_parse_record(app_module, quality_status="empty_text", text="")
        before_chunks = app_module.KnowledgeChunk.query.count()
        parse_uid = parse_record.parse_uid

    response = client.post(
        f"/api/knowledge-sources/from-parse/{parse_uid}",
        json={"title": "Blocked Empty Parse", "course": "Knowledge API Course"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["request_id"] == request_id
    assert payload["blocked_by_quality_gate"] is True
    assert payload["quality_status"] == "empty_text"
    with app_module.app.app_context():
        assert app_module.KnowledgeChunk.query.count() == before_chunks
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="knowledge_ingestion_blocked",
        ).first()
        assert audit is not None
        serialized = audit_records.serialize_audit_record(audit)
        assert "blocked parse quality" not in str(serialized["output_payload"]).lower()
