import pytest

from services import provider_execution as execution
from test_provider_execution_contract import _request


@pytest.mark.parametrize("mode", ["malformed_json", "missing_fields", "natural_language"])
def test_invalid_or_unstructured_response_never_succeeds(mode):
    result = execution.execute_provider_request(
        _request(), transport=execution.DeterministicFakeProviderTransport(mode=mode)
    )
    assert result.status == execution.FAILED
    assert result.parse_status == "failed"
    assert result.reason_codes


def test_unknown_prompt_version_fails_before_transport():
    from dataclasses import replace

    transport = execution.DeterministicFakeProviderTransport()
    result = execution.execute_provider_request(
        replace(_request(), prompt_version="latest"), transport=transport
    )
    assert execution.PROVIDER_EXECUTION_PROMPT_VERSION_INVALID in result.reason_codes
    assert transport.call_count == 0
