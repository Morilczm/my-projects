import pytest

from services import alignment_providers
from services import llm_provider_config
from services import llm_transport
from services.formal_document_alignment_provider_selection import (
    FormalDocumentAlignmentProviderSelectionError,
    resolve_default_formal_document_alignment_provider_selection,
    resolve_formal_document_alignment_provider_selection,
)


FAKE_DEEPSEEK_KEY = "LEXIBRIDGE_FAKE_DEEPSEEK_KEY_FOR_TESTS_ONLY"


class SentinelTransport(llm_transport.BaseLLMTransport):
    def generate(self, prompt, config, request_options=None):
        return llm_transport.LLMTransportResult(status="success", raw_output="sentinel")


def _clear_external_env(monkeypatch):
    monkeypatch.delenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_explicit_injected_transport_takes_priority(monkeypatch):
    _clear_external_env(monkeypatch)
    sentinel = SentinelTransport()

    provider = alignment_providers.GuardedLLMAlignmentProvider(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        transport=sentinel,
    )

    assert provider.transport is sentinel


def test_replay_and_disabled_provider_transport_selection_is_unchanged(monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_KEY)

    replay = alignment_providers.get_alignment_provider(llm_provider_config.REPLAY_EXTERNAL_PROVIDER_NAME)
    disabled = alignment_providers.get_alignment_provider(llm_provider_config.DISABLED_EXTERNAL_PROVIDER_NAME)

    assert isinstance(replay.transport, llm_transport.ReplayLLMTransport)
    assert isinstance(disabled.transport, llm_transport.DisabledLLMTransport)
    assert disabled.config["executable"] is False


def test_formal_deepseek_provider_uses_real_transport_only_when_executable(monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_KEY)

    provider = alignment_providers.get_alignment_provider(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    )

    assert provider.provider_name == llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    assert provider.config["executable"] is True
    assert isinstance(provider.transport, llm_transport.DeepSeekHTTPTransport)


def test_formal_deepseek_provider_stays_disabled_when_flag_or_key_missing(monkeypatch):
    _clear_external_env(monkeypatch)
    without_flag = alignment_providers.get_alignment_provider(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    )

    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    without_key = alignment_providers.get_alignment_provider(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    )

    assert without_flag.config["feature_enabled"] is False
    assert without_flag.config["executable"] is False
    assert isinstance(without_flag.transport, llm_transport.DisabledLLMTransport)
    assert without_key.config["feature_enabled"] is True
    assert without_key.config["credential_present"] is False
    assert without_key.config["executable"] is False
    assert isinstance(without_key.transport, llm_transport.DisabledLLMTransport)


def test_default_formal_workflow_selection_remains_mock_only(monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_KEY)

    default = resolve_default_formal_document_alignment_provider_selection()

    assert default.provider_name == alignment_providers.MOCK_PROVIDER_NAME
    with pytest.raises(FormalDocumentAlignmentProviderSelectionError):
        resolve_formal_document_alignment_provider_selection(
            llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
        )
