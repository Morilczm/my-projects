from types import SimpleNamespace

from services.embedding_provider import LocalHashEmbeddingProvider
from services.retrieval_backends import HybridRetrievalBackend
from services.vector_index import LocalJsonVectorIndexBackend


def _chunk(chunk_id, text, course_id=1):
    return SimpleNamespace(
        id=chunk_id,
        content=text,
        language="zh",
        course_id=course_id,
        course="Signal Processing",
        visibility="course",
        knowledge_base_type="zh_course_kb",
        owner_user_id="",
        index_status="indexed",
        is_duplicate=False,
        is_active=True,
    )


def test_hybrid_retrieval_keeps_hard_filter_and_lexical_gate(tmp_path):
    chunks = [
        _chunk(1, "傅里叶变换用于将时域信号表示为频率分量。", course_id=1),
        _chunk(2, "哈希表通过哈希函数将关键字映射到桶。", course_id=2),
    ]
    provider = LocalHashEmbeddingProvider(dimension=32)
    index = LocalJsonVectorIndexBackend(index_dir=tmp_path)
    embeddings = provider.embed_texts([chunk.content for chunk in chunks])
    index.upsert(7, [
        {"chunk_id": chunk.id, "kb_version_id": 7, "embedding": embedding, "metadata": {"course_id": chunk.course_id, "scope_type": "course", "language": "zh", "knowledge_base_type": "zh_course_kb", "visibility": "course"}}
        for chunk, embedding in zip(chunks, embeddings)
    ])
    backend = HybridRetrievalBackend(embedding_provider=provider, vector_index=index)
    results = backend.search(
        "Fourier Transform",
        {"course_id": 1, "language": "zh", "knowledge_base_type": "zh_course_kb", "scope_type": "course"},
        7,
        top_k=5,
        context={"chunks": chunks},
    )
    assert results
    assert results[0]["chunk_id"] == 1
    assert all(result["course_id"] == 1 for result in results)
    assert "hybrid_score" in results[0]["score_breakdown"]
