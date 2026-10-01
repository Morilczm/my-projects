import json

import pytest

from services import llm_provider_config


FAKE_DEEPSEEK_KEY = "LEXIBRIDGE_FAKE_DEEPSEEK_KEY_FOR_TESTS_ONLY"


def _clear_external_env(monkeypatch):
    monkeypatch.delenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_deepseek_disabled_provider_stays_permanently_disabled(monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_KEY)

    config = llm_provider_config.get_llm_provider_config(
        llm_provider_config.DISABLED_EXTERNAL_PROVIDER_NAME,
        overrides={"enabled": True},
    )

    assert config["provider_name"] == "deepseek-alignment-v1-disabled"
    assert config["configured"] is True
    assert config["enabled"] is False
    assert config["feature_enabled"] is True
    assert config["credential_present"] is True
    assert config["executable"] is False
    with pytest.raises(llm_provider_config.LLMProviderConfigError) as exc:
        llm_provider_config.require_external_llm_enabled(
            llm_provider_config.DISABLED_EXTERNAL_PROVIDER_NAME,
            config=config,
        )
    assert exc.value.error_code == "provider_disabled"


def test_formal_deepseek_provider_is_registered_but_not_executable_by_default(monkeypatch):
    _clear_external_env(monkeypatch)

    config = llm_provider_config.get_llm_provider_config(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    )

    assert config["provider_name"] == "deepseek-alignment-v1"
    assert config["provider_type"] == "external_llm"
    assert config["configured"] is True
    assert config["enabled"] is True
    assert config["feature_enabled"] is False
    assert config["credential_present"] is False
    assert config["executable"] is False
    with pytest.raises(llm_provider_config.LLMProviderConfigError) as exc:
        llm_provider_config.require_external_llm_enabled(
            llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
            config=config,
        )
    assert exc.value.error_code == "provider_disabled"


def test_formal_deepseek_provider_requires_feature_flag_and_credential(monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    without_key = llm_provider_config.get_llm_provider_config(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    )

    assert without_key["enabled"] is True
    assert without_key["feature_enabled"] is True
    assert without_key["credential_present"] is False
    assert without_key["executable"] is False
    with pytest.raises(llm_provider_config.LLMProviderConfigError) as missing:
        llm_provider_config.require_external_llm_enabled(
            llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
            config=without_key,
        )
    assert missing.value.error_code == "credential_missing"

    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_KEY)
    executable = llm_provider_config.get_llm_provider_config(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    )

    assert executable["enabled"] is True
    assert executable["feature_enabled"] is True
    assert executable["credential_present"] is True
    assert executable["executable"] is True
    assert llm_provider_config.require_external_llm_enabled(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        config=executable,
    )


def test_formal_deepseek_config_sanitization_never_includes_secret(monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "yes")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_KEY)

    config = llm_provider_config.get_llm_provider_config(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    )
    sanitized = llm_provider_config.sanitize_provider_config({
        **config,
        "api_key": FAKE_DEEPSEEK_KEY,
        "base_url": "https://user:secret@api.deepseek.com/v1?api_key=secret",
    })

    assert sanitized["base_url"] == "https://api.deepseek.com/v1"
    assert sanitized["api_key_env_name"] == "DEEPSEEK_API_KEY"
    assert "api_key" not in sanitized
    assert FAKE_DEEPSEEK_KEY not in json.dumps(sanitized, sort_keys=True)


def test_only_formal_deepseek_provider_is_executable_external_alignment_provider(monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "on")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_KEY)

    external = {
        name: llm_provider_config.get_llm_provider_config(name)
        for name, raw in llm_provider_config.DEFAULT_PROVIDER_CONFIGS.items()
        if raw.get("provider_type") == "external_llm"
    }

    assert set(external) == {
        llm_provider_config.DISABLED_EXTERNAL_PROVIDER_NAME,
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
    }
    assert external[llm_provider_config.DISABLED_EXTERNAL_PROVIDER_NAME]["executable"] is False
    assert external[llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME]["executable"] is True
