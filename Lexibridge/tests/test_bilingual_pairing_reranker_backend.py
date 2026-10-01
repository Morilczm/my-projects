import pytest

from services.local_bilingual_reranker import (
    BILINGUAL_RERANKER_BACKEND_UNAVAILABLE,
    BILINGUAL_RERANKER_REVISION_MISMATCH,
    MAX_CHINESE_TOKENS,
    MAX_ENGLISH_TOKENS,
    MODEL_ID,
    MODEL_LICENSE,
    MODEL_REVISION,
    LocalBilingualReranker,
    LocalBilingualRerankerError,
)
from services.bilingual_pairing_reranker import rerank_pair_scores


def test_reranker_manifest_is_fixed_and_offline():
    assert MODEL_ID == "BAAI/bge-reranker-v2-m3"
    assert MODEL_REVISION == "79c481748842b7efa0a12db59915db91731f0b93"
    assert MODEL_LICENSE == "Apache-2.0"
    assert MAX_ENGLISH_TOKENS == 192
    assert MAX_CHINESE_TOKENS == 316
    assert MAX_ENGLISH_TOKENS + MAX_CHINESE_TOKENS < 512


def test_unavailable_backend_fails_closed(tmp_path):
    backend = LocalBilingualReranker(
        model_cache_dir=tmp_path / "outside-cache",
        repo_root=tmp_path / "repo",
    )
    assert not backend.readiness().ready
    with pytest.raises(
        LocalBilingualRerankerError,
        match=BILINGUAL_RERANKER_BACKEND_UNAVAILABLE,
    ):
        backend.score_pairs([("query", "passage")])


def test_fake_loader_scores_without_network(tmp_path):
    calls = {}

    class FakeRuntime:
        def score_pairs(self, pairs, *, max_length):
            calls["pairs"] = pairs
            calls["max_length"] = max_length
            return [0.75 for _ in pairs]

    backend = LocalBilingualReranker(
        model_cache_dir=tmp_path / "outside-cache",
        repo_root=tmp_path / "repo",
        model_loader=lambda _: FakeRuntime(),
    )
    assert backend.readiness().ready
    assert backend.score_pairs([("query", "passage")]) == [0.75]
    assert calls["pairs"] == [("query", "passage")]
    assert calls["max_length"] == 512


def test_revision_mismatch_fails_closed():
    class WrongRevision:
        model_id = MODEL_ID
        model_revision = "main"

        def readiness(self):
            return type("Readiness", (), {"ready": True})()

    with pytest.raises(
        LocalBilingualRerankerError,
        match=BILINGUAL_RERANKER_REVISION_MISMATCH,
    ):
        rerank_pair_scores(
            [{
                "english_text": "query",
                "chinese_text": "passage",
                "candidate": {},
            }],
            WrongRevision(),
        )
