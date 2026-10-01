from dataclasses import replace

from services import provider_readiness as readiness
from test_provider_readiness_contract import _input


def test_local_preflight_gates_are_fail_closed():
    cases = (
        replace(_input(), privacy_gate_passed=False),
        replace(_input(), prompt_approved=False),
        replace(_input(), provider_allowed=False),
        replace(_input(), provider_config_complete=False),
        replace(_input(), request_token_budget=0),
        replace(_input(), retry_budget=9),
        replace(_input(), timeout_seconds=0),
        replace(_input(), audit_context=""),
    )
    results = [readiness.evaluate_provider_readiness(value) for value in cases]
    assert all(result.decision == readiness.NOT_READY for result in results)
    assert all(result.reason_codes for result in results)


def test_readiness_contract_has_no_network_or_credential_value_fields(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-be-read")
    result = readiness.evaluate_provider_readiness(_input())
    payload = readiness.serialize_provider_readiness_result(result)
    assert payload["network_called"] is False
    assert "api_key" not in repr(payload).lower()
    assert "must-not-be-read" not in repr(payload)
