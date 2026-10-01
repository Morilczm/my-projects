"""Provider preflight execution route registration.

This staged extraction keeps provider preflight execution separate from
alignment verification execution, provider usage writes, credential management,
and transports. The route remains a local readiness check and does not call
real external providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from routes.shared import RouteCoreDependencies
from services import provider_preflight as provider_preflight_service


ROUTE_MARKER = "provider_preflight_routes"
TARGET_ROUTES = {
    "/api/alignment/providers/<path:provider_name>/preflight": {
        "endpoint": "run_alignment_provider_preflight_api",
        "method": "POST",
    },
}


@dataclass(frozen=True)
class ProviderPreflightModels:
    """Domain model dependencies for provider preflight execution routes."""

    AlignmentProviderPreflightRun: Any
    AlignmentProviderPolicy: Any


def register_provider_preflight_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: ProviderPreflightModels,
    record_provider_preflight_audit: Callable[..., Any],
) -> None:
    """Register provider preflight execution routes."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    db = core.db

    def run_alignment_provider_preflight_api(provider_name):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        data = request.get_json(silent=True) or {}
        course = str(data.get("course") or "").strip()
        include_replay_dry_run = data.get("include_replay_dry_run", True)
        if isinstance(include_replay_dry_run, str):
            include_replay_dry_run = include_replay_dry_run.strip().lower() in {"1", "true", "yes", "on"}
        else:
            include_replay_dry_run = bool(include_replay_dry_run)

        record_provider_preflight_audit(
            "provider_preflight_requested",
            provider_name=provider_name,
            course=course,
            audit_context=audit_context,
            commit=True,
        )
        run, report = provider_preflight_service.run_provider_preflight(
            db.session,
            models.AlignmentProviderPreflightRun,
            models.AlignmentProviderPolicy,
            provider_name,
            course=course,
            actor=user,
            include_replay_dry_run=include_replay_dry_run,
            replay_response_type=str(data.get("replay_response_type") or "valid"),
            now_fn=core.current_time_text,
            commit=True,
        )
        event_type = "provider_preflight_completed" if report.get("check_status") in {"passed", "warning"} else "provider_preflight_failed"
        record_provider_preflight_audit(
            event_type,
            provider_name=provider_name,
            preflight_run=run,
            course=course,
            error_code=";".join(report.get("blocking_reasons", [])) if event_type == "provider_preflight_failed" else "",
            error_message="Provider preflight did not meet readiness gates." if event_type == "provider_preflight_failed" else "",
            audit_context=audit_context,
            commit=True,
        )
        return core.api_success_with_audit_context(report, audit_context=audit_context)

    app.add_url_rule(
        "/api/alignment/providers/<path:provider_name>/preflight",
        view_func=run_alignment_provider_preflight_api,
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
