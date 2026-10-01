import inspect

from scripts.evaluations import candidate_residual_evaluation
from services.document_alignment_term_candidates import (
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS,
    GovernedSourceChunkSnapshot,
    extract_chunk_scoped_term_candidates,
)


def _terms(app_module, text):
    return [
        item["english_term"].casefold()
        for item in app_module.extract_terms_from_text(text)
    ]


def test_copular_scientific_definition_subjects_are_extracted(app_module):
    charge = _terms(
        app_module,
        "Electric charge is a property of matter that causes electric interactions.",
    )
    field = _terms(
        app_module,
        "Electric field is force per unit positive test charge at a point.",
    )

    assert "electric charge" in charge
    assert "electric field" in field


def test_unseen_scientific_definition_subjects_use_the_same_general_contract(app_module):
    terms = _terms(
        app_module,
        "Magnetic flux is a measure through a surface. "
        "Photon energy is the energy carried by one photon.",
    )

    assert "magnetic flux" in terms
    assert "photon energy" in terms


def test_ordinary_prose_does_not_create_a_candidate_explosion(app_module):
    terms = _terms(
        app_module,
        "Students carry blue folders to class. "
        "They discuss several examples and write short notes. "
        "The teacher checks the work after lunch.",
    )

    assert len(terms) <= 4
    assert "students carry" not in terms
    assert "blue folders" not in terms
    assert "teacher checks" not in terms


def test_definition_sentence_is_not_emitted_as_a_candidate(app_module):
    terms = _terms(
        app_module,
        "Magnetic flux is a measure of magnetic field through a surface.",
    )

    assert "magnetic flux" in terms
    assert all("is a measure" not in term for term in terms)
    assert all(len(term.split()) <= 4 for term in terms)


def test_chunk_scoped_candidate_preserves_span_identity_and_dedup(app_module):
    chunks = (
        GovernedSourceChunkSnapshot(
            chunk_uid="chunk-residual-a",
            source_uid="source-residual",
            parse_uid="parse-residual",
            source_version="1",
            chunk_index=0,
            text="Magnetic flux is a measure through a surface.",
            language="en",
        ),
        GovernedSourceChunkSnapshot(
            chunk_uid="chunk-residual-b",
            source_uid="source-residual",
            parse_uid="parse-residual",
            source_version="1",
            chunk_index=1,
            text="MAGNETIC FLUX is conserved in this idealized example.",
            language="en",
        ),
    )
    result = extract_chunk_scoped_term_candidates(
        chunks,
        app_module.extract_terms_from_text,
        expected_source_uid="source-residual",
        expected_parse_uid="parse-residual",
        expected_source_version="1",
    )
    matches = [
        candidate for candidate in result.candidates
        if candidate.normalized_term == "magnetic flux"
    ]

    assert len(matches) == 1
    assert matches[0].candidate_term == "Magnetic flux"
    assert matches[0].source_uid == "source-residual"
    assert matches[0].source_chunk_uids == (
        "chunk-residual-a",
        "chunk-residual-b",
    )
    assert matches[0].candidate_id


def test_extractor_has_no_gold_alias_or_provider_input(app_module):
    signature = inspect.signature(app_module.extract_terms_from_text)
    assert tuple(signature.parameters) == ("text",)


def test_residual_rule_does_not_change_fifty_item_governance(app_module):
    chunk = GovernedSourceChunkSnapshot(
        chunk_uid="chunk-governance",
        source_uid="source-governance",
        parse_uid="parse-governance",
        source_version="1",
        chunk_index=0,
        text="content",
    )
    terms = [{"english_term": f"Candidate Term {index:02d}"} for index in range(55)]
    result = extract_chunk_scoped_term_candidates(
        (chunk,),
        lambda _text: terms,
        expected_source_uid="source-governance",
        expected_parse_uid="parse-governance",
        expected_source_version="1",
    )

    assert len(result.candidates) == FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS
    assert len(result.overflow_candidates) == 5
    assert result.canonical_candidate_count == 55


def test_frozen_residual_diagnosis_separates_extraction_boundary_and_overflow():
    artifact = candidate_residual_evaluation.evaluate()

    assert sum(artifact["after_attribution_counts"].values()) == 11
    assert artifact["after"]["extraction_missing_count"] == 0
    assert artifact["after_attribution_counts"].get("EXTRACTION_MISSING", 0) == 0
    assert set(artifact["after_attribution_counts"]) <= {
        "CANDIDATE_BOUNDARY_DEFECT",
        "MATCHED",
        "OVERFLOW_NOT_ADMITTED",
    }
    assert artifact["real_provider_requests"] == 0
    assert artifact["accident_database_before"] == artifact["accident_database_after"]
