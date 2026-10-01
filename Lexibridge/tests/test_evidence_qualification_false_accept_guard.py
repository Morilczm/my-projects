from services import bilingual_evidence_qualification as qualification


class _ConsistencyBackend:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def score_pairs(self, pairs):
        assert len(pairs) == 1
        english, chinese = pairs[0]
        assert "term:" in english and "context:" in english
        assert "术语:" in chinese and "语境:" in chinese
        return [7.0]


def _workflow_values():
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
        "reranker_backend_id": _ConsistencyBackend.backend_id,
        "reranker_model_id": _ConsistencyBackend.model_id,
        "reranker_model_revision": _ConsistencyBackend.model_revision,
        "english_representation_hash": "a" * 64,
        "chinese_representation_hash": "b" * 64,
    }
    return (
        {
            "english_candidate_uid": "en-candidate-1",
            "english_term": "density",
            "normalized_english_term": "density",
            "english_context": "Density is mass per unit volume.",
            "discipline": "physics",
            "english_binding_status": "matched",
        },
        [{
            "source_uid": "en-source-1",
            "chunk_uid": "en-chunk-1",
            "language": "en",
            "status": "active",
            "quality_status": "ready",
            "snippet": "Density is mass per unit volume.",
        }],
        [{
            "source_uid": "zh-source-1",
            "chunk_uid": "zh-chunk-1",
            "language": "zh",
            "status": "active",
            "quality_status": "ready",
            "score": 0.82,
        }],
        [{
            "candidate_uid": "zh-candidate-1",
            "chinese_term": "密度",
            "normalized_text": "密度",
            "evidence_snippet": "密度表示单位体积中所含物质的质量。",
            "original_span": "密度",
            "source_uid": "zh-source-1",
            "chunk_uid": "zh-chunk-1",
            "score": 0.91,
            "rank": 1,
            "retrieval_rank": 1,
        }],
        [pair, {**pair, "rank": 2, "chinese_candidate_uid": "other", "final_score": 1.5}],
    )


def test_workflow_consistency_check_scores_only_selected_top1_and_never_substitutes():
    values = _workflow_values()
    result = qualification.qualify_workflow_top1(
        *values,
        consistency_backend=_ConsistencyBackend(),
    )
    assert result.decision == qualification.QUALIFIED
    assert result.score_components["pair_consistency_score"] == 7.0
    assert result.chinese_provenance["chunk_uid"] == "zh-chunk-1"


def test_workflow_propagates_english_upstream_status():
    input_data, *rest = _workflow_values()
    input_data["english_binding_status"] = "ambiguous"
    result = qualification.qualify_workflow_top1(
        input_data,
        *rest,
        consistency_backend=_ConsistencyBackend(),
    )
    assert result.decision != qualification.QUALIFIED
    assert qualification.EVIDENCE_UPSTREAM_STATE_NOT_READY in result.reason_codes
