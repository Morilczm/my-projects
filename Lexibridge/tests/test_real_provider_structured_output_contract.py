import json
import urllib.request

import pytest

from services import alignment_output_parser
from services import alignment_prompting
from services import alignment_providers
from services import llm_provider_config
from services import llm_transport


FAKE_KEY = "test-only-key"


class FakeExecutor:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return llm_transport.LLMHTTPResponse(
            status_code=200,
            body=json.dumps(self.payload),
            headers={"content-type": "application/json"},
        )


def _config(**overrides):
    config = {
        **llm_provider_config.DEFAULT_PROVIDER_CONFIGS[
            llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
        ],
        "feature_enabled": True,
        "credential_present": True,
        "executable": True,
    }
    config.update(overrides)
    return config


def _envelope(*, content=None, model="deepseek-chat", finish_reason="stop"):
    return {
        "model": model,
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {
                    "content": (
                        llm_transport.build_fixture_response("valid")
                        if content is None
                        else content
                    ),
                    "reasoning_content": '{"must_not_be_used": true}',
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("network access is forbidden")
        ),
    )


def _run(envelope, **config_overrides):
    executor = FakeExecutor(envelope)
    transport = llm_transport.DeepSeekHTTPTransport(
        http_executor=executor,
        credential_resolver=lambda _name: FAKE_KEY,
    )
    result = transport.generate(
        "Return JSON.",
        _config(**config_overrides),
        {"response_format": None, "max_tokens": 999999},
    )
    return result, executor


def test_deepseek_request_enforces_json_object_and_bounded_output_tokens():
    result, executor = _run(_envelope())

    assert result.status == "success"
    payload = json.loads(executor.requests[0].body)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == llm_provider_config.DEFAULT_MAX_OUTPUT_TOKENS
    assert payload["max_tokens"] >= llm_provider_config.MIN_ALIGNMENT_SCHEMA_OUTPUT_TOKENS
    assert result.metadata["response_format"] == "json_object"


def test_real_provider_adapter_cannot_be_downgraded_to_legacy_prompt(monkeypatch):
    class CapturingReplay(llm_transport.ReplayLLMTransport):
        def __init__(self):
            self.prompt = ""

        def generate(self, prompt, config, request_options=None):
            self.prompt = prompt
            return super().generate(prompt, config, request_options)

    transport = CapturingReplay()
    monkeypatch.setattr(
        llm_provider_config,
        "get_llm_provider_config",
        lambda *_args, **_kwargs: _config(max_estimated_cost=1.0),
    )
    monkeypatch.setattr(
        llm_provider_config,
        "require_external_llm_enabled",
        lambda *_args, **_kwargs: True,
    )
    provider = alignment_providers.GuardedLLMAlignmentProvider(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        transport=transport,
    )
    output = provider.verify_alignment(
        {
            "english_term": "synthetic",
            "chinese_term": "合成",
            "english_evidence": [
                {"source_uid": "en-source", "chunk_uid": "en-chunk"}
            ],
            "chinese_evidence": [
                {"source_uid": "zh-source", "chunk_uid": "zh-chunk"}
            ],
            "provider_options": {
                "prompt_version": alignment_prompting.LEGACY_PROMPT_VERSION
            },
        }
    )

    assert output["prompt_version"] == alignment_prompting.STRUCTURED_PROMPT_VERSION
    assert output["parser_version"] == alignment_output_parser.STRUCTURED_PARSER_VERSION
    assert f"Prompt version: {alignment_prompting.STRUCTURED_PROMPT_VERSION}" in transport.prompt


def test_structured_prompt_is_versioned_and_matches_strict_parser_schema():
    prompt = alignment_prompting.build_alignment_prompt(
        {"english_term": "synthetic term", "chinese_term": "合成术语"},
        alignment_prompting.STRUCTURED_PROMPT_VERSION,
    )

    assert alignment_prompting.LEGACY_PROMPT_VERSION in alignment_prompting.list_prompt_versions()
    assert alignment_prompting.STRUCTURED_PROMPT_VERSION in alignment_prompting.list_prompt_versions()
    assert "JSON" in prompt
    assert "single JSON object" in prompt
    assert "Markdown code fence" in prompt
    for field in alignment_output_parser.REQUIRED_OUTPUT_FIELDS:
        assert f'"{field}"' in prompt


@pytest.mark.parametrize(
    "raw",
    [
        "plain natural language",
        "Explanation first\n{}",
        "```json\n{}\n```",
        '{"alignment_decision":',
        "",
    ],
)
def test_parser_remains_strict_and_does_not_extract_json_substrings(raw):
    with pytest.raises(alignment_output_parser.AlignmentOutputParserError):
        alignment_output_parser.parse_alignment_provider_output(raw)


