from dataclasses import replace

from services import bilingual_evidence_qualification as qualification
from test_bilingual_evidence_qualification_contract import _input


def test_english_missing_and_ambiguous_cannot_qualify():
    missing = qualification.qualify_bilingual_evidence(
        replace(_input(), english_binding_status="missing")
    )
    ambiguous = qualification.qualify_bilingual_evidence(
        replace(_input(), english_binding_status="ambiguous")
    )

    assert missing.decision != qualification.QUALIFIED
    assert ambiguous.decision != qualification.QUALIFIED
    assert qualification.EVIDENCE_UPSTREAM_STATE_NOT_READY in missing.reason_codes
    assert qualification.EVIDENCE_UPSTREAM_STATE_NOT_READY in ambiguous.reason_codes


def test_retrieval_or_candidate_pool_fatal_state_cannot_qualify():
    retrieval = qualification.qualify_bilingual_evidence(
        replace(_input(), retrieval_status="fatal")
    )
    candidate_pool = qualification.qualify_bilingual_evidence(
        replace(_input(), candidate_pool_status="incomplete")
    )

    assert retrieval.decision != qualification.QUALIFIED
    assert candidate_pool.decision != qualification.QUALIFIED
    assert qualification.EVIDENCE_UPSTREAM_STATE_NOT_READY in retrieval.reason_codes
    assert qualification.EVIDENCE_UPSTREAM_STATE_NOT_READY in candidate_pool.reason_codes


def test_missing_top1_or_pair_execution_failure_fails_closed():
    no_top1 = qualification.qualify_bilingual_evidence(
        replace(_input(), pair_rank=0)
    )
    execution_failed = qualification.qualify_bilingual_evidence(
        replace(_input(), pair_execution_status="failed")
    )

    assert no_top1.decision == qualification.REJECTED
    assert execution_failed.decision == qualification.REJECTED
    assert qualification.EVIDENCE_PAIR_NOT_TOP1 in no_top1.reason_codes
    assert (
        qualification.EVIDENCE_QUALIFICATION_EXECUTION_FAILED
        in execution_failed.reason_codes
    )


def test_unspecified_upstream_state_fails_closed():
    value = replace(
        _input(),
        english_binding_status="unknown",
        retrieval_status="unknown",
        candidate_pool_status="unknown",
        pair_execution_status="unknown",
    )
    result = qualification.qualify_bilingual_evidence(value)
    assert result.decision == qualification.REJECTED
    assert qualification.EVIDENCE_UPSTREAM_STATE_NOT_READY in result.reason_codes
