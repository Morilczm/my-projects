"""Pure provider classification for legacy `/api/alignment/run` containment.

This module is intentionally independent from Flask, database state, provider
adapters, secrets, and environment configuration. Callers pass already known
provider identifiers and receive a deterministic allow/block decision.
"""

from __future__ import annotations

from dataclasses import dataclass


LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED = "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"

SAFE_DETERMINISTIC_PROVIDER_CLASSES = frozenset({"none", "mock", "local_heuristic"})
_SAFE_ALIASES = {
    "": "none",
    "none": "none",
    "disabled": "none",
    "mock": "mock",
    "local": "local_heuristic",
    "heuristic": "local_heuristic",
    "local_heuristic": "local_heuristic",
}
_NETWORK_CAPABLE_PROVIDERS = frozenset({
    "deepseek",
    "openai",
    "custom_openai_compatible",
    "external",
    "live",
})
_NETWORK_CAPABLE_MODES = frozenset({"live", "external", "external_llm"})


@dataclass(frozen=True)
class LegacyAlignmentProviderClassification:
    requested_provider: str
    default_provider: str
    effective_provider: str
    requested_mode: str
    default_mode: str
    provider_class: str
    deterministic_allowed: bool
    external_execution_blocked: bool
    reason_code: str
    blocked_error_code: str = ""


def classify_legacy_alignment_provider(
    provider_value,
    *,
    provider_mode_value=None,
    default_provider_value=None,
    default_provider_mode_value=None,
    custom_endpoint_present=False,
) -> LegacyAlignmentProviderClassification:
    requested_provider = _normalize(provider_value)
    default_provider = _normalize(default_provider_value)
    requested_mode = _normalize(provider_mode_value)
    default_mode = _normalize(default_provider_mode_value)

    has_explicit_provider = provider_value is not None and str(provider_value).strip() != ""
    effective_raw = requested_provider if has_explicit_provider else default_provider
    effective_mode = requested_mode if requested_mode else ("" if has_explicit_provider else default_mode)
    effective_provider = _normalize_alias(effective_raw)

    if custom_endpoint_present:
        return _blocked(
            requested_provider,
            default_provider,
            effective_provider,
            requested_mode,
            default_mode,
            "custom",
            "LEGACY_ALIGNMENT_CUSTOM_ENDPOINT_BLOCKED",
        )

    if _looks_like_url(effective_raw):
        return _blocked(
            requested_provider,
            default_provider,
            effective_provider,
            requested_mode,
            default_mode,
            "custom",
            "LEGACY_ALIGNMENT_CUSTOM_ENDPOINT_BLOCKED",
        )

    if effective_mode in _NETWORK_CAPABLE_MODES or effective_provider in _NETWORK_CAPABLE_PROVIDERS:
        return _blocked(
            requested_provider,
            default_provider,
            effective_provider,
            requested_mode,
            default_mode,
            "external",
            "LEGACY_ALIGNMENT_EXTERNAL_PROVIDER_DISABLED",
        )

    if effective_provider in SAFE_DETERMINISTIC_PROVIDER_CLASSES:
        allowed_mode = effective_mode in {"", "none", effective_provider}
        if effective_provider == "mock":
            allowed_mode = effective_mode in {"", "none", "mock"}
        if effective_provider == "local_heuristic":
            allowed_mode = effective_mode in {"", "none", "local_heuristic"}
        if allowed_mode:
            return LegacyAlignmentProviderClassification(
                requested_provider=requested_provider,
                default_provider=default_provider,
                effective_provider=effective_provider,
                requested_mode=requested_mode,
                default_mode=default_mode,
                provider_class=effective_provider,
                deterministic_allowed=True,
                external_execution_blocked=False,
                reason_code="LEGACY_ALIGNMENT_PROVIDER_ALLOWED",
            )

    return _blocked(
        requested_provider,
        default_provider,
        effective_provider,
        requested_mode,
        default_mode,
        "unknown",
        "LEGACY_ALIGNMENT_UNKNOWN_PROVIDER_BLOCKED",
    )


def _blocked(
    requested_provider: str,
    default_provider: str,
    effective_provider: str,
    requested_mode: str,
    default_mode: str,
    provider_class: str,
    reason_code: str,
) -> LegacyAlignmentProviderClassification:
    return LegacyAlignmentProviderClassification(
        requested_provider=requested_provider,
        default_provider=default_provider,
        effective_provider=effective_provider,
        requested_mode=requested_mode,
        default_mode=default_mode,
        provider_class=provider_class,
        deterministic_allowed=False,
        external_execution_blocked=True,
        reason_code=reason_code,
        blocked_error_code=LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED,
    )


def _normalize(value) -> str:
    return str(value or "").strip().lower()


def _normalize_alias(value: str) -> str:
    return _SAFE_ALIASES.get(_normalize(value), _normalize(value))


def _looks_like_url(value: str) -> bool:
    normalized = _normalize(value)
    return normalized.startswith("http://") or normalized.startswith("https://")
