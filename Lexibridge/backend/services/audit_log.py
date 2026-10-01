"""Audit-log convenience wrappers for security-sensitive events."""

from __future__ import annotations

from .logging_config import log_event, safe_log_context


def log_security_event(event, message, **context):
    return log_event("security_log", event, message, level="warning", **safe_log_context(context))


def log_job_event(event, message, **context):
    return log_event("job_log", event, message, level=context.pop("level", "info"), **safe_log_context(context))


def log_provider_event(event, message, **context):
    return log_event("ai_provider_log", event, message, level=context.pop("level", "info"), **safe_log_context(context))
