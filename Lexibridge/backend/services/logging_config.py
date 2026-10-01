"""Structured logging helpers with conservative redaction defaults."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime


SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "auth_token",
    "authorization",
    "api_key",
    "secret",
    "secret_key",
    "deepseek_api_key",
    "mathpix_app_key",
    "prompt",
    "ai_prompt",
    "ai_response",
    "ocr_text",
    "file_text",
    "content",
}

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.]{12,}", re.IGNORECASE),
]


def redact_sensitive_value(value):
    """Return a log-safe representation of a potentially sensitive value."""
    if value is None:
        return None
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > 120:
        text = text[:80] + f"...[truncated {len(text) - 80} chars]"
    return text


def safe_log_context(context):
    """Drop or redact sensitive fields while keeping IDs and short metadata."""
    safe = {}
    for key, value in dict(context or {}).items():
        key_text = str(key)
        lowered = key_text.lower()
        if any(part in lowered for part in SENSITIVE_KEYS):
            if lowered.endswith("_id") or lowered in {"user_id", "course_id", "document_id", "job_id"}:
                safe[key_text] = value
            else:
                safe[key_text] = "[REDACTED]"
            continue
        if isinstance(value, dict):
            safe[key_text] = safe_log_context(value)
        elif isinstance(value, (list, tuple)):
            safe[key_text] = [redact_sensitive_value(item) for item in value[:20]]
        elif isinstance(value, (int, float, bool)):
            safe[key_text] = value
        else:
            safe[key_text] = redact_sensitive_value(value)
    return safe


def log_event(module, event, message, level="info", logger=None, **context):
    """Emit a structured JSON log line."""
    logger = logger or logging.getLogger("lexibridge")
    payload = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "level": str(level or "info").lower(),
        "module": module,
        "event": event,
        "message": redact_sensitive_value(message),
    }
    payload.update(safe_log_context(context))
    log_method = getattr(logger, payload["level"], logger.info)
    log_method(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


def configure_logging(level="INFO"):
    logging.basicConfig(level=getattr(logging, str(level or "INFO").upper(), logging.INFO))
