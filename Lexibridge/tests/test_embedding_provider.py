from services.embedding_provider import LocalHashEmbeddingProvider, NoneEmbeddingProvider


def test_none_embedding_provider_unavailable():
    provider = NoneEmbeddingProvider()
    assert provider.provider_name() == "none"
    assert provider.is_available() is False


def test_local_hash_embedding_is_deterministic():
    provider = LocalHashEmbeddingProvider(dimension=32)
    left = provider.embed_texts(["Fourier Transform"])[0]
    right = provider.embed_texts(["Fourier Transform"])[0]
    other = provider.embed_texts(["Hash Table"])[0]
    assert left == right
    assert len(left) == 32
    assert left != other
    assert provider.trust_level == "low_trust_embedding"
