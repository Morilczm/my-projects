import json
import socket
import urllib.request

import pytest

from services import llm_provider_config
from services import llm_transport


FAKE_DEEPSEEK_KEY = "LEXIBRIDGE_FAKE_DEEPSEEK_KEY_FOR_TESTS_ONLY"


@pytest.fixture(autouse=True)
def fail_on_real_network(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected real network")),
    )


class FakeExecutor:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def _config(**overrides):
    config = {
        "provider_name": llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        "provider_type": "external_llm",
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-chat",
        "timeout_seconds": 30,
        "max_retries": 0,
        "max_output_chars": 4000,
        "enabled": True,
        "feature_enabled": True,
        "credential_present": True,
        "executable": True,
        "replay_mode": False,
        "api_key_env_name": "DEEPSEEK_API_KEY",
    }
    config.update(overrides)
    return config


def _response(status_code, payload):
    if isinstance(payload, str):
        body = payload
    else:
        body = json.dumps(payload)
    return llm_transport.LLMHTTPResponse(status_code=status_code, body=body, headers={"content-type": "application/json"})


def _success_body(content=None):
    return {
        "id": "chatcmpl-test",
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content or llm_transport.build_fixture_response("valid"),
                },
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 17, "total_tokens": 28},
    }


def _transport(executor):
    return llm_transport.DeepSeekHTTPTransport(
        http_executor=executor,
        credential_resolver=lambda env_name: FAKE_DEEPSEEK_KEY if env_name == "DEEPSEEK_API_KEY" else "",
    )


def test_deepseek_transport_success_posts_openai_compatible_payload_without_secret():
    executor = FakeExecutor(_response(200, _success_body()))
    transport = _transport(executor)

    assert executor.requests == []

    result = transport.generate("Alignment prompt", _config(), {})

    assert result.status == "success"
    assert result.raw_output == llm_transport.build_fixture_response("valid")
    assert result.request_count == 1
    assert result.retry_count == 0
    assert result.metadata["provider"] == llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    assert result.metadata["model"] == "deepseek-chat"
    assert result.metadata["http_status"] == 200
    assert result.metadata["usage"] == {"prompt_tokens": 11, "completion_tokens": 17, "total_tokens": 28}
    assert result.metadata["finish_reason"] == "stop"
    assert result.metadata["response_model"] == "deepseek-chat"
    request = executor.requests[0]
    assert request.method == "POST"
    assert request.url == "https://api.deepseek.com/chat/completions"
    assert request.timeout_seconds == 30
    assert request.headers["Authorization"] == f"Bearer {FAKE_DEEPSEEK_KEY}"
    assert FAKE_DEEPSEEK_KEY not in repr(request)
    assert "Authorization" not in repr(request)
    payload = json.loads(request.body)
    assert payload["model"] == "deepseek-chat"
    assert payload["messages"] == [{"role": "user", "content": "Alignment prompt"}]
    assert payload["stream"] is False
    assert FAKE_DEEPSEEK_KEY not in json.dumps(result.__dict__, sort_keys=True)


def test_deepseek_transport_accepts_missing_usage_metadata():
    body = _success_body()
    body.pop("usage")
    executor = FakeExecutor(_response(200, body))

    result = _transport(executor).generate("prompt", _config(), {})

    assert result.status == "success"
    assert result.metadata["usage"] == {}
    assert result.metadata["finish_reason"] == "stop"


def test_deepseek_transport_preflight_failures_do_not_call_executor():
    executor = FakeExecutor(_response(200, _success_body()))
    missing_key = llm_transport.DeepSeekHTTPTransport(
        http_executor=executor,
        credential_resolver=lambda _env_name: "",
    ).generate("prompt", _config(), {})
    disabled = _transport(executor).generate("prompt", _config(enabled=False, executable=False), {})
    feature_disabled = _transport(executor).generate("prompt", _config(feature_enabled=False, executable=False), {})

    assert missing_key.error_code == "credential_missing"
    assert disabled.error_code == "provider_disabled"
    assert feature_disabled.error_code == "provider_disabled"
    assert missing_key.request_count == 0
    assert disabled.request_count == 0
    assert feature_disabled.request_count == 0
    assert executor.requests == []


def test_deepseek_transport_maps_http_errors():
    cases = [
        (400, "invalid_request"),
        (401, "authentication_failed"),
        (403, "authentication_failed"),
        (429, "rate_limited"),
        (500, "provider_server_error"),
        (502, "provider_server_error"),
        (503, "provider_server_error"),
    ]

    for status_code, error_code in cases:
        executor = FakeExecutor(_response(status_code, {"error": "not returned"}))
        result = _transport(executor).generate("prompt", _config(), {})

        assert result.status == "error"
        assert result.error_code == error_code
        assert result.request_count == 1
        assert result.retry_count == 0
        assert FAKE_DEEPSEEK_KEY not in result.error_message


def test_deepseek_transport_maps_timeout_and_network_errors():
    cases = [
        (llm_transport.LLMTransportConnectionTimeout("connect"), "connection_timeout"),
        (llm_transport.LLMTransportReadTimeout("read"), "read_timeout"),
        (socket.timeout("read timed out"), "read_timeout"),
        (llm_transport.LLMTransportNetworkError("network failed"), "network_error"),
    ]

    for error, error_code in cases:
        executor = FakeExecutor(error=error)
        result = _transport(executor).generate("prompt", _config(), {})

        assert result.status == "error"
        assert result.error_code == error_code
        assert result.request_count == 1
        assert result.retry_count == 0
        assert FAKE_DEEPSEEK_KEY not in result.error_message


def test_deepseek_transport_rejects_invalid_or_malformed_provider_envelope():
    cases = [
        ("not json", "invalid_json"),
        ({"model": "deepseek-chat"}, "malformed_provider_response"),
        ({"choices": []}, "malformed_provider_response"),
        ({"choices": [{"message": {}}]}, "missing_response_content"),
        ({"choices": [{"message": {"content": ""}}]}, "missing_response_content"),
        ({"choices": [{"message": {"content": {"json": "object"}}}]}, "missing_response_content"),
    ]

    for payload, error_code in cases:
        executor = FakeExecutor(_response(200, payload))
        result = _transport(executor).generate("prompt", _config(), {})

        assert result.status == "error"
        assert result.error_code == error_code
        assert result.request_count == 1
        assert result.retry_count == 0
        assert FAKE_DEEPSEEK_KEY not in result.error_message
