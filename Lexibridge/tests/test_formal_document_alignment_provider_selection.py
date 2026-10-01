import dataclasses

import pytest

from services import alignment_output_parser, alignment_prompting, alignment_providers, llm_provider_config
from services.formal_document_alignment_provider_selection import (
    FORMAL_DEFAULT_MODEL_IDENTITY,
    FORMAL_DEFAULT_PROVIDER_NAME,
    FormalDocumentAlignmentProviderSelection,
    FormalDocumentAlignmentProviderSelectionError,
    resolve_default_formal_document_alignment_provider_selection,
    resolve_formal_document_alignment_provider_selection,
)


def test_default_selection_uses_the_existing_deterministic_contract():
    selection = resolve_default_formal_document_alignment_provider_selection()

    assert selection == FormalDocumentAlignmentProviderSelection(
        provider_name=alignment_providers.MOCK_PROVIDER_NAME,
        model_identity=f"{alignment_providers.MOCK_PROVIDER_NAME}:{alignment_providers.MOCK_PROVIDER_VERSION}",
        prompt_version=alignment_prompting.PROMPT_VERSION,
        parser_version=alignment_output_parser.PARSER_VERSION,
        output_schema_version=alignment_output_parser.OUTPUT_SCHEMA_VERSION,
    )
    assert FORMAL_DEFAULT_PROVIDER_NAME == "mock-rule-v1"
    assert FORMAL_DEFAULT_MODEL_IDENTITY == "mock-rule-v1:v1"
    with pytest.raises(dataclasses.FrozenInstanceError):
        selection.provider_name = "changed"


def test_default_provider_config_is_local_enabled_and_credential_free():
    config = llm_provider_config.get_llm_provider_config(FORMAL_DEFAULT_PROVIDER_NAME)

    assert config["provider_type"] == "mock"
    assert config["model_identity"] == FORMAL_DEFAULT_MODEL_IDENTITY
    assert config["enabled"] is True
    assert config["transport_mode"] == "local"
    assert config["requires_credentials"] is False
    assert config["api_key_env_name"] == ""
    assert config["base_url"] == ""


def test_default_selection_does_not_read_environment_credentials(monkeypatch):
    class NoEnvironmentReads(dict):
        def get(self, key, default=None):
            raise AssertionError(f"environment read is forbidden: {key}")

    monkeypatch.setattr(llm_provider_config.os, "environ", NoEnvironmentReads())

    selection = resolve_default_formal_document_alignment_provider_selection()

    assert selection.provider_name == FORMAL_DEFAULT_PROVIDER_NAME


@pytest.mark.parametrize(
    "provider_name",
    [
        "unknown-provider",
        alignment_providers.DISABLED_EXTERNAL_PROVIDER_NAME,
        alignment_providers.REPLAY_EXTERNAL_PROVIDER_NAME,
        "custom-provider",
    ],
)
def test_non_default_or_external_provider_selection_fails_closed(provider_name):
    with pytest.raises(FormalDocumentAlignmentProviderSelectionError):
        resolve_formal_document_alignment_provider_selection(provider_name)


def test_selection_repr_has_no_secret_or_transport_configuration():
    rendered = repr(resolve_default_formal_document_alignment_provider_selection())

    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5F1" not in rendered
    assert "api_key" not in rendered
    assert "base_url" not in rendered
    assert "credential" not in rendered
