from types import SimpleNamespace

from services import knowledge_governance


def _block(uid, index, block_type, text, page=1, locator=None):
    return SimpleNamespace(
        block_uid=uid,
        block_index=index,
        block_type=block_type,
        text=text,
        page_number=page,
        slide_number=None,
        parser_type="layout_rule_based",
        source_locator=locator or f"page:{page};block:{index}",
        quality_flags=["layout", f"layout_type_{block_type}"],
    )


def _parse_record():
    return SimpleNamespace(
        parse_uid="parse-layout-contract",
        parser_name="pymupdf_layout_rule_based",
        parser_version="document_parse_quality_v1",
        quality_status="native_text_ok",
        quality_flags=["native_text_ok", "layout_applied"],
    )


def _chunks():
    blocks = [
        _block("b-header", 1, "header_footer", "Repeated Course Header"),
        _block("b-title-1", 2, "title", "Electric Potential"),
        _block(
            "b-text-1",
            3,
            "text",
            "Potential describes work per unit charge at a location.",
        ),
        _block("b-title-2", 4, "title", "Electric Potential Energy"),
        _block(
            "b-text-2",
            5,
            "text",
            "Potential energy belongs to a charge in an electric configuration.",
        ),
        _block("b-list", 6, "list", "• depends on charge\n• measured in joules"),
        _block("b-table", 7, "table", "quantity | unit\nenergy | joule"),
        _block("b-formula", 8, "formula", "U = qV"),
        _block("b-list", 9, "list", "• depends on charge\n• measured in joules"),
        _block("b-footer", 10, "page_number", "1"),
    ]
    return knowledge_governance.build_knowledge_chunks_from_parse_blocks(
        _parse_record(),
        blocks,
        "source-layout-contract",
        {
            "course": "Synthetic Physics",
            "chapter": "Fields",
            "language": "en",
            "trust_level": "teacher_verified",
        },
    )


def test_heading_and_definition_stay_together_without_crossing_section():
    chunks = _chunks()

    potential = next(item for item in chunks if item["source_section"] == "Electric Potential")
    energy = next(
        item for item in chunks
        if item["source_section"] == "Electric Potential Energy"
    )

    assert "Electric Potential\n" in potential["text"]
    assert "work per unit charge" in potential["text"]
    assert "Potential Energy" not in potential["text"]
    assert "Potential Energy\n" in energy["text"]
    assert "electric configuration" in energy["text"]


def test_layout_metadata_provenance_and_noise_filter_are_complete():
    chunks = _chunks()

    assert all("Repeated Course Header" not in item["text"] for item in chunks)
    assert all(item["parse_block_uid"] for item in chunks)
    assert all(item["page_number"] == 1 for item in chunks)
    assert all("blocks:" in item["source_locator"] for item in chunks)
    assert all("spans:" in item["source_locator"] for item in chunks)
    assert all(item["content_hash"] for item in chunks)
    assert all(item["chunk_uid"] for item in chunks)
    assert any("list" in item["block_type"] for item in chunks)
    assert any("table" in item["block_type"] for item in chunks)
    assert any("formula" in item["block_type"] for item in chunks)


def test_chunking_is_bounded_deterministic_and_deduplicates_same_block():
    first = _chunks()
    second = _chunks()

    assert first == second
    assert all(
        knowledge_governance.LAYOUT_CHUNK_MIN_CHARS
        <= len(item["text"])
        <= knowledge_governance.LAYOUT_CHUNK_MAX_CHARS
        for item in first
    )
    assert (
        0
        <= knowledge_governance.LAYOUT_CHUNK_OVERLAP_CHARS
        < knowledge_governance.LAYOUT_CHUNK_MAX_CHARS
    )
    joined = "\n".join(item["text"] for item in first)
    assert joined.count("depends on charge") == 1
