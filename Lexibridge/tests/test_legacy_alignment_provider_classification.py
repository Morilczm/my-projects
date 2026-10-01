import inspect

import pytest

from services.legacy_alignment_provider_classification import (
    LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED,
    classify_legacy_alignment_provider,
)


@pytest.mark.parametrize(
    ("provider", "mode", "expected"),
    [
        ("none", "", "none"),
        ("mock", "", "mock"),
        ("local_heuristic", "", "local_heuristic"),
        (" local ", "", "local_heuristic"),
        ("HEURISTIC", "", "local_heuristic"),
    ],
)
def test_explicit_safe_allowlist(provider, mode, expected):
    result = classify_legacy_alignment_provider(provider, provider_mode_value=mode)

    assert result.deterministic_allowed is True
    assert result.external_execution_blocked is False
    assert result.effective_provider == expected
    assert result.reason_code == "LEGACY_ALIGNMENT_PROVIDER_ALLOWED"


@pytest.mark.parametrize(
    ("provider", "mode"),
    [
        ("deepseek", "live"),
        ("openai", "live"),
        ("custom_openai_compatible", "live"),
        ("external", ""),
        ("live", ""),
        ("https://example.invalid/v1", ""),
        ("mock-deepseek", ""),
        ("custom-provider", ""),
        ("", "live"),
    ],
)
def test_external_unknown_and_substring_values_fail_closed(provider, mode):
    result = classify_legacy_alignment_provider(provider, provider_mode_value=mode)

    assert result.deterministic_allowed is False
    assert result.external_execution_blocked is True
    assert result.blocked_error_code == LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED


def test_default_external_blocks_when_request_omits_provider():
    result = classify_legacy_alignment_provider(
        None,
        default_provider_value="deepseek",
        default_provider_mode_value="live",
    )

    assert result.effective_provider == "deepseek"
    assert result.external_execution_blocked is True
    assert result.reason_code == "LEGACY_ALIGNMENT_EXTERNAL_PROVIDER_DISABLED"


def test_explicit_local_override_can_replace_external_default():
    result = classify_legacy_alignment_provider(
        "mock",
        default_provider_value="deepseek",
        default_provider_mode_value="live",
    )

    assert result.effective_provider == "mock"
    assert result.deterministic_allowed is True


def test_custom_url_or_base_url_fails_closed():
    result = classify_legacy_alignment_provider("mock", custom_endpoint_present=True)

    assert result.deterministic_allowed is False
    assert result.external_execution_blocked is True
    assert result.reason_code == "LEGACY_ALIGNMENT_CUSTOM_ENDPOINT_BLOCKED"


def test_classification_has_no_environment_credential_or_network_dependency():
    import services.legacy_alignment_provider_classification as module

    source = inspect.getsource(module)
    assert "os.environ" not in source
    assert "urllib" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "api_key" not in source.lower()
    assert "credential" not in source.lower()
