import math
from pathlib import Path

import pytest

from services.local_multilingual_embedding import (
    BACKEND_UNAVAILABLE,
    LocalMultilingualEmbeddingBackend,
    LocalMultilingualEmbeddingError,
    cache_key,
)


class FakeSentenceTransformer:
    def __init__(self):
        self.inputs = []

    def encode(self, texts, **kwargs):
        self.inputs.append((list(texts), dict(kwargs)))
        vectors = []
        for text in texts:
            if text.startswith("query: "):
                vectors.append([3.0, 4.0, 0.0])
            else:
                vectors.append([0.0, 3.0, 4.0])
        return vectors


def test_query_and_passage_prefixes_are_distinct_and_outputs_are_normalized(tmp_path):
    fake = FakeSentenceTransformer()
    backend = LocalMultilingualEmbeddingBackend(
        model_cache_dir=tmp_path,
        model_loader=lambda _: fake,
        repo_root=Path(__file__).resolve().parents[1],
    )

    query = backend.embed_queries(["rotational resistance"])
    passages = backend.embed_passages(["抵抗转动状态变化的物理量"])

    assert fake.inputs[0][0] == ["query: rotational resistance"]
    assert fake.inputs[1][0] == ["passage: 抵抗转动状态变化的物理量"]
    assert math.isclose(sum(value * value for value in query[0]), 1.0)
    assert math.isclose(sum(value * value for value in passages[0]), 1.0)
    assert query == backend.embed_queries(["rotational resistance"])


def test_backend_fails_closed_without_cache_and_never_falls_back(tmp_path):
    missing = tmp_path / "missing"
    backend = LocalMultilingualEmbeddingBackend(
        model_cache_dir=missing,
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert backend.readiness().reason_code == BACKEND_UNAVAILABLE
    with pytest.raises(LocalMultilingualEmbeddingError, match=BACKEND_UNAVAILABLE):
        backend.embed_queries(["no download"])
    assert "hash" not in backend.backend_id
    assert "external" not in backend.backend_id


def test_model_cache_must_be_outside_repository():
    repo_root = Path(__file__).resolve().parents[1]
    with pytest.raises(LocalMultilingualEmbeddingError, match="outside"):
        LocalMultilingualEmbeddingBackend(
            model_cache_dir=repo_root / "models",
            repo_root=repo_root,
        )


def test_cache_key_includes_model_revision_and_content_hash():
    first = cache_key("model-a", "revision-a", "same text")
    second = cache_key("model-a", "revision-b", "same text")
    third = cache_key("model-a", "revision-a", "different text")
    assert first != second
    assert first != third
    assert "same text" not in first
