"""Configuration guards for external alignment LLM providers.

External providers are disabled by default. This module exposes only sanitized
configuration summaries and never returns API key values.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


DISABLED_EXTERNAL_PROVIDER_NAME = "deepseek-alignment-v1-disabled"
DEEPSEEK_EXTERNAL_PROVIDER_NAME = "deepseek-alignment-v1"
REPLAY_EXTERNAL_PROVIDER_NAME = "external-llm-replay-v1"
EXTERNAL_LLM_ENABLED_ENV = "LEXIBRIDGE_EXTERNAL_LLM_ENABLED"

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 0
DEFAULT_MAX_PROMPT_CHARS = 8000
DEFAULT_MAX_OUTPUT_CHARS = 4000
DEFAULT_MAX_OUTPUT_TOKENS = 1000
MIN_ALIGNMENT_SCHEMA_OUTPUT_TOKENS = 512
DEEPSEEK_MODEL_POLICY_VERSION = "deepseek-formal-model-compatibility@1.0.0"
DEEPSEEK_PRICING_POLICY_VERSION = "deepseek-chat-pricing@2025-02-08"
DEEPSEEK_PRICING_EFFECTIVE_DATE = "2025-02-08"
DEEPSEEK_PRICING_CURRENCY = "USD"
DEEPSEEK_ALLOWED_RESOLVED_MODELS = {
    "deepseek-chat": frozenset({"deepseek-chat", "deepseek-v4-flash"}),
}
LLM_PROVIDER_ERROR_CODES = {
    "provider_disabled",
    "provider_not_configured",
    "credential_missing",
    "missing_api_key",
    "authentication_failed",
    "rate_limited",
    "provider_server_error",
    "connection_timeout",
    "read_timeout",
    "network_error",
    "invalid_request",
    "invalid_json",
    "malformed_provider_response",
    "missing_response_content",
    "provider_timeout",
    "provider_rate_limited",
    "provider_bad_response",
    "provider_non_json_output",
    "provider_schema_invalid",
    "provider_confidence_out_of_range",
    "provider_network_error",
    "provider_cost_limit_exceeded",
    "provider_output_too_long",
    "provider_pricing_unavailable",
    "response_model_not_allowed",
    "response_truncated",
}
PERMANENTLY_DISABLED_PROVIDER_NAMES = frozenset({DISABLED_EXTERNAL_PROVIDER_NAME})


class LLMProviderConfigError(ValueError):
    """Raised when external provider configuration fails a safety gate."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


DEFAULT_PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "mock-rule-v1": {
        "provider_name": "mock-rule-v1",
        "provider_type": "mock",
        "model_name": "mock-rule-v1",
        "model_identity": "mock-rule-v1:v1",
        "base_url": "",
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_retries": 0,
        "max_prompt_chars": DEFAULT_MAX_PROMPT_CHARS,
        "max_output_chars": DEFAULT_MAX_OUTPUT_CHARS,
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "cost_per_1k_input_tokens": 0.0,
        "cost_per_1k_output_tokens": 0.0,
        "max_estimated_cost": 0.0,
        "enabled": True,
        "replay_mode": True,
        "transport_mode": "local",
        "requires_credentials": False,
        "api_key_env_name": "",
    },
    DISABLED_EXTERNAL_PROVIDER_NAME: {
        "provider_name": DISABLED_EXTERNAL_PROVIDER_NAME,
        "provider_type": "external_llm",
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-chat",
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_retries": DEFAULT_MAX_RETRIES,
        "max_prompt_chars": DEFAULT_MAX_PROMPT_CHARS,
        "max_output_chars": DEFAULT_MAX_OUTPUT_CHARS,
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "cost_per_1k_input_tokens": None,
        "cost_per_1k_output_tokens": None,
        "max_estimated_cost": None,
        "enabled": False,
        "replay_mode": False,
        "api_key_env_name": "DEEPSEEK_API_KEY",
    },
    DEEPSEEK_EXTERNAL_PROVIDER_NAME: {
        "provider_name": DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        "provider_type": "external_llm",
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-chat",
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_retries": DEFAULT_MAX_RETRIES,
        "max_prompt_chars": DEFAULT_MAX_PROMPT_CHARS,
        "max_output_chars": DEFAULT_MAX_OUTPUT_CHARS,
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "supports_json_object_response_format": True,
        "model_policy_version": DEEPSEEK_MODEL_POLICY_VERSION,
        "pricing_model_identity": "deepseek-chat",
        "pricing_policy_version": DEEPSEEK_PRICING_POLICY_VERSION,
        "pricing_effective_date": DEEPSEEK_PRICING_EFFECTIVE_DATE,
        "pricing_currency": DEEPSEEK_PRICING_CURRENCY,
        "cost_per_1k_input_cache_hit_tokens": 0.00007,
        "cost_per_1k_input_cache_miss_tokens": 0.00027,
        "cost_per_1k_input_tokens": 0.00027,
        "cost_per_1k_output_tokens": 0.00110,
        "max_estimated_cost": None,
        "enabled": True,
        "replay_mode": False,
        "transport_mode": "deepseek_http",
        "requires_credentials": True,
        "api_key_env_name": "DEEPSEEK_API_KEY",
    },
    REPLAY_EXTERNAL_PROVIDER_NAME: {
        "provider_name": REPLAY_EXTERNAL_PROVIDER_NAME,
        "provider_type": "replay_llm",
        "base_url": "",
        "model_name": "alignment-replay-fixture",
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_retries": DEFAULT_MAX_RETRIES,
        "max_prompt_chars": DEFAULT_MAX_PROMPT_CHARS,
        "max_output_chars": DEFAULT_MAX_OUTPUT_CHARS,
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "cost_per_1k_input_tokens": 0.001,
        "cost_per_1k_output_tokens": 0.001,
        "max_estimated_cost": None,
        "enabled": False,
        "replay_mode": True,
        "api_key_env_name": "",
    },
}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_float(value: Any, default: float | None = None) -> float | None:
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_external_llm_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return _truthy(source.get(EXTERNAL_LLM_ENABLED_ENV, ""))


