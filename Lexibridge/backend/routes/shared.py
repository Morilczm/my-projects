"""Shared route infrastructure for staged route extraction.

This module intentionally contains only cross-domain route plumbing. It is not
a service locator, does not register routes, and does not import ``backend.app``
or business service modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RouteCoreDependencies:
    """Common immutable route infrastructure shared by extracted route modules."""

    db: Any
    audit_record_model: Any
    audit_record_service: Any
    current_time_text: Callable[[], str]
    require_current_user: Callable[..., Any]
    get_route_audit_context: Callable[..., dict[str, Any]]
    attach_request_id_to_response: Callable[..., Any]
    api_success_with_audit_context: Callable[..., Any]
    api_error_with_audit_context: Callable[..., Any]
