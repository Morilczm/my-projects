from dataclasses import replace

from services import provider_execution as execution
from test_provider_execution_contract import _request


def test_review_not_ready_and_unqualified_never_reach_transport():
    cases = (
        replace(_request(), readiness_decision="REVIEW_REQUIRED"),
        replace(_request(), readiness_decision="NOT_READY"),
        replace(_request(), qualification_decision="REVIEW_REQUIRED"),
        replace(_request(), execution_admission=False),
        replace(_request(), readiness_policy="governed-provider-readiness@0.9.0"),
    )
    for value in cases:
        transport = execution.DeterministicFakeProviderTransport()
        result = execution.execute_provider_request(value, transport=transport)
        assert result.status == execution.BLOCKED
        assert transport.call_count == 0


def test_failed_privacy_provenance_or_budget_gate_denies_admission():
    for field in ("privacy_gate_passed", "provenance_gate_passed", "budget_gate_passed"):
        result = execution.execute_provider_request(
            replace(_request(), **{field: False}),
            transport=execution.DeterministicFakeProviderTransport(),
        )
        assert result.status == execution.BLOCKED
