from services.chunk_dedup import compute_content_hash, is_too_short_chunk, mark_duplicate_chunk, normalize_chunk_text


def test_chunk_hash_and_duplicate_marking(app_module):
    assert normalize_chunk_text(" Fourier   Transform ") == "fourier transform"
    assert compute_content_hash("Fourier Transform") == compute_content_hash("fourier   transform")
    assert is_too_short_chunk("  a ")

    with app_module.app.app_context():
        chunk = app_module.KnowledgeChunk(document_id=0, content="duplicate")
        app_module.db.session.add(chunk)
        app_module.db.session.flush()
        mark_duplicate_chunk(chunk, 99)
        assert chunk.is_duplicate is True
        assert chunk.duplicate_of_chunk_id == 99
        assert chunk.index_status == "duplicate"
        assert chunk.is_active is False
