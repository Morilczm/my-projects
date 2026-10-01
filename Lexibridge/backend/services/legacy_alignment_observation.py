"""Structured, payload-free telemetry for legacy alignment retirement."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Iterable, Optional

from .logging_config import log_event


MODULE = "legacy_alignment_observation"
REQUEST_EVENT = "legacy_alignment_request"
INTERNAL_CREATION_EVENT = "legacy_alignment_internal_creation"


def request_result(status_code: int, error_code: str = "") -> str:
    code = int(status_code or 0)
    if 200 <= code < 400:
        return "success"
    if str(error_code or "") == "LEGACY_ALIGNMENT_ADMISSION_DISABLED":
        return "admission_blocked"
    if code in {401, 403}:
        return "access_denied"
    return "error"


def log_request(
    *,
    method: str,
    route: str,
    endpoint: str,
    status_code: int,
    error_code: str = "",
    caller_id: Any = None,
    caller_role: str = "unknown",
    request_id: str = "",
    request_mode: str = "read",
    alignment_run_creations: int = 0,
    background_job_creations: int = 0,
    logger=None,
) -> dict[str, Any]:
    return log_event(
        MODULE,
        REQUEST_EVENT,
        "Legacy alignment compatibility request observed.",
        logger=logger,
        method=str(method or "").upper(),
        route=str(route or ""),
        endpoint=str(endpoint or ""),
        status_code=int(status_code or 0),
        result=request_result(status_code, error_code),
        error_code=str(error_code or ""),
        caller_id=caller_id,
        caller_role=str(caller_role or "unknown"),
        request_id=str(request_id or ""),
        request_mode=str(request_mode or "read"),
        alignment_run_creations=max(0, int(alignment_run_creations or 0)),
        background_job_creations=max(0, int(background_job_creations or 0)),
    )


def log_internal_creation(
    *,
    entity: str,
    source: str,
    caller_id: Any = None,
    result: str = "created_in_transaction",
    logger=None,
) -> dict[str, Any]:
    return log_event(
        MODULE,
        INTERNAL_CREATION_EVENT,
        "Legacy alignment internal creation signal observed.",
        logger=logger,
        entity=str(entity or "unknown"),
        source=str(source or "unknown"),
        caller_id=caller_id,
        result=str(result or "created_in_transaction"),
    )


def parse_event_line(line: str) -> Optional[dict[str, Any]]:
    text = str(line or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        payload = json.loads(text[start:])
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("module") != MODULE:
        return None
    return payload


def summarize_events(lines: Iterable[str]) -> dict[str, Any]:
    events = [event for event in (parse_event_line(line) for line in lines) if event is not None]
    requests = [event for event in events if event.get("event") == REQUEST_EVENT]
    internal = [event for event in events if event.get("event") == INTERNAL_CREATION_EVENT]
    timestamps = sorted(str(event.get("timestamp") or "") for event in events if event.get("timestamp"))
    request_routes = Counter(
        f"{event.get('method', '')} {event.get('route', '')}" for event in requests
    )
    request_results = Counter(str(event.get("result") or "unknown") for event in requests)
    callers = Counter(
        f"{event.get('caller_role', 'unknown')}:{event.get('caller_id', 'unknown')}"
        for event in requests
    )
    request_run_creations = sum(int(event.get("alignment_run_creations") or 0) for event in requests)
    request_job_creations = sum(int(event.get("background_job_creations") or 0) for event in requests)
    internal_entities = Counter(str(event.get("entity") or "unknown") for event in internal)
    return {
        "event_count": len(events),
        "first_timestamp": timestamps[0] if timestamps else "",
        "last_timestamp": timestamps[-1] if timestamps else "",
        "request_count": len(requests),
        "request_counts_by_route": dict(sorted(request_routes.items())),
        "request_counts_by_result": dict(sorted(request_results.items())),
        "caller_counts": dict(sorted(callers.items())),
        "request_alignment_run_creation_count": request_run_creations,
        "request_background_job_creation_count": request_job_creations,
        "internal_creation_signal_count": len(internal),
        "internal_creation_counts_by_entity": dict(sorted(internal_entities.items())),
        "legacy_creation_signal_count": request_run_creations + request_job_creations + len(internal),
    }
