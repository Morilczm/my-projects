"""Server-owned provider identity for formal document alignment workflows."""

from __future__ import annotations

from dataclasses import dataclass

from services import alignment_output_parser, alignment_prompting, alignment_providers, llm_provider_config
from services.formal_real_provider_evaluation_policy import (
    is_trusted_formal_real_provider_evaluation_context,
)


FORMAL_DEFAULT_PROVIDER_NAME = alignment_providers.MOCK_PROVIDER_NAME
FORMAL_DEFAULT_MODEL_IDENTITY = (
    f"{alignment_providers.MOCK_PROVIDER_NAME}:{alignment_providers.MOCK_PROVIDER_VERSION}"
)


class FormalDocumentAlignmentProviderSelectionError(ValueError):
    """Raised when no safe server-owned formal provider identity is available."""


def _required_text(value, field_name, max_length=160):
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


@dataclass(frozen=True)
class FormalDocumentAlignmentProviderSelection:
    provider_name: str
    model_identity: str
    prompt_version: str
    parser_version: str
    output_schema_version: str

    def __post_init__(self):
        for name in (
            "provider_name",
            "model_identity",
            "prompt_version",
            "parser_version",
            "output_schema_version",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))


def resolve_formal_document_alignment_provider_selection(
    provider_name: str,
    *,
    evaluation_context=None,
) -> FormalDocumentAlignmentProviderSelection:
    provider_name = _required_text(provider_name, "provider_name", 120)
    evaluation_provider_allowed = is_trusted_formal_real_provider_evaluation_context(
        evaluation_context,
        provider_name=provider_name,
    )
    if provider_name != FORMAL_DEFAULT_PROVIDER_NAME and not evaluation_provider_allowed:
        raise FormalDocumentAlignmentProviderSelectionError(
            "Formal document alignment provider is not allowed."
        )
    try:
        provider = alignment_providers.get_alignment_provider(provider_name)
        config = llm_provider_config.get_llm_provider_config(provider_name)
    except Exception as exc:
        raise FormalDocumentAlignmentProviderSelectionError(
            "Formal document alignment provider is not configured."
        ) from exc
    if evaluation_provider_allowed:
        model_identity = str(config.get("model_name") or "").strip()
        if (
            provider.provider_name != provider_name
            or provider.provider_type != "external_llm"
            or not bool(getattr(provider, "supports_external_calls", False))
            or config.get("provider_type") != "external_llm"
            or not bool(config.get("enabled"))
            or not is_trusted_formal_real_provider_evaluation_context(
                evaluation_context,
                provider_name=provider_name,
                model_identity=model_identity,
            )
        ):
            raise FormalDocumentAlignmentProviderSelectionError(
                "Formal evaluation provider configuration is unsafe."
            )
        return FormalDocumentAlignmentProviderSelection(
            provider_name=provider.provider_name,
            model_identity=model_identity,
            prompt_version=alignment_prompting.STRUCTURED_PROMPT_VERSION,
            parser_version=alignment_output_parser.STRUCTURED_PARSER_VERSION,
            output_schema_version=alignment_output_parser.STRUCTURED_OUTPUT_SCHEMA_VERSION,
        )
    if (
        provider.provider_name != FORMAL_DEFAULT_PROVIDER_NAME
        or provider.provider_type != "mock"
        or bool(getattr(provider, "supports_external_calls", False))
        or config.get("provider_type") != "mock"
        or config.get("model_identity") != FORMAL_DEFAULT_MODEL_IDENTITY
        or not bool(config.get("enabled"))
        or config.get("transport_mode") != "local"
        or bool(config.get("requires_credentials"))
        or bool(config.get("api_key_env_name"))
        or bool(config.get("base_url"))
    ):
        raise FormalDocumentAlignmentProviderSelectionError(
            "Formal document alignment provider configuration is unsafe."
        )
    return FormalDocumentAlignmentProviderSelection(
        provider_name=provider.provider_name,
        model_identity=FORMAL_DEFAULT_MODEL_IDENTITY,
        prompt_version=alignment_prompting.PROMPT_VERSION,
        parser_version=alignment_output_parser.PARSER_VERSION,
        output_schema_version=alignment_output_parser.OUTPUT_SCHEMA_VERSION,
    )


def resolve_default_formal_document_alignment_provider_selection(
) -> FormalDocumentAlignmentProviderSelection:
    return resolve_formal_document_alignment_provider_selection(FORMAL_DEFAULT_PROVIDER_NAME)


def validate_formal_document_alignment_provider_selection(
    *,
    provider_name: str,
    model_identity: str,
    prompt_version: str,
    evaluation_context=None,
) -> FormalDocumentAlignmentProviderSelection:
    selection = resolve_formal_document_alignment_provider_selection(
        provider_name,
        evaluation_context=evaluation_context,
    )
    if (
        str(model_identity or "").strip() != selection.model_identity
        or str(prompt_version or "").strip() != selection.prompt_version
    ):
        raise FormalDocumentAlignmentProviderSelectionError(
            "Formal document alignment provider identity does not match server policy."
        )
    return selection
