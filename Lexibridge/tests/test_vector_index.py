from services.vector_index import LocalJsonVectorIndexBackend


def test_local_json_vector_index_upsert_search_delete(tmp_path):
    backend = LocalJsonVectorIndexBackend(index_dir=tmp_path)
    result = backend.upsert(3, [
        {
            "chunk_id": 1,
            "kb_version_id": 3,
            "embedding": [1.0, 0.0],
            "metadata": {"course_id": 1, "scope_type": "course", "language": "zh", "knowledge_base_type": "zh_course_kb", "visibility": "course"},
        },
        {
            "chunk_id": 2,
            "kb_version_id": 3,
            "embedding": [0.0, 1.0],
            "metadata": {"course_id": 2, "scope_type": "course", "language": "zh", "knowledge_base_type": "zh_course_kb", "visibility": "course"},
        },
    ])
    assert result["upserted"] == 2
    hits = backend.search(3, [1.0, 0.0], {"course_id": 1, "scope_type": "course", "language": "zh", "knowledge_base_type": "zh_course_kb", "visibility": "course"}, 5)
    assert [hit["chunk_id"] for hit in hits] == [1]
    assert backend.healthcheck(3)["vector_count"] == 2
    assert backend.delete_version(3)["deleted"] == 1
    assert backend.search(3, [1.0, 0.0], {}, 5) == []
