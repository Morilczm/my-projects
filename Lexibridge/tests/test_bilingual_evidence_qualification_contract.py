from services import bilingual_evidence_qualification as qualification


def _input(**overrides):
    value = {
        "english_candidate_uid": "en-candidate-1",
        "english_term": "electric potential",
        "normalized_english_term": "electric potential",
        "english_context": "Electric potential describes potential energy per unit charge.",
        "english_source_uid": "en-source-1",
        "english_chunk_uid": "en-chunk-1",
        "english_evidence_span": "Electric potential describes potential energy per unit charge.",
        "english_source_language": "en",
        "english_source_status": "active",
        "english_quality_status": "ready",
        "chinese_candidate_uid": "zh-candidate-1",
        "chinese_term": "电势",
        "normalized_chinese_term": "电势",
        "chinese_context": "电势描述单位电荷在电场中的势能。",
        "chinese_source_uid": "zh-source-1",
        "chinese_chunk_uid": "zh-chunk-1",
        "chinese_evidence_span": "电势描述单位电荷在电场中的势能。",
        "chinese_source_language": "zh",
        "chinese_source_status": "active",
        "chinese_quality_status": "ready",
        "retrieval_score": 0.82,
        "retrieval_rank": 1,
        "extraction_score": 0.91,
        "extraction_rank": 1,
        "pair_rank": 1,
        "bi_encoder_score": 0.84,
        "reranker_score": 2.1,
        "final_pair_score": 2.16,
        "pair_score_margin": 0.4,
        "pair_backend_id": "local-e5",
        "pair_model_id": "intfloat/multilingual-e5-small",
        "pair_model_revision": "fixed",
        "reranker_backend_id": "local-bge",
        "reranker_model_id": "BAAI/bge-reranker-v2-m3",
        "reranker_model_revision": "fixed",
        "english_representation_hash": "a" * 64,
        "chinese_representation_hash": "b" * 64,
        "pair_consistency_score": 7.0,
        "english_binding_status": "matched",
        "retrieval_status": "ready",
        "candidate_pool_status": "ready",
        "pair_execution_status": "succeeded",
    }
    value.update(overrides)
    return qualification.BilingualEvidenceQualificationInput(**value)


def test_complete_correct_top1_pair_is_qualified_deterministically():
    first = qualification.qualify_bilingual_evidence(_input())
    second = qualification.qualify_bilingual_evidence(_input())
    assert first.decision == qualification.QUALIFIED
    assert first == second
    assert first.policy_id == qualification.POLICY_ID
    assert first.policy_version == qualification.POLICY_VERSION
    assert first.qualification_score_is_probability is False
    assert first.english_provenance["chunk_uid"] == "en-chunk-1"
    assert first.chinese_provenance["chunk_uid"] == "zh-chunk-1"


def test_policy_never_replaces_non_top1_pair_and_fails_closed():
    result = qualification.qualify_bilingual_evidence(_input(pair_rank=2))
    assert result.decision == qualification.REJECTED
    assert qualification.EVIDENCE_PAIR_NOT_TOP1 in result.reason_codes


def test_chinese_candidate_must_be_bound_to_real_evidence_span():
    result = qualification.qualify_bilingual_evidence(
        _input(chinese_evidence_span="该段落只描述另一个概念。")
    )
    assert result.decision == qualification.REJECTED
    assert qualification.EVIDENCE_PROVENANCE_INCOMPLETE in result.reason_codes


def test_low_pair_score_rejects_and_low_margin_requires_review():
    rejected = qualification.qualify_bilingual_evidence(
        _input(bi_encoder_score=0.2)
    )
    reviewed = qualification.qualify_bilingual_evidence(
        _input(pair_score_margin=0.01)
    )
    assert rejected.decision == qualification.REJECTED
    assert qualification.EVIDENCE_PAIR_SCORE_INSUFFICIENT in rejected.reason_codes
    assert reviewed.decision == qualification.REVIEW_REQUIRED
    assert qualification.EVIDENCE_PAIR_MARGIN_INSUFFICIENT in reviewed.reason_codes


def test_workflow_adapter_consumes_only_the_production_selected_top1():
    pair = {
        "rank": 1,
        "english_candidate_uid": "en-candidate-1",
        "chinese_candidate_uid": "zh-candidate-1",
        "final_score": 2.0,
        "semantic_score": 0.84,
        "cross_encoder_score": 1.9,
        "source_uid": "zh-source-1",
        "chunk_uid": "zh-chunk-1",
        "retrieval_rank": 1,
        "extraction_rank": 1,
        "backend_id": "local-e5",
        "model_id": "intfloat/multilingual-e5-small",
        "model_revision": "fixed",
        "reranker_backend_id": "local-bge",
        "reranker_model_id": "BAAI/bge-reranker-v2-m3",
        "reranker_model_revision": "fixed",
        "english_representation_hash": "a" * 64,
        "chinese_representation_hash": "b" * 64,
        "score_components": {},
    }
    class _ConsistencyBackend:
        model_id = "BAAI/bge-reranker-v2-m3"
        model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

        def readiness(self):
            return type("Readiness", (), {"ready": True})()

        def score_pairs(self, pairs):
            return [7.0 for _ in pairs]

    result = qualification.qualify_workflow_top1(
        {
            "english_candidate_uid": "en-candidate-1",
            "english_term": "electric potential",
            "normalized_english_term": "electric potential",
            "english_context": "Electric potential describes potential energy per unit charge.",
        },
        [{
            "source_uid": "en-source-1", "chunk_uid": "en-chunk-1",
            "language": "en", "status": "active", "quality_status": "ready",
            "snippet": "Electric potential describes potential energy per unit charge.",
        }],
        [{
            "source_uid": "zh-source-1", "chunk_uid": "zh-chunk-1",
            "language": "zh", "status": "active", "quality_status": "ready",
            "score": 0.82,
        }],
        [{
            "candidate_uid": "zh-candidate-1", "chinese_term": "电势",
            "normalized_text": "电势", "evidence_snippet": "电势描述单位电荷在电场中的势能。",
            "original_span": "电势", "source_uid": "zh-source-1",
            "chunk_uid": "zh-chunk-1", "score": 0.91, "rank": 1,
            "retrieval_rank": 1,
        }],
        [pair, {**pair, "rank": 2, "chinese_candidate_uid": "other", "final_score": 1.5}],
        consistency_backend=_ConsistencyBackend(),
    )
    assert result.decision == qualification.QUALIFIED
    assert result.chinese_provenance["chunk_uid"] == "zh-chunk-1"
