"""Admin alignment run listing route registration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import jsonify

from routes.shared import RouteCoreDependencies


ROUTE_MARKER = "admin_alignment_run_routes"
TARGET_ROUTES = {
    "/api/admin/alignment-runs": {
        "endpoint": "admin_alignment_runs",
        "method": "GET",
    },
}


@dataclass(frozen=True)
class AdminAlignmentRunModels:
    """Domain model dependencies for admin alignment run listing."""

    AlignmentRun: Any


def register_admin_alignment_run_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: AdminAlignmentRunModels,
    serialize_alignment_run: Callable[[Any], dict[str, Any]],
) -> None:
    """Register the legacy admin alignment run listing route."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    def admin_alignment_runs():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        runs = models.AlignmentRun.query.order_by(models.AlignmentRun.id.desc()).limit(300).all()
        return jsonify(
            {
                "status": "success",
                "runs": [serialize_alignment_run(run) for run in runs],
            }
        )

    app.add_url_rule(
        "/api/admin/alignment-runs",
        endpoint="admin_alignment_runs",
        view_func=admin_alignment_runs,
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
