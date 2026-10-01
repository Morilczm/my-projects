from services.bilingual_semantic_pairing import (
    EnglishPairingInput,
    rank_bilingual_pairs,
)


class BiEncoderFake:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]


class CrossEncoderFake:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def score_pairs(self, pairs):
        assert all("discipline:\nphysics" in left for left, _ in pairs)
        assert all("context:" in left and "context:" in right for left, right in pairs)
        return [5.0 if "term:\n质量\n" in right else -1.0 for _, right in pairs]


def _english():
    return EnglishPairingInput(
        english_candidate_uid="en-mass",
        canonical_english_term="mass",
        normalized_english_term="mass",
        english_context="a measure of resistance to acceleration",
        discipline="physics",
        provenance={"source_uid": "en-source", "chunk_uid": "en-chunk"},
    )


def _candidate(term, rank):
    return {
        "candidate_uid": f"zh-{rank}",
        "chinese_term": term,
        "normalized_text": term,
        "evidence_snippet": f"{term}的定义上下文。",
        "source_uid": "zh-source",
        "chunk_uid": f"zh-chunk-{rank}",
        "rank": rank,
        "retrieval_rank": 1,
        "score": 0.9,
        "extraction_method": "definition_subject",
        "provenance": {
            "source_uid": "zh-source",
            "chunk_uid": f"zh-chunk-{rank}",
        },
    }


def test_cross_encoder_reranks_entire_existing_pool_including_rank_five():
    candidates = [
        _candidate("冲量", 1),
        _candidate("动量", 2),
        _candidate("惯性", 3),
        _candidate("重量", 4),
        _candidate("质量", 5),
    ]
    pairs = rank_bilingual_pairs(
        _english(),
        candidates,
        BiEncoderFake(),
        reranker_backend=CrossEncoderFake(),
    )
    assert len(pairs) == len(candidates)
    assert pairs[0].chinese_candidate_text == "质量"
    assert pairs[0].extraction_rank == 5
    assert pairs[0].cross_encoder_score == 5.0
    assert pairs[0].score_components["cross_encoder_weight"] > 0.5
    assert pairs[0].score_components["bi_encoder_score"] == 1.0
    assert "probability" not in pairs[0].score_components


def test_reranker_order_is_deterministic_with_stable_tie_break():
    candidates = [_candidate("重量", 2), _candidate("质量", 1)]

    class TieReranker(CrossEncoderFake):
        def score_pairs(self, pairs):
            return [0.5 for _ in pairs]

    first = rank_bilingual_pairs(
        _english(), candidates, BiEncoderFake(), reranker_backend=TieReranker()
    )
    second = rank_bilingual_pairs(
        _english(), list(reversed(candidates)), BiEncoderFake(),
        reranker_backend=TieReranker(),
    )
    assert [item.chinese_candidate_uid for item in first] == [
        item.chinese_candidate_uid for item in second
    ]


def test_scope_confusions_use_context_not_extraction_rank():
    cases = [
        ("weight", "force exerted by gravity", "重量", "质量"),
        ("electric potential", "energy per unit charge", "电势", "电势能"),
        (
            "electric potential energy",
            "energy a charge has because of position",
            "电势能",
            "电势",
        ),
        ("angular velocity", "rate of change of angular position", "角速度", "角加速度"),
        (
            "angular acceleration",
            "rate of change of angular velocity",
            "角加速度",
            "角速度",
        ),
    ]
    for english_term, context, expected, distractor in cases:
        english = EnglishPairingInput(
            "en", english_term, english_term, context, "physics",
            {"source_uid": "en-source", "chunk_uid": "en-chunk"},
        )

        class ScopeReranker(CrossEncoderFake):
            def score_pairs(self, pairs):
                assert all(context in left for left, _ in pairs)
                return [
                    4.0 if f"term:\n{expected}\n" in right else -2.0
                    for _, right in pairs
                ]

        pairs = rank_bilingual_pairs(
            english,
            [_candidate(distractor, 1), _candidate(expected, 5)],
            BiEncoderFake(),
            reranker_backend=ScopeReranker(),
        )
        assert pairs[0].chinese_candidate_text == expected
        assert pairs[0].extraction_rank == 5
