"""Legacy admin AI healthcheck route registration.

This module moves only the legacy POST healthcheck HTTP adapter. Live provider
transport remains disabled by the local readiness service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from flask import request

from routes.shared import RouteCoreDependencies
from services.legacy_provider_local_readiness import (
    LegacyProviderLocalReadinessProvider,
    LegacyProviderLocalReadinessRequest,
)


ROUTE_MARKER = "legacy_provider_admin_healthcheck_routes"
TARGET_ROUTES = {
    "/api/admin/ai/healthcheck": {
        "endpoint": "admin_ai_healthcheck",
        "method": "POST",
    },
}


@dataclass(frozen=True)
class LegacyProviderAdminHealthcheckModels:
    """Domain model dependencies for the legacy healthcheck route."""

    AIProviderConfig: Any


@dataclass(frozen=True)
class LegacyProviderAdminHealthcheckSerializers:
    """Legacy response helpers passed explicitly from the Flask app."""

    api_success: Callable[..., Any]


def register_legacy_provider_admin_healthcheck_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: LegacyProviderAdminHealthcheckModels,
    serializers: LegacyProviderAdminHealthcheckSerializers,
    registry_seed_service: Callable[..., Any],
    seed_models: Any,
    provider_selection_factory: Callable[[], Any],
    default_prompts: Iterable[dict[str, Any]],
    model_version_factory: Callable[[], str],
    local_readiness_service: Callable[..., Any],
    credential_presence_resolver: Callable[[Any], bool],
) -> None:
    """Register the legacy admin AI healthcheck route."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    def seed_registry(owner_user_id: int) -> None:
        registry_seed_service(
            db=core.db,
            models=seed_models,
            selection=provider_selection_factory(),
            default_prompts=default_prompts,
            current_time_text=core.current_time_text,
            model_version=model_version_factory(),
            owner_user_id=owner_user_id,
        )

    def admin_ai_healthcheck():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        seed_registry(user.id)
        live_probe = bool((request.get_json() or {}).get("live_probe", False))
        results = []
        for config in models.AIProviderConfig.query.filter_by(is_enabled=True).all():
            readiness = local_readiness_service(
                request=LegacyProviderLocalReadinessRequest(live_probe_requested=live_probe),
                provider=LegacyProviderLocalReadinessProvider(
                    provider_name=config.provider_name,
                    provider_mode=config.provider_mode,
                    model_name=config.default_model or "",
                    enabled=bool(config.is_enabled),
                    credential_present=bool(credential_presence_resolver(config)),
                    adapter_available=True,
                    external_execution_enabled=False,
                ),
            )
            result = readiness.to_payload()
            config.health_status = readiness.health_updates["health_status"]
            config.last_healthcheck_at = core.current_time_text()
            config.updated_at = core.current_time_text()
            results.append(result)
        core.db.session.commit()
        return serializers.api_success({"items": results})

    app.add_url_rule(
        "/api/admin/ai/healthcheck",
        endpoint="admin_ai_healthcheck",
        view_func=admin_ai_healthcheck,
        methods=["POST"],
    )
    registered.add(ROUTE_MARKER)


def _assert_no_duplicate_target_routes(app) -> None:
    for path, route in TARGET_ROUTES.items():
        method = route["method"]
        endpoint = route["endpoint"]
        for rule in app.url_map.iter_rules():
            if rule.rule == path and method in rule.methods:
                raise RuntimeError(
                    f"Cannot register {endpoint}: {method} {path} is already registered as {rule.endpoint}."
                )
