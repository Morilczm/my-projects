from types import SimpleNamespace

from services.retrieval_backends import LexicalRetrievalBackend, VALID_RETRIEVAL_BACKENDS, get_retrieval_backend


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


def test_lexical_backend_schema_and_invalid_backend_fallback():
    backend = LexicalRetrievalBackend()
    results = backend.search(
        "Fourier Transform",
        {"course_id": 1, "language": "zh", "knowledge_base_type": "zh_course_kb", "scope_type": "course"},
        None,
        top_k=5,
        context={"chunks": [_chunk(1, "傅里叶变换用于将时域信号表示为频率分量。"), _chunk(2, "哈希表通过哈希函数映射关键字。")]},
    )
    assert results
    assert results[0]["retrieval_backend"] == "lexical"
    assert "lexical_score" in results[0]
    assert "score_breakdown" in results[0]
    assert "hybrid" in VALID_RETRIEVAL_BACKENDS
    assert get_retrieval_backend("missing").backend_name == "lexical"
