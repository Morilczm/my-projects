import inspect

from scripts.evaluations import candidate_boundary_evaluation
from services.document_alignment_term_candidates import (
    CANDIDATE_GOVERNANCE_OVERFLOW_REJECTED,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS,
    GovernedSourceChunkSnapshot,
    extract_chunk_scoped_term_candidates,
)


def _terms(app_module, text):
    return {
        item["english_term"].casefold(): item
        for item in app_module.extract_terms_from_text(text)
    }


def _chunk(uid, index, text):
    return GovernedSourceChunkSnapshot(
        chunk_uid=uid,
        source_uid="source-boundary",
        parse_uid="parse-boundary",
        source_version="1",
        chunk_index=index,
        text=text,
        language="en",
    )


def test_definition_predicate_boundary_extracts_exact_mass_subject(app_module):
    terms = _terms(
        app_module,
        "Mass measures the amount of matter in an object.",
    )

    assert "mass" in terms
    assert all(not term.startswith("mass measures") for term in terms)


def test_definition_predicate_boundary_extracts_exact_angular_momentum_subject(
    app_module,
):
    terms = _terms(
        app_module,
        "Angular momentum describes rotational motion about an axis.",
    )

    assert "angular momentum" in terms
    assert all("describes" not in term for term in terms)


def test_unseen_definition_predicate_subjects_use_the_same_general_boundary(
    app_module,
):
    terms = _terms(
        app_module,
        "Magnetic moment describes the magnetic strength of a system. "
        "Specific heat measures the energy needed per unit temperature change.",
    )

    assert "magnetic moment" in terms
    assert "specific heat" in terms


def test_definition_predicate_and_complete_clause_are_not_candidates(app_module):
    terms = _terms(
        app_module,
        "Magnetic moment describes rotational response in an applied field.",
    )

    assert "magnetic moment" in terms
    assert all("describes" not in term for term in terms)
    assert all(len(term.split()) <= 4 for term in terms)


def test_ordinary_leading_subjects_do_not_create_candidate_explosion(app_module):
    terms = _terms(
        app_module,
        "The instructor describes the schedule after lunch. "
        "A student measures the table before class. "
        "They record the result in a notebook.",
    )

    assert len(terms) <= 5
    assert "the instructor" not in terms
    assert "a student" not in terms


def test_boundary_candidate_preserves_span_provenance_and_canonical_dedup(
    app_module,
):
    chunks = (
        _chunk(
            "chunk-boundary-a",
            0,
            "Magnetic moment describes the magnetic strength of a system.",
        ),
        _chunk(
            "chunk-boundary-b",
            1,
            "MAGNETIC MOMENT describes rotational response in a field.",
        ),
    )
    result = extract_chunk_scoped_term_candidates(
        chunks,
        app_module.extract_terms_from_text,
        expected_source_uid="source-boundary",
        expected_parse_uid="parse-boundary",
        expected_source_version="1",
    )
    matches = [
        candidate
        for candidate in result.candidates
        if candidate.normalized_term == "magnetic moment"
    ]

    assert len(matches) == 1
    assert matches[0].candidate_term == "Magnetic moment"
    assert matches[0].source_uid == "source-boundary"
    assert matches[0].source_chunk_uids == (
        "chunk-boundary-a",
        "chunk-boundary-b",
    )
    assert matches[0].candidate_id


def test_boundary_contract_does_not_change_fifty_item_governance(app_module):
    terms = [{"english_term": f"Candidate Term {index:02d}"} for index in range(55)]
    result = extract_chunk_scoped_term_candidates(
        (_chunk("chunk-boundary-governance", 0, "content"),),
        lambda _text: terms,
        expected_source_uid="source-boundary",
        expected_parse_uid="parse-boundary",
        expected_source_version="1",
    )

    assert result.admitted_candidate_count == FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS
    assert result.overflow_candidate_count == 5
    assert result.canonical_candidate_count == 55
    assert all(
        candidate.governance_status == CANDIDATE_GOVERNANCE_OVERFLOW_REJECTED
        for candidate in result.overflow_candidates
    )


def test_boundary_extractor_has_no_gold_alias_or_provider_input(app_module):
    signature = inspect.signature(app_module.extract_terms_from_text)

    assert tuple(signature.parameters) == ("text",)


def test_frozen_boundary_evaluation_closes_defects_without_reordering_governance():
    artifact = candidate_boundary_evaluation.evaluate()

    assert artifact["status"] == "RESIDUAL_CANDIDATE_BOUNDARY_CONTRACT_CLOSED"
    assert artifact["after"]["boundary_defect_count"] == 0
    assert artifact["after"]["extraction_missing_count"] == 0
    assert artifact["after"]["definition_fragment_false_positive_count"] == 0
    assert artifact["after"]["exact_matched"] == 25
    assert artifact["torque_overflow_audit"]["ordering_contract_unchanged"] is True
    assert artifact["torque_overflow_audit"]["benchmark_promotion_added"] is False
    assert artifact["benchmark_specific_rules_added"] is False
    assert artifact["real_provider_requests"] == 0
    assert artifact["accident_database_before"] == artifact["accident_database_after"]
