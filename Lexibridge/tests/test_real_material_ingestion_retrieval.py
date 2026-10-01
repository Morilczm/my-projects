import hashlib
from types import SimpleNamespace

from services import (
    bilingual_evidence_workflow,
    knowledge_governance,
    knowledge_ingestion,
)


class DeterministicLayoutRetrievalBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return SimpleNamespace(ready=True, reason_code="READY")

    def embed_queries(self, texts):
        return [[1.0, 0.0]]

    def embed_passages(self, texts):
        return [
            [1.0, 0.0] if "抵抗转动状态改变" in text else [0.0, 1.0]
            for text in texts
        ]


def _models(app_module):
    return knowledge_ingestion.KnowledgeIngestionModels(
        source_model=app_module.KnowledgeSource,
        chunk_model=app_module.KnowledgeChunk,
        version_model=app_module.KnowledgeVersion,
        audit_model=app_module.AuditRecord,
    )


def _persist_layout_source(app_module, course):
    record = app_module.DocumentParseRecord(
        parse_uid="parse-layout-retrieval",
        source_filename="synthetic-zh.pdf",
        file_type="pdf",
        parser_name="pymupdf_layout_rule_based",
        parser_version="document_parse_quality_v1",
        parse_status="success",
        quality_status="native_text_ok",
        quality_flags=["native_text_ok", "layout_applied", "layout_provider_rule_based"],
        block_count=2,
        extracted_text_chars=64,
    )
    app_module.db.session.add(record)
    app_module.db.session.flush()
    blocks = [
        app_module.DocumentParseBlock(
            block_uid="layout-title-inertia",
            parse_uid=record.parse_uid,
            block_index=1,
            block_type="title",
            text="转动惯量",
            page_number=1,
            parser_type="layout_rule_based",
            source_locator="page:1;bbox:72,80,200,110",
            quality_flags=["layout", "layout_type_title"],
        ),
        app_module.DocumentParseBlock(
            block_uid="layout-body-inertia",
            parse_uid=record.parse_uid,
            block_index=2,
            block_type="text",
            text="描述物体抵抗转动状态改变能力的物理量。",
            page_number=1,
            parser_type="layout_rule_based",
            source_locator="page:1;bbox:72,115,500,150",
            quality_flags=["layout", "layout_type_text"],
        ),
    ]
    app_module.db.session.add_all(blocks)
    app_module.db.session.commit()
    result = knowledge_ingestion.ingest_parse_record_to_governed_knowledge(
        app_module.db.session,
        _models(app_module),
        record,
        blocks,
        {
            "title": "Synthetic Chinese Mechanics",
            "course": course,
            "language": "zh",
            "source_type": "teacher_upload",
            "source_role": "chinese_reference_material",
            "trust_level": "teacher_verified",
            "visibility": "course",
        },
        now_fn=app_module.current_time_text,
    )
    return result


def test_layout_knowledge_chunk_enters_existing_multilingual_retrieval(app_module):
    with app_module.app.app_context():
        course = "Layout Retrieval Synthetic"
        ingested = _persist_layout_source(app_module, course)

        assert len(ingested.chunks) == 1
        chunk = ingested.chunks[0]
        assert chunk.status == "active"
        assert chunk.language == "zh"
        assert chunk.content_hash == hashlib.sha256(
            " ".join(chunk.content.split()).encode("utf-8")
        ).hexdigest()

        result = bilingual_evidence_workflow.retrieve_bilingual_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            "rotational inertia",
            course=course,
            english_candidate_uid="candidate-layout-inertia",
            normalized_english_term="rotational inertia",
            english_context="a property describing resistance to changes in rotational motion",
            discipline="physics",
            cross_language_embedding_backend=DeterministicLayoutRetrievalBackend(),
        )

        assert result.chinese_evidence_candidates
        assert result.chinese_evidence_candidates[0]["chunk_uid"] == chunk.chunk_uid
        assert result.chinese_evidence_candidates[0]["rank"] == 1
        assert result.chinese_evidence_candidates[0]["provenance"]["chunk_uid"] == chunk.chunk_uid
        assert "rotational inertia" not in chunk.content.lower()
