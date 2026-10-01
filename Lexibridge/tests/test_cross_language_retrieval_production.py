import hashlib
import uuid

from services import bilingual_evidence_workflow


class ProductionFakeBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        assert "term:\nelectric field" in texts[0]
        assert "discipline:\nphysics" in texts[0]
        assert "context:\na region where a test charge experiences force" in texts[0]
        return [[1.0, 0.0]]

    def embed_passages(self, texts):
        return [
            [1.0, 0.0] if "试探电荷" in text else [0.0, 1.0]
            for text in texts
        ]


def _add_source_and_chunk(
    app_module, *, language, text, course, status="active",
    quality_status="native_text_ok"
):
    source_uid = f"src-{uuid.uuid4().hex}"
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        name="governed reference",
        course=course,
        language=language,
        source_role="chinese_reference_material" if language == "zh" else "english_course_material",
        source_type="reference",
        status=status,
        quality_status=quality_status,
        trust_level="reference_material",
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk = app_module.KnowledgeChunk(
        chunk_uid=f"chunk-{uuid.uuid4().hex}",
        source_uid=source_uid,
        knowledge_source_id=source.id,
        document_id=0,
        course=course,
        language=language,
        content=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        status=status,
        quality_status=quality_status,
        trust_level="reference_material",
    )
    app_module.db.session.add(chunk)
    app_module.db.session.commit()
    return source, chunk


def test_production_workflow_uses_semantic_backend_and_chinese_governance(app_module):
    with app_module.app.app_context():
        course = f"Semantic Retrieval {uuid.uuid4().hex}"
        _, correct = _add_source_and_chunk(
            app_module,
            language="zh",
            text="电场表示单位正试探电荷所受力所刻画的空间性质。",
            course=course,
        )
        _add_source_and_chunk(
            app_module,
            language="en",
            text="electric field is an English-only course concept",
            course=course,
        )
        _add_source_and_chunk(
            app_module,
            language="zh",
            text="单位时间通过截面的电荷量描述另一种物理现象。",
            course=course,
            status="withdrawn",
        )
        result = bilingual_evidence_workflow.retrieve_bilingual_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            "electric field",
            course=course,
            english_candidate_uid="candidate-opaque",
            normalized_english_term="electric field",
            english_context="a region where a test charge experiences force",
            discipline="physics",
            cross_language_embedding_backend=ProductionFakeBackend(),
        )
        assert [item["chunk_uid"] for item in result.chinese_evidence_candidates] == [
            correct.chunk_uid
        ]
        candidate = result.chinese_evidence_candidates[0]
        assert candidate["language"] == "zh"
        assert candidate["retrieval_method"] == "multilingual_e5_cosine"
        assert candidate["model_revision"] == ProductionFakeBackend.model_revision
        assert candidate["query_hash"]
        assert "electric field" not in candidate["query_hash"]
        assert candidate["provenance"]["chunk_uid"] == correct.chunk_uid
        assert result.chinese_term == ""
        assert result.chinese_term_candidates[0]["chinese_term"] == "电场"
        assert result.bilingual_pair_candidates[0]["chinese_candidate_text"] == "电场"
        assert result.bilingual_pair_candidates[0]["pairing_method"] == (
            "multilingual_e5_semantic_pairing_v1"
        )
        assert result.bilingual_pair_candidates[0]["source_uid"]
        assert result.bilingual_pair_candidates[0]["chunk_uid"] == correct.chunk_uid
        assert result.selected_chinese_candidate is None
        assert "missing_chinese_term" in result.risk_labels


def test_request_cannot_select_model_or_disable_language_filter():
    query = bilingual_evidence_workflow.build_bilingual_evidence_query(
        {
            "english_term": "electric field",
            "model_path": "/tmp/arbitrary-model",
            "retrieval_backend": "external",
            "filters": {"language": "en"},
        }
    )
    assert "model_path" not in query
    assert "retrieval_backend" not in query
    assert query["filters"]["language"] == "en"
    assert bilingual_evidence_workflow.CROSS_LANGUAGE_BACKEND_NAME == (
        "local-multilingual-e5-small"
    )