def test_finish_reason_length_fails_closed_before_parser():
    result, _executor = _run(_envelope(finish_reason="length"))

    assert result.status == "error"
    assert result.error_code == "response_truncated"
    assert result.metadata["finish_reason"] == "length"


def test_transport_never_uses_reasoning_content_as_response_content():
    envelope = _envelope(content="")
    envelope["choices"][0]["message"].pop("content")
    result, _executor = _run(envelope)

    assert result.status == "error"
    assert result.error_code == "missing_response_content"


def test_structured_parser_rejects_unknown_source_or_chunk_provenance():
    parsed = json.loads(llm_transport.build_fixture_response("valid"))
    parsed["evidence_citations"] = {
        "english": [{"source_uid": "unknown", "chunk_uid": "unknown"}],
        "chinese": [{"source_uid": "zh-source", "chunk_uid": "zh-chunk"}],
    }

    with pytest.raises(
        alignment_output_parser.AlignmentOutputParserError
    ) as exc_info:
        alignment_output_parser.parse_structured_alignment_provider_output(
            parsed,
            allowed_provenance={
                "english": {("en-source", "en-chunk")},
                "chinese": {("zh-source", "zh-chunk")},
            },
        )

    assert exc_info.value.error_code == "invalid_alignment_output_provenance"


def test_structured_parser_rejects_schema_external_success_fields():
    parsed = json.loads(llm_transport.build_fixture_response("valid"))
    parsed["provider_execution_succeeded"] = True
    allowed = {
        "english": {("fixture-en-source", "fixture-en-chunk")},
        "chinese": {("fixture-zh-source", "fixture-zh-chunk")},
    }

    with pytest.raises(
        alignment_output_parser.AlignmentOutputParserError
    ) as exc_info:
        alignment_output_parser.parse_structured_alignment_provider_output(
            parsed,
            allowed_provenance=allowed,
        )

    assert exc_info.value.error_code == "invalid_alignment_output_schema"


def test_model_compatibility_is_explicit_and_audited():
    allowed, _executor = _run(_envelope(model="deepseek-v4-flash"))
    blocked, _executor = _run(_envelope(model="deepseek-v4-pro"))

    assert allowed.status == "success"
    assert allowed.metadata["requested_model"] == "deepseek-chat"
    assert allowed.metadata["resolved_model"] == "deepseek-v4-flash"
    assert (
        allowed.metadata["model_policy_version"]
        == llm_provider_config.DEEPSEEK_MODEL_POLICY_VERSION
    )
    assert blocked.status == "error"
    assert blocked.error_code == "response_model_not_allowed"


def test_pricing_policy_is_versioned_and_missing_prices_are_not_zero():
    configured = llm_provider_config.estimate_alignment_call_cost(
        {"prompt_chars": 4000, "expected_output_chars": 1000},
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        config=_config(max_estimated_cost=1.0),
    )
    missing = llm_provider_config.estimate_alignment_call_cost(
        {"prompt_chars": 4000, "expected_output_chars": 1000},
        llm_provider_config.REPLAY_EXTERNAL_PROVIDER_NAME,
        config={
            **llm_provider_config.DEFAULT_PROVIDER_CONFIGS[
                llm_provider_config.REPLAY_EXTERNAL_PROVIDER_NAME
            ],
            "cost_per_1k_input_tokens": None,
            "cost_per_1k_output_tokens": None,
        },
    )

    assert configured["pricing_policy_version"]
    assert configured["pricing_model_identity"] == "deepseek-chat"
    assert configured["currency"] == "USD"
    assert configured["estimated_cost"] > 0
    assert missing["pricing_available"] is False
    assert missing["estimated_cost"] is None
    assert missing["exceeds_limit"] is None


def test_sanitized_output_diagnostics_never_store_response_text():
    secret_body = '{"secret_response_text":"must-never-persist"}'
    diagnostics = alignment_output_parser.build_sanitized_output_diagnostics(
        secret_body,
        finish_reason="stop",
        response_model="deepseek-v4-flash",
        validation_stage="schema_validation",
        parser_reason="provider_schema_invalid",
    )
    serialized = json.dumps(diagnostics, sort_keys=True)

    assert diagnostics["content_present"] is True
    assert diagnostics["first_non_whitespace_character_class"] == "object_open"
    assert diagnostics["looks_like_json_object"] is True
    assert diagnostics["outer_code_fence_present"] is False
    assert diagnostics["response_hash"]
    assert "must-never-persist" not in serialized
    assert "secret_response_text" not in serialized
