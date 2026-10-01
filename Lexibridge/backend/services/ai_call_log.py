"""AI call log redaction, hashing, and token-estimation helpers."""

from __future__ import annotations

import hashlib
import json

from .logging_config import redact_sensitive_value, safe_log_context


def stable_json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def hash_payload(value):
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def estimate_tokens(value):
    text = stable_json(value) if not isinstance(value, str) else value
    if not text:
        return 0
    # Conservative approximation for English/Chinese mixed prompts.
    return max(1, int(len(text) / 4))


def preview_payload(value, limit=300):
    redacted = safe_log_context(value) if isinstance(value, dict) else redact_sensitive_value(value)
    text = stable_json(redacted) if not isinstance(redacted, str) else redacted
    if len(text) > limit:
        return text[:limit] + f"...[truncated {len(text) - limit} chars]"
    return text
