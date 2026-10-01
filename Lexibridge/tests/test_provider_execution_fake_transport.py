from services import provider_execution as execution
from test_provider_execution_contract import _request


def test_fake_transport_never_uses_network_or_credentials():
    transport = execution.DeterministicFakeProviderTransport()
    execution.execute_provider_request(_request(), transport=transport)
    assert transport.network_calls == 0
    assert transport.credential_reads == 0


def test_non_retryable_error_does_not_retry():
    transport = execution.DeterministicFakeProviderTransport(mode="non_retryable_error")
    result = execution.execute_provider_request(_request(), transport=transport)
    assert result.status == execution.FAILED
    assert result.retry_count == 0
    assert transport.call_count == 1
