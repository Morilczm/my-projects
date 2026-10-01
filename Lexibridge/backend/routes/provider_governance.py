"""Read-only provider governance and preflight route registration.

This staged extraction keeps provider registry, policy summary, usage history,
and preflight history GET handlers thin. Provider policy mutation, preflight
execution, verification execution, usage recording, and transports remain in
``backend/app.py`` or the service layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import request

from routes.shared import RouteCoreDependencies
from services import alignment_providers as alignment_provider_service
from services import provider_governance as provider_governance_service
from services import provider_preflight as provider_preflight_service


ROUTE_MARKER = "provider_governance_routes"
TARGET_ROUTES = {
    "/api/alignment/providers": {
        "endpoint": "list_alignment_providers_api",
        "method": "GET",
    },
    "/api/alignment/providers/<path:provider_name>/policy": {
        "endpoint": "get_alignment_provider_policy_api",
        "method": "GET",
    },
    "/api/alignment/providers/<path:provider_name>/usage": {
        "endpoint": "list_alignment_provider_usage_api",
        "method": "GET",
    },
    "/api/alignment/providers/preflight/<preflight_uid>": {
        "endpoint": "get_alignment_provider_preflight_api",
        "method": "GET",
    },
    "/api/alignment/providers/<path:provider_name>/preflight": {
        "endpoint": "list_alignment_provider_preflights_api",
        "method": "GET",
    },
}


@dataclass(frozen=True)
class ProviderGovernanceModels:
    """Domain model dependencies for provider governance read routes."""

    AlignmentProviderPolicy: Any
    AlignmentProviderUsageRecord: Any
    AlignmentProviderPreflightRun: Any


def register_provider_governance_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: ProviderGovernanceModels,
) -> None:
    """Register read-only provider governance and preflight routes."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    db = core.db

    def provider_type_for_name(provider_name):
        return provider_governance_service.provider_type_for(provider_name)

    def get_serialized_provider_policy(provider_name):
        policy = provider_governance_service.get_effective_provider_policy(
            db.session,
            models.AlignmentProviderPolicy,
            provider_name,
        )
        if policy is None:
            data = provider_governance_service.default_policy_data(provider_name, provider_type_for_name(provider_name))
            data["policy_missing"] = True
            return data
        return provider_governance_service.serialize_provider_policy(policy)

    def list_alignment_providers_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        providers = []
        for item in alignment_provider_service.list_alignment_providers():
            policy = get_serialized_provider_policy(item.get("provider_name", ""))
            providers.append({**item, "policy": policy})
        return core.api_success_with_audit_context(
            {"providers": providers, "total": len(providers)},
            audit_context=audit_context,
        )

    def get_alignment_provider_policy_api(provider_name):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        return core.api_success_with_audit_context(
            {"policy": get_serialized_provider_policy(provider_name)},
            audit_context=audit_context,
        )

    def list_alignment_provider_usage_api(provider_name):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        items, total, page, per_page = provider_governance_service.list_provider_usage_records(
            db.session,
            models.AlignmentProviderUsageRecord,
            provider_name,
            filters={
                "course": request.args.get("course", ""),
                "date_from": request.args.get("date_from", ""),
                "date_to": request.args.get("date_to", ""),
                "page": request.args.get("page", 1),
                "per_page": request.args.get("per_page", 20),
            },
        )
        return core.api_success_with_audit_context(
            {
                "items": [provider_governance_service.serialize_provider_usage_record(item) for item in items],
                "total": total,
                "page": page,
                "per_page": per_page,
            },
            audit_context=audit_context,
        )

    def get_alignment_provider_preflight_api(preflight_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        run = provider_preflight_service.get_preflight_run(
            db.session,
            models.AlignmentProviderPreflightRun,
            preflight_uid,
        )
        if run is None:
            return core.api_error_with_audit_context(
                "RESOURCE_NOT_FOUND",
                "Provider preflight run not found.",
                404,
                audit_context,
                {"audit_error_code": "provider_preflight_not_found"},
            )
        return core.api_success_with_audit_context(
            {"preflight": provider_preflight_service.serialize_preflight_run(run)},
            audit_context=audit_context,
        )

    def list_alignment_provider_preflights_api(provider_name):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        items, total, page, per_page = provider_preflight_service.list_preflight_runs(
            db.session,
            models.AlignmentProviderPreflightRun,
            provider_name,
            filters={
                "course": request.args.get("course", ""),
                "page": request.args.get("page", 1),
                "per_page": request.args.get("per_page", 20),
            },
        )
        return core.api_success_with_audit_context(
            {
                "items": [provider_preflight_service.serialize_preflight_run(item) for item in items],
                "total": total,
                "page": page,
                "per_page": per_page,
            },
            audit_context=audit_context,
        )

    app.add_url_rule(
        "/api/alignment/providers",
        view_func=list_alignment_providers_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/alignment/providers/<path:provider_name>/policy",
        view_func=get_alignment_provider_policy_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/alignment/providers/<path:provider_name>/usage",
        view_func=list_alignment_provider_usage_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/alignment/providers/preflight/<preflight_uid>",
        view_func=get_alignment_provider_preflight_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/alignment/providers/<path:provider_name>/preflight",
        view_func=list_alignment_provider_preflights_api,
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
