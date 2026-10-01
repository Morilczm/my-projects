"""Legacy provider local readiness evaluation.

This module contains only deterministic local health evaluation for the
legacy admin AI healthcheck endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass


LEGACY_LIVE_PROBE_DISABLED = "LEGACY_LIVE_PROBE_DISABLED"


@dataclass(frozen=True)
class LegacyProviderLocalReadinessRequest:
    live_probe_requested: bool = False


@dataclass(frozen=True)
class LegacyProviderLocalReadinessProvider:
    provider_name: str
    provider_mode: str
    model_name: str = ""
    enabled: bool = True
    credential_present: bool = False
    adapter_available: bool = True
    external_execution_enabled: bool = False


@dataclass(frozen=True)
class LegacyProviderLocalReadinessResult:
    provider_name: str
    provider_mode: str
    health_status: str
    latency_ms: int
    message: str
    error_code: str | None = None
    live_probe_requested: bool = False
    live_probe_executed: bool = False

    @property
    def health_updates(self) -> dict[str, str]:
        return {"health_status": self.health_status}

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider_name": self.provider_name,
            "provider_mode": self.provider_mode,
            "health_status": self.health_status,
            "latency_ms": self.latency_ms,
            "message": self.message,
        }
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload


def evaluate_legacy_provider_local_readiness(
    *,
    request: LegacyProviderLocalReadinessRequest,
    provider: LegacyProviderLocalReadinessProvider,
) -> LegacyProviderLocalReadinessResult:
    provider_name = str(provider.provider_name or "none")
    mode = str(provider.provider_mode or "none").strip().lower()

    if request.live_probe_requested:
        return LegacyProviderLocalReadinessResult(
            provider_name=provider_name,
            provider_mode=mode,
            health_status="unknown",
            latency_ms=0,
            message="Legacy live probe is disabled; provider transport was not attempted.",
            error_code=LEGACY_LIVE_PROBE_DISABLED,
            live_probe_requested=True,
            live_probe_executed=False,
        )

    if not provider.adapter_available:
        return LegacyProviderLocalReadinessResult(
            provider_name=provider_name,
            provider_mode=mode,
            health_status="unhealthy",
            latency_ms=0,
            message="Provider adapter is not available.",
            error_code="AI_PROVIDER_ADAPTER_UNAVAILABLE",
        )

    if mode == "none":
        return LegacyProviderLocalReadinessResult(
            provider_name=provider_name,
            provider_mode=mode,
            health_status="unhealthy",
            latency_ms=0,
            message="AI provider is not configured.",
        )

    if mode in {"mock", "local_heuristic"}:
        return LegacyProviderLocalReadinessResult(
            provider_name=provider_name,
            provider_mode=mode,
            health_status="healthy",
            latency_ms=0,
            message="Development-only provider is available.",
        )

    if not provider.credential_present:
        return LegacyProviderLocalReadinessResult(
            provider_name=provider_name,
            provider_mode=mode,
            health_status="unhealthy",
            latency_ms=0,
            message="Live provider API key is missing or placeholder.",
        )

    return LegacyProviderLocalReadinessResult(
        provider_name=provider_name,
        provider_mode=mode,
        health_status="unknown",
        latency_ms=0,
        message="Config is complete; live probe skipped.",
    )
