"""AI provider and model registry helpers.

These helpers are deliberately database-agnostic. The Flask app owns ORM
records, while this module centralizes validation and production-safety rules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


PROVIDER_MODES = {"none", "mock", "local_heuristic", "live"}
LIVE_PROVIDERS = {"deepseek", "openai", "custom_openai_compatible"}
KNOWN_PROVIDERS = {"none", "mock", "local_heuristic", "deepseek", "openai", "custom_openai_compatible"}
PLACEHOLDER_TOKENS = {
    "your-api-key",
    "your-api-key-here",
    "your-deepseek-api-key-here",
    "sk-xxx",
    "placeholder",
    "change-me",
    "replace-with-strong-secret",
}


@dataclass
class ProviderSelection:
    provider_name: str
    provider_mode: str
    model_name: str
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: int = 45
    max_retries: int = 2
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0


def parse_bool(value, default=False):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_placeholder_secret(value):
    text = str(value or "").strip().lower()
    if not text:
        return False
    return text in PLACEHOLDER_TOKENS or any(token in text for token in PLACEHOLDER_TOKENS)


def normalize_provider_name(value):
    provider = str(value or "none").strip().lower()
    if provider in {"local", "heuristic"}:
        return "local_heuristic"
    if provider in {"openai_compatible", "custom"}:
        return "custom_openai_compatible"
    return provider if provider in KNOWN_PROVIDERS else provider


def infer_provider_mode(provider_name, configured_mode="", api_key="", allow_mock=True, allow_local=True):
    configured = str(configured_mode or "").strip().lower()
    if configured in PROVIDER_MODES:
        return configured
    provider = normalize_provider_name(provider_name)
    if provider == "none":
        return "none"
    if provider == "mock":
        return "mock" if allow_mock else "none"
    if provider == "local_heuristic":
        return "local_heuristic" if allow_local else "none"
    if provider in LIVE_PROVIDERS and api_key and not is_placeholder_secret(api_key):
        return "live"
    if allow_local:
        return "local_heuristic"
    return "none"


def env_provider_selection(env=None):
    env = env or os.environ
    provider = normalize_provider_name(env.get("AI_PROVIDER", "none"))
    if provider == "deepseek":
        api_key = env.get("DEEPSEEK_API_KEY", "")
        base_url = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = env.get("DEEPSEEK_MODEL") or env.get("AI_MODEL") or "deepseek-chat"
    elif provider in {"openai", "custom_openai_compatible"}:
        api_key = env.get("OPENAI_API_KEY", "")
        base_url = env.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = env.get("OPENAI_MODEL") or env.get("AI_MODEL") or ""
    else:
        api_key = ""
        base_url = ""
        model = env.get("AI_MODEL", "") or provider

    allow_mock = parse_bool(env.get("ALLOW_MOCK_AI"), default=True)
    allow_local = parse_bool(env.get("ALLOW_LOCAL_HEURISTIC_AI"), default=True)
    mode = infer_provider_mode(
        provider,
        configured_mode=env.get("AI_PROVIDER_MODE", ""),
        api_key=api_key,
        allow_mock=allow_mock,
        allow_local=allow_local,
    )
    try:
        timeout = int(env.get("AI_REQUEST_TIMEOUT_SECONDS", env.get("DEEPSEEK_TIMEOUT_SECONDS", "45")))
    except ValueError:
        timeout = 45
    try:
        retries = int(env.get("AI_MAX_RETRIES", "2"))
    except ValueError:
        retries = 2
    return ProviderSelection(
        provider_name=provider,
        provider_mode=mode,
        model_name=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=max(3, min(timeout, 120)),
        max_retries=max(0, min(retries, 5)),
        cost_per_1k_input_tokens=float(env.get("AI_COST_PER_1K_INPUT_TOKENS", "0") or 0),
        cost_per_1k_output_tokens=float(env.get("AI_COST_PER_1K_OUTPUT_TOKENS", "0") or 0),
    )


def validate_ai_config(env_name, env=None):
    env = env or os.environ
    errors = []
    warnings = []
    provider = normalize_provider_name(env.get("AI_PROVIDER", "none"))
    mode = str(env.get("AI_PROVIDER_MODE", "") or infer_provider_mode(provider, api_key="")).strip().lower()
    allow_mock = parse_bool(env.get("ALLOW_MOCK_AI"), default=False)
    allow_local = parse_bool(env.get("ALLOW_LOCAL_HEURISTIC_AI"), default=False)
    prompt_full = parse_bool(env.get("AI_LOG_PROMPT_FULL"), default=False)
    response_full = parse_bool(env.get("AI_LOG_RESPONSE_FULL"), default=False)
    redact = parse_bool(env.get("AI_LOG_REDACT_SECRETS", env.get("LOG_REDACT_SECRETS", "true")), default=True)

    if provider not in KNOWN_PROVIDERS:
        errors.append(f"AI_PROVIDER is invalid: {provider}")
    if mode and mode not in PROVIDER_MODES:
        errors.append(f"AI_PROVIDER_MODE is invalid: {mode}")

    if provider == "deepseek":
        key = env.get("DEEPSEEK_API_KEY", "")
    elif provider in {"openai", "custom_openai_compatible"}:
        key = env.get("OPENAI_API_KEY", "")
    else:
        key = ""

    if key and is_placeholder_secret(key):
        errors.append("AI provider API key is a placeholder.")

    if env_name == "production":
        if mode != "live":
            errors.append("AI_PROVIDER_MODE must be live in production.")
        if provider not in LIVE_PROVIDERS:
            errors.append("AI_PROVIDER must be a live provider in production.")
        if allow_mock:
            errors.append("ALLOW_MOCK_AI must be false in production.")
        if allow_local:
            errors.append("ALLOW_LOCAL_HEURISTIC_AI must be false in production.")
        if not key or is_placeholder_secret(key):
            errors.append("Production AI provider requires a non-placeholder API key.")
        if prompt_full:
            errors.append("AI_LOG_PROMPT_FULL must be false in production.")
        if response_full:
            errors.append("AI_LOG_RESPONSE_FULL must be false in production.")
        if not redact:
            errors.append("AI_LOG_REDACT_SECRETS/LOG_REDACT_SECRETS must be true in production.")
        if not env.get("AI_DAILY_CALL_LIMIT_PER_USER"):
            errors.append("AI_DAILY_CALL_LIMIT_PER_USER must be configured in production.")
        if not env.get("AI_MONTHLY_CALL_LIMIT_PER_USER"):
            errors.append("AI_MONTHLY_CALL_LIMIT_PER_USER must be configured in production.")
        if not env.get("AI_DAILY_COST_LIMIT_PER_USER"):
            errors.append("AI_DAILY_COST_LIMIT_PER_USER must be configured in production.")
        if not parse_bool(env.get("AI_PROVIDER_HEALTHCHECK_ENABLED"), default=False):
            errors.append("AI_PROVIDER_HEALTHCHECK_ENABLED must be true in production.")
    else:
        if mode in {"mock", "local_heuristic"} or allow_mock or allow_local:
            warnings.append("Mock/local AI is allowed only for local demo and cannot auto-approve cards.")
        if provider in LIVE_PROVIDERS and (not key or is_placeholder_secret(key)):
            warnings.append("Live AI provider selected but no usable API key is configured.")

    return errors, warnings


def can_default_provider(provider_name, provider_mode, app_env="development"):
    provider = normalize_provider_name(provider_name)
    mode = str(provider_mode or "none").strip().lower()
    if app_env == "production" and mode != "live":
        return False, ["production default provider must be live"]
    if mode in {"mock", "local_heuristic"} and app_env == "production":
        return False, ["mock/local providers cannot be production defaults"]
    if provider == "none" and app_env == "production":
        return False, ["none provider cannot be production default"]
    return True, []
