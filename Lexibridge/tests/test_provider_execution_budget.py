from dataclasses import replace

from services import provider_execution as execution
from test_provider_execution_contract import _request


def test_token_and_cost_budget_fail_before_transport():
    for value in (
        replace(_request(), request_token_ceiling=1),
        replace(_request(), cost_ceiling=-1),
    ):
        transport = execution.DeterministicFakeProviderTransport()
        result = execution.execute_provider_request(value, transport=transport)
        assert execution.PROVIDER_EXECUTION_BUDGET_EXCEEDED in result.reason_codes
        assert transport.call_count == 0


def test_timeout_retries_only_within_budget():
    transport = execution.DeterministicFakeProviderTransport(mode="timeout")
    result = execution.execute_provider_request(
        replace(_request(), retry_budget=2), transport=transport
    )
    assert result.status == execution.FAILED
    assert result.retry_count == 2
    assert transport.call_count == 3
