from types import SimpleNamespace

from services.reranker import LocalHeuristicRerankerProvider, NoneRerankerProvider


def test_local_heuristic_reranker_orders_filtered_candidates():
    chunk_exact = SimpleNamespace(content="傅里叶变换用于表示频率分量。")
    chunk_other = SimpleNamespace(content="哈希表通过哈希函数映射关键字。")
    candidates = [
        {"chunk_id": 2, "_chunk": chunk_other, "final_retrieval_score": 0.7, "evidence_score": 0.7},
        {"chunk_id": 1, "_chunk": chunk_exact, "final_retrieval_score": 0.7, "evidence_score": 0.7},
    ]
    reranker = LocalHeuristicRerankerProvider()
    results = reranker.rerank("Fourier Transform", candidates, 2)
    assert results[0]["chunk_id"] == 1
    assert results[0]["rerank_score"] >= results[1]["rerank_score"]
    assert NoneRerankerProvider().is_available() is False