def external_llm_credential_present(config: dict[str, Any], env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    api_key_env_name = str(config.get("api_key_env_name") or "").strip()
    return bool(api_key_env_name and str(source.get(api_key_env_name) or "").strip())


def normalize_provider_timeout(value: Any) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    return max(1, min(timeout, 120))


def normalize_provider_retry_policy(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        raw_retries = value.get("max_retries")
    else:
        raw_retries = value
    try:
        max_retries = int(raw_retries)
    except (TypeError, ValueError):
        max_retries = DEFAULT_MAX_RETRIES
    return {"max_retries": max(0, min(max_retries, 3))}


def _sanitize_base_url(base_url: str) -> str:
    if not base_url:
        return ""
    try:
        parts = urlsplit(base_url)
    except ValueError:
        return "[invalid-url]"
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def sanitize_provider_config(config: dict[str, Any] | None) -> dict[str, Any]:
    safe = dict(config or {})
    safe.pop("api_key", None)
    safe["base_url"] = _sanitize_base_url(str(safe.get("base_url") or ""))
    safe["timeout_seconds"] = normalize_provider_timeout(safe.get("timeout_seconds"))
    safe["max_retries"] = normalize_provider_retry_policy(safe.get("max_retries")).get("max_retries", 0)
    safe["enabled"] = bool(safe.get("enabled"))
    safe["replay_mode"] = bool(safe.get("replay_mode"))
    return safe


def get_llm_provider_config(
    provider_name: str,
    overrides: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    provider = str(provider_name or "").strip()
    if provider not in DEFAULT_PROVIDER_CONFIGS:
        raise LLMProviderConfigError("provider_not_configured", f"LLM provider is not configured: {provider}")
    config = copy.deepcopy(DEFAULT_PROVIDER_CONFIGS[provider])
    if overrides:
        allowed_overrides = {
            "timeout_seconds",
            "max_retries",
            "max_prompt_chars",
            "max_output_chars",
            "max_output_tokens",
            "max_estimated_cost",
            "enabled",
            "replay_mode",
        }
        for key in allowed_overrides:
            if key in overrides:
                config[key] = overrides[key]
    if provider in PERMANENTLY_DISABLED_PROVIDER_NAMES:
        config["enabled"] = False
    config["timeout_seconds"] = normalize_provider_timeout(config.get("timeout_seconds"))
    config["max_retries"] = normalize_provider_retry_policy(config.get("max_retries")).get("max_retries", 0)
    config["max_prompt_chars"] = max(500, int(config.get("max_prompt_chars") or DEFAULT_MAX_PROMPT_CHARS))
    config["max_output_chars"] = max(500, int(config.get("max_output_chars") or DEFAULT_MAX_OUTPUT_CHARS))
    config["max_output_tokens"] = max(
        MIN_ALIGNMENT_SCHEMA_OUTPUT_TOKENS,
        min(int(config.get("max_output_tokens") or DEFAULT_MAX_OUTPUT_TOKENS), 4096),
    )
    config["configured"] = True
    if config.get("provider_type") == "external_llm":
        config["enabled"] = bool(config.get("enabled"))
        config["feature_enabled"] = is_external_llm_enabled(env)
        config["credential_present"] = external_llm_credential_present(config, env)
        config["executable"] = bool(
            config.get("enabled")
            and config.get("feature_enabled")
            and config.get("credential_present")
            and not config.get("replay_mode")
        )
    else:
        config["enabled"] = bool(config.get("enabled"))
        config["feature_enabled"] = False
        config["credential_present"] = False
        config["executable"] = bool(config.get("enabled"))
    config["replay_mode"] = bool(config.get("replay_mode"))
    return config


def require_external_llm_enabled(provider_name: str, config: dict[str, Any] | None = None) -> bool:
    cfg = config or get_llm_provider_config(provider_name)
    if cfg.get("replay_mode"):
        return True
    if provider_name in PERMANENTLY_DISABLED_PROVIDER_NAMES or not cfg.get("enabled"):
        raise LLMProviderConfigError("provider_disabled", f"External LLM provider is disabled: {provider_name}")
    if cfg.get("provider_type") == "external_llm":
        feature_enabled = bool(cfg.get("feature_enabled")) if "feature_enabled" in cfg else is_external_llm_enabled()
        if not feature_enabled:
            raise LLMProviderConfigError("provider_disabled", f"External LLM provider is disabled: {provider_name}")
    api_key_env_name = str(cfg.get("api_key_env_name") or "").strip()
    if not api_key_env_name:
        raise LLMProviderConfigError("provider_not_configured", "External LLM provider API key environment name is not configured.")
    if not external_llm_credential_present(cfg):
        raise LLMProviderConfigError("credential_missing", f"Missing API key environment variable: {api_key_env_name}")
    return True


def estimate_alignment_call_cost(
    input_summary: dict[str, Any] | None,
    provider_name: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or get_llm_provider_config(provider_name)
    summary = input_summary or {}
    prompt_chars = int(summary.get("prompt_chars") or summary.get("input_chars") or 0)
    output_chars = int(summary.get("expected_output_chars") or cfg.get("max_output_chars") or DEFAULT_MAX_OUTPUT_CHARS)
    input_tokens = max(1, int(prompt_chars / 4)) if prompt_chars else 0
    output_tokens = max(1, int(output_chars / 4)) if output_chars else 0
    input_cost = _coerce_float(cfg.get("cost_per_1k_input_cache_miss_tokens"))
    if input_cost is None:
        input_cost = _coerce_float(cfg.get("cost_per_1k_input_tokens"))
    output_cost = _coerce_float(cfg.get("cost_per_1k_output_tokens"))
    pricing_available = input_cost is not None and output_cost is not None
    estimated_cost = (
        round(
            (input_tokens / 1000.0 * input_cost)
            + (output_tokens / 1000.0 * output_cost),
            8,
        )
        if pricing_available
        else None
    )
    max_cost = _coerce_float(cfg.get("max_estimated_cost"))
    return {
        "provider_name": provider_name,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost": estimated_cost,
        "max_estimated_cost": max_cost,
        "cost_is_estimate": True,
        "pricing_available": pricing_available,
        "pricing_model_identity": str(cfg.get("pricing_model_identity") or cfg.get("model_name") or ""),
        "pricing_policy_version": str(cfg.get("pricing_policy_version") or ""),
        "pricing_effective_date": str(cfg.get("pricing_effective_date") or ""),
        "currency": str(cfg.get("pricing_currency") or ""),
        "input_cache_hit_per_1k_tokens": _coerce_float(
            cfg.get("cost_per_1k_input_cache_hit_tokens")
        ),
        "input_cache_miss_per_1k_tokens": input_cost,
        "output_per_1k_tokens": output_cost,
        "exceeds_limit": (
            max_cost is not None and estimated_cost > max_cost
            if estimated_cost is not None
            else None
        ),
    }


def validate_response_model_identity(
    requested_model: str,
    resolved_model: str,
) -> dict[str, Any]:
    requested = str(requested_model or "").strip()
    resolved = str(resolved_model or "").strip()
    allowed = DEEPSEEK_ALLOWED_RESOLVED_MODELS.get(requested, frozenset())
    compatible = bool(requested and resolved and resolved in allowed)
    return {
        "requested_model": requested,
        "resolved_model": resolved,
        "compatible": compatible,
        "model_policy_version": DEEPSEEK_MODEL_POLICY_VERSION,
        "pricing_model_identity": "deepseek-chat" if requested == "deepseek-chat" else "",
    }
