from dataclasses import asdict

from scripts.evaluations import candidate_overflow_governance
from services.document_alignment_term_candidates import (
    EXTRACTION_OUTCOME_EXTRACTED,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS,
    GovernedSourceChunkSnapshot,
    extract_chunk_scoped_term_candidates,
)


def _chunk(text="content"):
    return GovernedSourceChunkSnapshot(
        chunk_uid="chunk-overflow-12b1",
        source_uid="source-overflow-12b1",
        parse_uid="parse-overflow-12b1",
        source_version="1",
        chunk_index=0,
        text=text,
        language="en",
    )


def _extract(count, *, duplicate=False):
    terms = [
        {
            "english_term": f"Candidate Term {index:02d}",
            # These benchmark-like fields must be ignored by governance.
            "gold_english_term": "must-not-be-read",
            "gold_chinese_term": "不得读取",
            "accepted_aliases": ["must-not-be-read"],
            "benchmark_score": 999,
            "required_propositions": ["must-not-be-read"],
        }
        for index in range(count)
    ]
    if duplicate:
        terms.append({"english_term": "Ｃａｎｄｉｄａｔｅ   Term 00"})
    return extract_chunk_scoped_term_candidates(
        (_chunk(),),
        lambda _text: terms,
        expected_source_uid="source-overflow-12b1",
        expected_parse_uid="parse-overflow-12b1",
        expected_source_version="1",
    )


def _identities(values):
    return [candidate.candidate_id for candidate in values]


def test_exactly_fifty_candidates_preserve_existing_admission_behavior():
    result = _extract(FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS)

    assert result.outcome == EXTRACTION_OUTCOME_EXTRACTED
    assert len(result.candidates) == 50
    assert result.overflow_candidates == ()
    assert result.admitted_candidate_count == 50
    assert result.overflow_candidate_count == 0
    assert all(item.governance_status == "admitted" for item in result.candidates)


def test_fifty_one_candidates_are_bounded_without_whole_set_rejection():
    result = _extract(51)

    assert result.outcome == EXTRACTION_OUTCOME_EXTRACTED
    assert len(result.candidates) == 50
    assert len(result.overflow_candidates) == 1
    assert result.canonical_candidate_count == 51
    assert result.admitted_candidate_count + result.overflow_candidate_count == 51
    assert result.overflow_candidates[0].governance_status == "overflow_rejected"


def test_fifty_five_candidates_preserve_every_identity_and_provenance():
    result = _extract(55)
    all_candidates = (*result.candidates, *result.overflow_candidates)

    assert len(result.candidates) == 50
    assert len(result.overflow_candidates) == 5
    assert len(set(_identities(all_candidates))) == 55
    assert all(item.candidate_id for item in all_candidates)
    assert all(item.normalized_term for item in all_candidates)
    assert all(item.source_chunk_uids == ("chunk-overflow-12b1",) for item in all_candidates)
    assert all(item.governance_reason for item in all_candidates)


def test_threshold_applies_after_normalized_deduplication():
    result = _extract(50, duplicate=True)

    assert result.raw_occurrence_count == 51
    assert result.canonical_candidate_count == 50
    assert len(result.candidates) == 50
    assert result.overflow_candidates == ()


def test_selection_and_overflow_order_are_deterministic_and_gold_isolated():
    first = _extract(55)
    second = _extract(55)

    assert _identities(first.candidates) == _identities(second.candidates)
    assert _identities(first.overflow_candidates) == _identities(second.overflow_candidates)
    serialized = repr([asdict(item) for item in (*first.candidates, *first.overflow_candidates)])
    for forbidden in (
        "must-not-be-read",
        "不得读取",
        "benchmark_score",
        "required_propositions",
        "accepted_aliases",
    ):
        assert forbidden not in serialized


def test_public_call_cannot_raise_or_disable_the_production_limit():
    terms = [{"english_term": f"Candidate Term {index:02d}"} for index in range(55)]
    result = extract_chunk_scoped_term_candidates(
        (_chunk(),),
        lambda _text: terms,
        expected_source_uid="source-overflow-12b1",
        expected_parse_uid="parse-overflow-12b1",
        expected_source_version="1",
        max_items=500,
    )

    assert result.admitted_candidate_count == FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS
    assert result.overflow_candidate_count == 5


def test_frozen_mechanics_overflow_reaches_binding_and_readiness_without_provider():
    artifact = candidate_overflow_governance.evaluate()
    mechanics = next(
        item for item in artifact["source_results"]
        if item["source_id"] == "english-mechanics"
    )

    assert mechanics["source_id"] == "english-mechanics"
    assert mechanics["admitted_candidates"] == FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS
    assert mechanics["overflow_candidates"] > 0
    assert (
        mechanics["admitted_candidates"] + mechanics["overflow_candidates"]
        == mechanics["canonical_candidates"]
    )
    assert mechanics["whole_set_rejected"] is False
    assert mechanics["governance_status"] == "overflow_rejected"
    assert artifact["after"]["exact_matched"] > artifact["before"]["exact_matched"]
    assert artifact["after"]["provider_ready"] >= 1
    assert artifact["real_provider_requests"] == 0
    assert artifact["accident_database_before"] == artifact["accident_database_after"]
