import pytest

from services import audit_records
from services import knowledge_ingestion


def create_parse_with_blocks(app_module, quality_status="native_text_ok", text="Fourier Transform maps time to frequency."):
    parse_status = "success" if quality_status in {"native_text_ok", "partial_text"} else "failed"
    record = app_module.DocumentParseRecord(
        source_filename=f"ingestion-{quality_status}.txt",
        file_type="txt",
        parser_name="pytest_ingestion_parser",
        parser_version="test",
        parse_status=parse_status,
        quality_status=quality_status,
        quality_flags=[quality_status],
        block_count=1 if text else 0,
        extracted_text_chars=len(text),
        error_code="" if quality_status in {"native_text_ok", "partial_text"} else quality_status,
        error_message="" if quality_status in {"native_text_ok", "partial_text"} else f"{quality_status} blocked",
    )
    app_module.db.session.add(record)
    app_module.db.session.flush()
    blocks = []
    if text:
        block = app_module.DocumentParseBlock(
            parse_uid=record.parse_uid,
            block_index=1,
            block_type="text",
            text=text,
            confidence=1.0,
            parser_type="native",
            source_locator="page:1",
            page_number=1,
            quality_flags=[quality_status],
        )
        app_module.db.session.add(block)
        blocks.append(block)
    app_module.db.session.commit()
    return record, blocks


def models(app_module):
    return knowledge_ingestion.KnowledgeIngestionModels(
        source_model=app_module.KnowledgeSource,
        chunk_model=app_module.KnowledgeChunk,
        version_model=app_module.KnowledgeVersion,
        audit_model=app_module.AuditRecord,
    )


def metadata(**overrides):
    data = {
        "title": "Ingestion Service Notes",
        "course": "Ingestion Course",
        "chapter": "Governance",
        "language": "en",
        "source_type": "teacher_upload",
        "source_role": "english_course_material",
        "trust_level": "teacher_verified",
        "visibility": "course",
    }
    data.update(overrides)
    return data


def test_ingest_native_text_creates_source_and_active_chunk(app_module):
    with app_module.app.app_context():
        record, blocks = create_parse_with_blocks(app_module, "native_text_ok")

        result = knowledge_ingestion.ingest_parse_record_to_governed_knowledge(
            app_module.db.session,
            models(app_module),
            record,
            blocks,
            metadata(),
            now_fn=app_module.current_time_text,
        )

        assert result.source.source_uid
        assert result.source.course == "Ingestion Course"
        assert result.source.chapter == "Governance"
        assert result.source.language == "en"
        assert result.source.source_type == "teacher_upload"
        assert result.source.source_role == "english_course_material"
        assert result.source.trust_level == "teacher_verified"
        assert result.chunks[0].status == "active"
        assert result.chunks[0].parse_uid == record.parse_uid
        assert result.chunks[0].parse_block_uid == blocks[0].block_uid
        assert result.chunks[0].source_locator == "page:1"


def test_ingest_partial_text_creates_needs_review_chunk(app_module):
    with app_module.app.app_context():
        record, blocks = create_parse_with_blocks(app_module, "partial_text", "Partial but usable text.")

        result = knowledge_ingestion.ingest_parse_record_to_governed_knowledge(
            app_module.db.session,
            models(app_module),
            record,
            blocks,
            metadata(),
            now_fn=app_module.current_time_text,
        )

        assert result.ingestion_status == "partial"
        assert result.source.trust_level == "low_quality"
        assert result.chunks[0].status == "needs_review"
        assert "partial_text" in app_module.safe_json_loads(result.chunks[0].quality_flags, [])


@pytest.mark.parametrize("quality_status", ["empty_text", "ocr_unavailable", "parse_failed"])
def test_ingest_blocked_parse_does_not_create_active_chunk(app_module, quality_status):
    with app_module.app.app_context():
        record, blocks = create_parse_with_blocks(app_module, quality_status, "")
        before = app_module.KnowledgeChunk.query.filter_by(status="active").count()

        with pytest.raises(knowledge_ingestion.KnowledgeIngestionBlockedError):
            knowledge_ingestion.ingest_parse_record_to_governed_knowledge(
                app_module.db.session,
                models(app_module),
                record,
                blocks,
                metadata(),
                now_fn=app_module.current_time_text,
            )

        assert app_module.KnowledgeChunk.query.filter_by(status="active").count() == before
        audit = app_module.AuditRecord.query.filter_by(
            target_uid=record.parse_uid,
            event_type="knowledge_ingestion_blocked",
        ).first()
        assert audit is not None


def test_ingest_duplicate_chunks_are_marked(app_module):
    with app_module.app.app_context():
        record, blocks = create_parse_with_blocks(app_module, "native_text_ok", "Duplicate governed chunk.")
        duplicate = app_module.DocumentParseBlock(
            parse_uid=record.parse_uid,
            block_index=2,
            block_type="text",
            text="Duplicate governed chunk.",
            source_locator="page:2",
            quality_flags=["native_text_ok"],
        )
        app_module.db.session.add(duplicate)
        app_module.db.session.commit()
        blocks.append(duplicate)

        result = knowledge_ingestion.ingest_parse_record_to_governed_knowledge(
            app_module.db.session,
            models(app_module),
            record,
            blocks,
            metadata(title="Duplicate Ingestion Notes"),
            now_fn=app_module.current_time_text,
        )

        assert len(result.chunks) == 2
        assert result.chunks[1].is_duplicate is True
        assert result.chunks[1].duplicate_of_chunk_id == result.chunks[0].id


def test_ingestion_audit_is_summary_only(app_module):
    with app_module.app.app_context():
        record, blocks = create_parse_with_blocks(app_module, "native_text_ok", "Sensitive full chunk text should not be copied into audit.")

        result = knowledge_ingestion.ingest_parse_record_to_governed_knowledge(
            app_module.db.session,
            models(app_module),
            record,
            blocks,
            metadata(title="Audit Summary Notes"),
            now_fn=app_module.current_time_text,
        )

        audit = app_module.AuditRecord.query.filter_by(
            target_uid=result.source.source_uid,
            event_type="knowledge_ingestion_completed",
        ).first()
        serialized = audit_records.serialize_audit_record(audit)
        assert serialized["output_payload"]["chunk_count"] == 1
        assert "Sensitive full chunk text" not in str(serialized["output_payload"])
