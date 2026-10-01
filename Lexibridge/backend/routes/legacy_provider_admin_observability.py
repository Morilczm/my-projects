"""Legacy admin AI observability route registration.

This module moves only the legacy read views for AI call logs, usage summary,
and local provider health state. It intentionally does not move prompt
mutation, healthcheck execution, provider transport, replay, or credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from routes.shared import RouteCoreDependencies


ROUTE_MARKER = "legacy_provider_admin_observability_routes"
TARGET_ROUTES = {
    "/api/admin/ai/calls": {
        "endpoint": "admin_ai_calls",
        "method": "GET",
    },
    "/api/admin/ai/usage": {
        "endpoint": "admin_ai_usage",
        "method": "GET",
    },
    "/api/admin/ai/health": {
        "endpoint": "admin_ai_health",
        "method": "GET",
    },
}


@dataclass(frozen=True)
class LegacyProviderAdminObservabilityModels:
    """Domain model dependencies for legacy admin AI observability views."""

    AICallLog: Any
    AIProviderConfig: Any


@dataclass(frozen=True)
class LegacyProviderAdminObservabilitySerializers:
    """Legacy response helpers passed explicitly from the Flask app."""

    api_success: Callable[..., Any]
    serialize_ai_call_log: Callable[[Any], dict[str, Any]]
    serialize_ai_provider_config: Callable[[Any], dict[str, Any]]
    summarize_ai_calls: Callable[[list[Any]], dict[str, Any]]


def register_legacy_provider_admin_observability_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: LegacyProviderAdminObservabilityModels,
    serializers: LegacyProviderAdminObservabilitySerializers,
    registry_seed_service: Callable[..., Any],
) -> None:
    """Register legacy admin AI calls, usage, and local health GET routes."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    def admin_ai_calls():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        logs = models.AICallLog.query.order_by(models.AICallLog.id.desc()).limit(300).all()
        return serializers.api_success(
            {"items": [serializers.serialize_ai_call_log(log) for log in logs]}
        )

    def admin_ai_usage():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        logs = models.AICallLog.query.order_by(models.AICallLog.id.desc()).limit(1000).all()
        return serializers.api_success(
            {
                "summary": serializers.summarize_ai_calls(logs),
                "recent": [serializers.serialize_ai_call_log(log) for log in logs[:50]],
            }
        )

    def admin_ai_health():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        registry_seed_service(owner_user_id=user.id)
        providers = models.AIProviderConfig.query.order_by(models.AIProviderConfig.id.asc()).all()
        return serializers.api_success(
            {"items": [serializers.serialize_ai_provider_config(provider) for provider in providers]}
        )

    app.add_url_rule(
        "/api/admin/ai/calls",
        endpoint="admin_ai_calls",
        view_func=admin_ai_calls,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/ai/usage",
        endpoint="admin_ai_usage",
        view_func=admin_ai_usage,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/ai/health",
        endpoint="admin_ai_health",
        view_func=admin_ai_health,
        methods=["GET"],
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
