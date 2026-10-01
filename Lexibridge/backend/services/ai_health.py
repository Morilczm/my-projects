"""AI provider healthcheck helpers."""

from __future__ import annotations

import time

from .ai_provider import provider_from_selection
from .ai_registry import ProviderSelection, is_placeholder_secret


def healthcheck_provider(selection: ProviderSelection, live_probe=False):
    started = time.time()
    provider_name = selection.provider_name
    mode = selection.provider_mode
    if mode == "none":
        return {
            "provider_name": provider_name,
            "provider_mode": mode,
            "health_status": "unhealthy",
            "latency_ms": 0,
            "message": "AI provider is not configured.",
        }
    if mode in {"mock", "local_heuristic"}:
        return {
            "provider_name": provider_name,
            "provider_mode": mode,
            "health_status": "healthy",
            "latency_ms": 0,
            "message": "Development-only provider is available.",
        }
    if not selection.api_key or is_placeholder_secret(selection.api_key):
        return {
            "provider_name": provider_name,
            "provider_mode": mode,
            "health_status": "unhealthy",
            "latency_ms": 0,
            "message": "Live provider API key is missing or placeholder.",
        }
    if not live_probe:
        return {
            "provider_name": provider_name,
            "provider_mode": mode,
            "health_status": "unknown",
            "latency_ms": 0,
            "message": "Config is complete; live probe skipped.",
        }
    provider = provider_from_selection(selection)
    response = provider.call(
        "term_alignment",
        "Return a minimal JSON health response.",
        {
            "english_term": "Health Check",
            "translation_candidate_hint": "健康检查",
            "english_evidence": [],
            "chinese_evidence": [],
        },
    )
    latency_ms = int((time.time() - started) * 1000)
    if response.get("status") == "success":
        return {
            "provider_name": provider_name,
            "provider_mode": mode,
            "health_status": "healthy",
            "latency_ms": latency_ms,
            "message": "Live provider responded.",
        }
    return {
        "provider_name": provider_name,
        "provider_mode": mode,
        "health_status": "unhealthy",
        "latency_ms": latency_ms,
        "message": response.get("message", "Provider healthcheck failed."),
        "error_code": response.get("error_code", "AI_PROVIDER_FAILED"),
    }
