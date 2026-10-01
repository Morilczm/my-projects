import hashlib
import uuid

from services import bilingual_evidence_workflow


class PairingProductionFakeBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        assert "term:\nelectric potential" in texts[0]
        assert "context:\nenergy per unit charge" in texts[0]
        return [[1.0, 0.0]]

    def embed_passages(self, texts):
        return [
            [1.0, 0.0] if "单位电荷" in text and "特定带电体" not in text
            else [0.0, 1.0]
            for text in texts
        ]


class ProductionRerankerFake:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def score_pairs(self, pairs):
        return [3.0 if "term:\n电势\n" in right else -1.0 for _, right in pairs]


def _add(app_module, course, language, text):
    source_uid = f"source-{uuid.uuid4().hex}"
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        name="governed source",
        course=course,
        language=language,
        source_role=(
            "chinese_reference_material"
            if language == "zh"
            else "english_course_material"
        ),
        source_type="reference",
        status="active",
        quality_status="native_text_ok",
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
        status="active",
        quality_status="native_text_ok",
        trust_level="reference_material",
    )
    app_module.db.session.add(chunk)
    app_module.db.session.commit()
    return chunk


def test_production_workflow_exposes_bounded_semantic_pairs(app_module):
    with app_module.app.app_context():
        course = f"Pairing {uuid.uuid4().hex}"
        _add(
            app_module,
            course,
            "en",
            "Electric potential is the energy per unit charge at a point.",
        )
        correct = _add(
            app_module,
            course,
            "zh",
            "电势描述空间某点单位电荷对应的能量水平。",
        )
        _add(
            app_module,
            course,
            "zh",
            "电势能是特定带电体因位置而具有的能量。",
        )
        result = bilingual_evidence_workflow.retrieve_bilingual_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            "electric potential",
            course=course,
            english_candidate_uid="candidate-en",
            normalized_english_term="electric potential",
            english_context="energy per unit charge",
            discipline="physics",
            cross_language_embedding_backend=PairingProductionFakeBackend(),
            bilingual_reranker_backend=ProductionRerankerFake(),
        )
        assert result.bilingual_pair_candidates
        top = result.bilingual_pair_candidates[0]
        assert top["chinese_candidate_text"] == "电势"
        assert top["chunk_uid"] == correct.chunk_uid
        assert top["semantic_score"] > 0
        assert top["score_components"]["semantic_weight"] == 0.05
        assert top["cross_encoder_score"] == 3.0
        assert top["pairing_method"] == "bge_reranker_v2_m3_cross_encoder_v1"
        assert "probability" not in top
        assert result.selected_chinese_candidate is None
