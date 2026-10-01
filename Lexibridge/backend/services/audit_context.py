"""Lightweight request-level context helpers for audit records."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any


MAX_REQUEST_ID_LENGTH = 120
MAX_ACTOR_NAME_LENGTH = 160
MAX_USER_AGENT_LENGTH = 160


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def get_request_id(request_like: Any | None = None) -> str:
    headers = getattr(request_like, "headers", {}) or {}
    request_id = ""
    try:
        request_id = headers.get("X-Request-ID", "")
    except AttributeError:
        request_id = ""
    request_id = _truncate(request_id, MAX_REQUEST_ID_LENGTH)
    return request_id or str(uuid.uuid4())


def _actor_from_user(user: Any | None) -> dict[str, Any]:
    if user is None:
        return {"actor_id": None, "actor_role": "", "actor_name": ""}
    return {
        "actor_id": getattr(user, "id", None),
        "actor_role": str(getattr(user, "role", "") or ""),
        "actor_name": _truncate(
            getattr(user, "display_name", "")
            or getattr(user, "username", "")
            or getattr(user, "email", "")
            or "",
            MAX_ACTOR_NAME_LENGTH,
        ),
    }


def _remote_addr(request_like: Any | None) -> str:
    if request_like is None:
        return ""
    access_route = getattr(request_like, "access_route", None)
    if access_route:
        return str(access_route[0] or "")
    return str(getattr(request_like, "remote_addr", "") or "")


def _ip_hash(remote_addr: str) -> str:
    remote_addr = str(remote_addr or "").strip()
    if not remote_addr:
        return ""
    return hashlib.sha256(remote_addr.encode("utf-8")).hexdigest()[:16]


def _user_agent_summary(request_like: Any | None) -> str:
    headers = getattr(request_like, "headers", {}) or {}
    try:
        user_agent = headers.get("User-Agent", "")
    except AttributeError:
        user_agent = ""
    return _truncate(user_agent, MAX_USER_AGENT_LENGTH)


def build_audit_context_from_request(
    request_like: Any,
    current_user: Any | None = None,
    *,
    source: str = "api",
    request_id: str | None = None,
) -> dict[str, Any]:
    context = {
        "request_id": _truncate(request_id, MAX_REQUEST_ID_LENGTH) if request_id else get_request_id(request_like),
        "source": str(source or "api"),
        "ip_hash": _ip_hash(_remote_addr(request_like)),
        "user_agent_summary": _user_agent_summary(request_like),
    }
    context.update(_actor_from_user(current_user))
    return context


def normalize_audit_context(context: dict[str, Any] | None) -> dict[str, Any]:
    normalized = {
        "request_id": "",
        "actor_id": None,
        "actor_role": "",
        "actor_name": "",
        "source": "service",
        "ip_hash": "",
        "user_agent_summary": "",
    }
    if context:
        normalized.update({
            "request_id": _truncate(context.get("request_id", ""), MAX_REQUEST_ID_LENGTH),
            "actor_id": context.get("actor_id"),
            "actor_role": str(context.get("actor_role") or ""),
            "actor_name": _truncate(context.get("actor_name", ""), MAX_ACTOR_NAME_LENGTH),
            "source": str(context.get("source") or "service"),
            "ip_hash": str(context.get("ip_hash") or ""),
            "user_agent_summary": _truncate(context.get("user_agent_summary", ""), MAX_USER_AGENT_LENGTH),
        })
    return normalized


def extract_actor_from_context(context: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_audit_context(context)
    return {
        "actor_id": normalized["actor_id"],
        "actor_role": normalized["actor_role"],
        "actor_name": normalized["actor_name"],
    }
