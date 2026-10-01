import pytest

from services.bilingual_semantic_pairing import (
    BILINGUAL_PAIRING_CANDIDATE_POOL_EMPTY,
    MAX_PAIR_CANDIDATES,
    BilingualPairingError,
    EnglishPairingInput,
    rank_bilingual_pairs,
)


class SemanticFakeBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    dimension = 2

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        assert "term:\nelectric potential" in texts[0]
        assert "discipline:\nphysics" in texts[0]
        assert "context:\nenergy per unit charge at a point" in texts[0]
        return [[1.0, 0.0]]

    def embed_passages(self, texts):
        assert all("term:" in text and "discipline:\nphysics" in text and "context:" in text for text in texts)
        return [
            [1.0, 0.0] if "单位电荷" in text and "特定带电体" not in text
            else [0.0, 1.0]
            for text in texts
        ]


def _english(**changes):
    values = dict(
        english_candidate_uid="en-candidate-1",
        canonical_english_term="electric potential",
        normalized_english_term="electric potential",
        english_context="energy per unit charge at a point",
        discipline="physics",
        provenance={"source_uid": "en-source", "chunk_uid": "en-chunk"},
    )
    values.update(changes)
    return EnglishPairingInput(**values)


def _candidate(term, rank, context, **changes):
    values = {
        "candidate_uid": f"candidate-{rank}",
        "chinese_term": term,
        "normalized_text": term,
        "evidence_snippet": context,
        "source_uid": "zh-source",
        "chunk_uid": f"zh-chunk-{rank}",
        "source_language": "zh",
        "extraction_method": "definition_subject",
        "score": 0.9 if rank == 1 else 0.5,
        "rank": rank,
        "retrieval_score": 0.8,
        "retrieval_rank": 1,
        "quality_status": "ready",
        "source_role": "chinese_reference_material",
        "provenance": {"source_uid": "zh-source", "chunk_uid": f"zh-chunk-{rank}"},
    }
    values.update(changes)
    return values


def test_semantic_pairing_reranks_lower_extraction_candidate():
    candidates = [
        _candidate("电势能", 1, "电势能属于特定带电体所具有的能量。"),
        _candidate("电势", 2, "电势描述某点单位电荷对应的能量水平。"),
    ]
    pairs = rank_bilingual_pairs(_english(), candidates, SemanticFakeBackend())
    assert pairs[0].chinese_candidate_text == "电势"
    assert pairs[0].extraction_rank == 2
    assert pairs[0].semantic_score > pairs[1].semantic_score
    assert pairs[0].final_score > pairs[1].final_score
    assert pairs[0].score_components["semantic_weight"] > 0.5
    assert pairs[0].english_representation_hash
    assert pairs[0].chinese_representation_hash
    assert pairs[0].provenance["chunk_uid"] == "zh-chunk-2"
    assert not hasattr(pairs[0], "probability")


def test_pairing_is_bounded_deterministic_and_ties_are_stable():
    candidates = [
        _candidate(f"术语{i}", i + 1, "相同定义上下文", score=0.5)
        for i in range(MAX_PAIR_CANDIDATES + 5)
    ]
    first = rank_bilingual_pairs(_english(), candidates, SemanticFakeBackend())
    second = rank_bilingual_pairs(_english(), list(reversed(candidates)), SemanticFakeBackend())
    assert len(first) == MAX_PAIR_CANDIDATES
    assert [item.chinese_candidate_uid for item in first] == [
        item.chinese_candidate_uid for item in second
    ]


def test_empty_pool_fails_closed():
    with pytest.raises(BilingualPairingError, match=BILINGUAL_PAIRING_CANDIDATE_POOL_EMPTY):
        rank_bilingual_pairs(_english(), [], SemanticFakeBackend())


@pytest.mark.parametrize(
    ("english_term", "english_context", "expected", "distractor"),
    [
        ("electric potential energy", "energy held by a charge due to position", "电势能", "电势"),
        ("angular velocity", "rate at which angular position changes", "角速度", "角加速度"),
        ("angular acceleration", "rate at which angular velocity changes", "角加速度", "角速度"),
        ("mass", "measure of resistance to linear acceleration", "质量", "重量"),
        ("weight", "gravitational force acting on a body", "重量", "质量"),
    ],
)
def test_scope_confusions_are_semantically_ranked(
    english_term, english_context, expected, distractor
):
    class ScopeFakeBackend:
        backend_id = SemanticFakeBackend.backend_id
        model_id = SemanticFakeBackend.model_id
        model_revision = SemanticFakeBackend.model_revision

        def readiness(self):
            return type("Readiness", (), {"ready": True})()

        def embed_queries(self, texts):
            assert english_term in texts[0]
            assert english_context in texts[0]
            return [[1.0, 0.0]]

        def embed_passages(self, texts):
            return [[1.0, 0.0] if f"term:\n{expected}\n" in text else [0.0, 1.0] for text in texts]

    candidates = [
        _candidate(distractor, 1, f"{distractor}是相邻但范围不同的概念。"),
        _candidate(expected, 2, f"{expected}的定义上下文与英文概念范围一致。"),
    ]
    pairs = rank_bilingual_pairs(
        _english(
            canonical_english_term=english_term,
            normalized_english_term=english_term,
            english_context=english_context,
        ),
        candidates,
        ScopeFakeBackend(),
    )
    assert pairs[0].chinese_candidate_text == expected
    assert pairs[0].extraction_rank == 2
