from dataclasses import replace

from services import provider_readiness as readiness
from test_provider_readiness_contract import _input


def test_upstream_or_provenance_failure_never_ready():
    cases = (
        replace(_input(), upstream_fatal_reasons=("UPSTREAM_ENGLISH_BINDING_AMBIGUOUS",)),
        replace(_input(), provenance_gate_passed=False),
        replace(_input(), source_governance_passed=False),
        replace(_input(), english_evidence_refs=()),
    )
    assert all(
        readiness.evaluate_provider_readiness(value).decision == readiness.NOT_READY
        for value in cases
    )


def test_false_accept_style_pair_cannot_bypass_qualification():
    value = replace(
        _input(english_term="mass", chinese_term="冲量"),
        qualification_decision="REVIEW_REQUIRED",
        qualification_reason_codes=("EVIDENCE_TERM_SCOPE_RISK",),
    )
    result = readiness.evaluate_provider_readiness(value)
    assert result.decision == readiness.REVIEW_REQUIRED
    assert result.execution_admission is False
