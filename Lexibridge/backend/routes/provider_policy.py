"""Provider policy mutation route registration.

This staged extraction keeps provider policy writes separate from provider
preflight execution, verification execution, usage recording, credential
management, and transports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from routes.shared import RouteCoreDependencies
from services import provider_governance as provider_governance_service


ROUTE_MARKER = "provider_policy_routes"
TARGET_ROUTES = {
    "/api/alignment/providers/<path:provider_name>/policy": {
        "endpoint": "update_alignment_provider_policy_api",
        "method": "POST",
    },
}


@dataclass(frozen=True)
class ProviderPolicyModels:
    """Domain model dependencies for provider policy mutation routes."""

    AlignmentProviderPolicy: Any


def register_provider_policy_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: ProviderPolicyModels,
    record_provider_governance_audit: Callable[..., Any],
) -> None:
    """Register provider policy mutation routes."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    db = core.db

    def update_alignment_provider_policy_api(provider_name):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        data = request.get_json(silent=True) or {}
        policy, created = provider_governance_service.create_or_update_provider_policy(
            db.session,
            models.AlignmentProviderPolicy,
            provider_name,
            data,
            actor=user,
            now_fn=core.current_time_text,
            commit=True,
        )
        event_type = "provider_policy_created" if created else "provider_policy_updated"
        record_provider_governance_audit(
            event_type,
            provider_name=provider_name,
            policy=policy,
            input_data=data,
            audit_context=audit_context,
        )
        return core.api_success_with_audit_context(
            {"policy": provider_governance_service.serialize_provider_policy(policy), "created": created},
            audit_context=audit_context,
        )

    app.add_url_rule(
        "/api/alignment/providers/<path:provider_name>/policy",
        view_func=update_alignment_provider_policy_api,
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
