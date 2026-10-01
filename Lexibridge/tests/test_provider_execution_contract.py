from dataclasses import replace

from services import provider_execution as execution


def _request(**overrides):
    values = {
        "readiness_decision": "READY",
        "readiness_policy": "governed-provider-readiness@1.0.0",
        "readiness_result_id": "provider-readiness:" + "a" * 64,
        "qualification_decision": "QUALIFIED",
        "qualification_policy": "governed-bilingual-evidence-qualification@1.1.0",
        "qualification_result_id": "qualification:" + "b" * 64,
        "execution_admission": True,
        "privacy_gate_passed": True,
        "provenance_gate_passed": True,
        "budget_gate_passed": True,
        "provider_id": "fake-llm-v1",
        "model_id": "fake-llm-v1:v1",
        "prompt_registry_id": "term_alignment",
        "prompt_version": "v1",
        "english_term": "electric potential",
        "english_context": "Bounded English definition context.",
        "english_evidence": ("en-source:en-chunk:0:20",),
        "chinese_term": "电势",
        "chinese_context": "有界中文定义证据。",
        "chinese_evidence": ("zh-source:zh-chunk:0:8",),
        "request_token_ceiling": 1200,
        "cost_ceiling": 0.05,
        "timeout_seconds": 30,
        "retry_budget": 1,
        "idempotency_key": "execution-item-1",
        "audit_correlation_id": "audit-item-1",
    }
    values.update(overrides)
    return execution.ProviderExecutionRequest(**values)


def test_ready_request_executes_fake_transport_and_parses_schema():
    transport = execution.DeterministicFakeProviderTransport()
    result = execution.execute_provider_request(
        _request(), transport=transport, ledger=execution.InMemoryExecutionLedger()
    )
    assert result.status == execution.SUCCEEDED
    assert result.parse_status == "parsed"
    assert result.request_count == 1
    assert result.network_called is False
    assert result.real_provider_requests == 0


def test_result_is_sanitized_and_auditable():
    result = execution.execute_provider_request(
        _request(), transport=execution.DeterministicFakeProviderTransport()
    )
    payload = execution.serialize_execution_result(result)
    assert payload["request_hash"]
    assert payload["response_hash"]
    assert payload["idempotency_key_hash"]
    assert payload["created_by_policy"] == "governed-provider-execution@1.0.0"
    assert "Bounded English" not in repr(payload)
    assert "有界中文" not in repr(payload)
