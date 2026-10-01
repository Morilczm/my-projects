from dataclasses import replace

from services import provider_execution as execution
from test_provider_execution_contract import _request


def test_same_idempotency_key_and_payload_executes_once():
    ledger = execution.InMemoryExecutionLedger()
    transport = execution.DeterministicFakeProviderTransport()
    first = execution.execute_provider_request(_request(), transport=transport, ledger=ledger)
    second = execution.execute_provider_request(_request(), transport=transport, ledger=ledger)
    assert first.status == execution.SUCCEEDED
    assert second.status == execution.REUSED
    assert transport.call_count == 1


def test_same_key_with_different_payload_is_conflict():
    ledger = execution.InMemoryExecutionLedger()
    transport = execution.DeterministicFakeProviderTransport()
    execution.execute_provider_request(_request(), transport=transport, ledger=ledger)
    conflict = execution.execute_provider_request(
        replace(_request(), chinese_term="电势能"), transport=transport, ledger=ledger
    )
    assert execution.PROVIDER_EXECUTION_IDEMPOTENCY_CONFLICT in conflict.reason_codes
    assert transport.call_count == 1
