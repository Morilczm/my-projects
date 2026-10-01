"""Alignment verification route registration.

The execution state machine lives in
``services.alignment_verification_execution``. This module is only the thin
HTTP adapter for ``POST /api/alignment/verify``.
"""

from __future__ import annotations

from typing import Any

from flask import request

from routes.shared import RouteCoreDependencies
from services.alignment_verification_execution import (
    AlignmentVerificationActor,
    AlignmentVerificationExecutionContext,
    AlignmentVerificationExecutionDependencies,
    AlignmentVerificationExecutionRequest,
    execute_alignment_verification,
)


ROUTE_MARKER = "alignment_verification_routes"
TARGET_ROUTES = {
    "/api/alignment/verify": {
        "endpoint": "verify_alignment_api",
        "method": "POST",
    },
}


def register_alignment_verification_routes(
    app,
    *,
    core: RouteCoreDependencies,
    execution_dependencies: Any,
    execute_fn=execute_alignment_verification,
) -> None:
    """Register the alignment verification HTTP adapter route."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    def verify_alignment_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"student", "teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        data = request.get_json(silent=True) or {}
        provider_name = str(data.get("provider") or data.get("provider_name") or "mock-rule-v1").strip()
        card_uid = str(data.get("card_uid") or "").strip()
        attach_to_card = _truthy_request_value(data.get("attach_to_card", False))
        result = execute_fn(
            AlignmentVerificationExecutionRequest(
                payload=data,
                provider_name=provider_name,
                card_uid=card_uid,
                attach_to_card=attach_to_card,
            ),
            _actor_from_user(user),
            _context_from_audit_context(audit_context, core),
            _resolve_execution_dependencies(execution_dependencies),
        )
        if result.succeeded:
            return core.api_success_with_audit_context(result.payload, result.message, audit_context)
        return core.api_error_with_audit_context(
            result.error_code,
            result.message,
            result.status_code,
            audit_context,
            {"audit_error_code": result.audit_error_code},
        )

    app.add_url_rule(
        "/api/alignment/verify",
        endpoint="verify_alignment_api",
        view_func=verify_alignment_api,
        methods=["POST"],
    )
    registered.add(ROUTE_MARKER)


def _resolve_execution_dependencies(execution_dependencies: Any) -> AlignmentVerificationExecutionDependencies:
    if callable(execution_dependencies):
        return execution_dependencies()
    return execution_dependencies


def _truthy_request_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _context_from_audit_context(
    audit_context: dict[str, Any],
    core: RouteCoreDependencies,
) -> AlignmentVerificationExecutionContext:
    return AlignmentVerificationExecutionContext(
        request_id=audit_context.get("request_id", ""),
        actor_id=audit_context.get("actor_id"),
        actor_role=audit_context.get("actor_role", ""),
        actor_name=audit_context.get("actor_name", ""),
        source=audit_context.get("source", "api"),
        ip_hash=audit_context.get("ip_hash", ""),
        user_agent_summary=audit_context.get("user_agent_summary", ""),
        route="/api/alignment/verify",
        occurred_at=core.current_time_text(),
    )


def _actor_from_user(user: Any) -> AlignmentVerificationActor:
    return AlignmentVerificationActor(
        user_id=getattr(user, "id", None),
        email=str(getattr(user, "email", "") or ""),
        role=str(getattr(user, "role", "") or ""),
        display_name=str(
            getattr(user, "display_name", "")
            or getattr(user, "username", "")
            or getattr(user, "email", "")
            or ""
        ),
    )


def _assert_no_duplicate_target_routes(app) -> None:
    for path, route in TARGET_ROUTES.items():
        method = route["method"]
        endpoint = route["endpoint"]
        for rule in app.url_map.iter_rules():
            if rule.rule == path and method in rule.methods:
                raise RuntimeError(
                    f"Cannot register {endpoint}: {method} {path} is already registered as {rule.endpoint}."
                )
