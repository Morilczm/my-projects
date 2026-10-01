import pytest

from services.cross_language_retrieval import (
    MAX_CONTEXT_CHARS,
    MAX_PASSAGE_CANDIDATES,
    MAX_TOP_K,
    CrossLanguageRetrievalError,
    CrossLanguageRetrievalQuery,
    SemanticPassage,
    build_passage_representation,
    build_query_text,
    rank_chinese_passages,
)


class FakeBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    dimension = 2

    def readiness(self):
        return type("R", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        assert texts[0].startswith("term:\nelectric field")
        assert "discipline:\nphysics" in texts[0]
        assert "context:\n" in texts[0]
        return [[1.0, 0.0]]

    def embed_passages(self, texts):
        return [[1.0, 0.0] if "单位正试探电荷" in text else [0.0, 1.0] for text in texts]


def _query(**changes):
    data = dict(
        english_candidate_uid="candidate-1",
        canonical_english_term="electric field",
        normalized_english_term="electric field",
        english_context="a region where a positive test charge experiences force",
        discipline="physics",
        allowed_chinese_source_uids=("zh-1", "zh-2"),
        top_k=3,
        retrieval_budget=20,
    )
    data.update(changes)
    return CrossLanguageRetrievalQuery(**data)


def _passage(uid, text, **changes):
    data = dict(source_uid="zh-1", chunk_uid=uid, content=text, language="zh",
                source_status="active", quality_status="ready", content_hash=uid)
    data.update(changes)
    return SemanticPassage(**data)


class ConceptAnchorBackend(FakeBackend):
    def __init__(self):
        self.passage_inputs = []

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        self.passage_inputs.extend(texts)
        return [
            [1.0, 0.0] if text.startswith("电荷\n概念定义") else [0.0, 1.0]
            for text in texts
        ]


def test_english_only_query_retrieves_chinese_without_lexical_overlap():
    results = rank_chinese_passages(
        _query(),
        [_passage("b", "单位正试探电荷受到的力刻画这种空间性质。"),
         _passage("a", "单位时间通过截面的电荷量描述电流。")],
        FakeBackend(),
    )
    assert results[0].chunk_uid == "b"
    assert results[0].rank == 1
    assert results[0].query_hash and "electric field" not in results[0].query_hash
    assert results[0].backend_id == FakeBackend.backend_id


def test_filters_language_status_quality_scope_and_preserves_provenance():
    passages = [
        _passage("good", "单位正试探电荷受到的力刻画这种空间性质。"),
        _passage("en", "electric field", language="en"),
        _passage("withdrawn", "单位正试探电荷", source_status="withdrawn"),
        _passage("bad", "单位正试探电荷", quality_status="blocked"),
        _passage("scope", "单位正试探电荷", source_uid="zh-other"),
    ]
    results = rank_chinese_passages(_query(), passages, FakeBackend())
    assert [item.chunk_uid for item in results] == ["good"]
    assert results[0].provenance["source_uid"] == "zh-1"


def test_budgets_are_bounded_and_ties_are_deterministic():
    query = _query(top_k=999, retrieval_budget=999)
    passages = [_passage(f"{i:03}", "无关文本") for i in range(MAX_PASSAGE_CANDIDATES + 5)]
    first = rank_chinese_passages(query, passages, FakeBackend())
    second = rank_chinese_passages(query, list(reversed(passages)), FakeBackend())
    assert len(first) == MAX_TOP_K
    assert [x.chunk_uid for x in first] == [x.chunk_uid for x in second]


def test_context_is_bounded_and_backend_unavailable_fails_closed():
    assert len(build_query_text(_query(english_context="x" * 9999))) <= MAX_CONTEXT_CHARS + 100
    backend = FakeBackend()
    backend.readiness = lambda: type("R", (), {"ready": False, "reason_code": "NO"})()
    with pytest.raises(CrossLanguageRetrievalError, match="LOCAL_MULTILINGUAL"):
        rank_chinese_passages(_query(), [_passage("x", "文本")], backend)


def test_passage_representation_focuses_heading_and_definition_not_repeated_page_noise():
    repeated = "Synthetic private rehearsal footer that repeats on every page"
    passages = [
        _passage(
            "charge",
            f"{repeated}\n第 1 页\n电荷\n概念定义\n电荷是物质的一种基本物理属性。\n关键性质\n电荷守恒。",
            page_number=1,
            block_uid="block-charge",
        ),
        _passage(
            "potential",
            f"{repeated}\n第 2 页\n电势\n概念定义\n电势描述单位正电荷的电势能。\n关键性质\n电势是标量。",
            page_number=2,
            block_uid="block-potential",
        ),
    ]
    backend = ConceptAnchorBackend()

    results = rank_chinese_passages(_query(canonical_english_term="electric charge"), passages, backend)

    assert results[0].chunk_uid == "charge"
    assert backend.passage_inputs[0].startswith("电荷\n概念定义")
    assert repeated not in backend.passage_inputs[0]
    assert "关键性质" not in backend.passage_inputs[0]
    assert results[0].provenance["page_number"] == 1
    assert results[0].provenance["block_uid"] == "block-charge"


def test_passage_representation_is_bounded_and_deterministic():
    text = "概念\n概念定义\n" + "定义正文" * 500
    first = build_passage_representation(text)
    second = build_passage_representation(text)
    assert first == second
    assert len(first) <= 240
