"""Service helpers for system-level observable audit records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from services import audit_context as audit_context_service


CONCEPT_CARD_TARGET_TYPE = "concept_alignment_card"
SENSITIVE_KEY_PARTS = ("api_key", "apikey", "secret", "password", "token")
JSON_FIELDS = {
    "before_snapshot",
    "after_snapshot",
    "input_payload",
    "output_payload",
    "changed_fields",
}
CONCEPT_CARD_SNAPSHOT_FIELDS = (
    "card_uid",
    "english_term",
    "chinese_term",
    "course",
    "chapter",
    "status",
    "confidence_score",
    "risk_labels",
    "version",
    "reviewed_by",
    "reviewed_at",
)
EVIDENCE_SUMMARY_FIELDS = (
    "source",
    "source_id",
    "document_id",
    "page",
    "page_number",
    "chunk_id",
    "score",
)


class AuditRecordError(ValueError):
    """Base service-layer error for audit records."""


class AuditRecordNotFoundError(AuditRecordError):
    """Raised when an audit record id or uid cannot be found."""


@dataclass(frozen=True)
class AuditRecordListResult:
    items: list[Any]
    page: int
    per_page: int
    total: int

    @property
    def pagination(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "per_page": self.per_page,
            "total": self.total,
            "has_next": self.page * self.per_page < self.total,
        }


def _loads_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _dumps_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _truncate_text(value: str, limit: int = 500) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated]"


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _summarize_evidence(value: Any) -> Any:
    parsed = _loads_json(value, value)
    if isinstance(parsed, list):
        return [_summarize_evidence(item) for item in parsed[:20]]
    if isinstance(parsed, dict):
        return {field: parsed.get(field) for field in EVIDENCE_SUMMARY_FIELDS if field in parsed}
    if parsed in (None, ""):
        return []
    return {"text_length": len(str(parsed))}


def _sanitize_payload(value: Any, key: str = "") -> Any:
    if _is_sensitive_key(key):
        return "[REDACTED]"
    if key in {"english_evidence", "chinese_evidence"}:
        return _summarize_evidence(value)
    if isinstance(value, dict):
        return {str(item_key): _sanitize_payload(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        limited = [_sanitize_payload(item) for item in value[:50]]
        if len(value) > 50:
            limited.append({"truncated_count": len(value) - 50})
        return limited
    if isinstance(value, str):
        return _truncate_text(value)
    return value


def _normalize_json_field(value: Any) -> str:
    if isinstance(value, str):
        parsed = _loads_json(value, None)
        if parsed is not None:
            return _dumps_json(_sanitize_payload(parsed))
        return _dumps_json(_sanitize_payload(value))
    return _dumps_json(_sanitize_payload(value))


def _actor_fields(actor: Any) -> dict[str, Any]:
    if actor is None:
        return {"actor_id": None, "actor_role": "", "actor_name": ""}
    if isinstance(actor, dict):
        return {
            "actor_id": actor.get("actor_id") or actor.get("id"),
            "actor_role": str(actor.get("actor_role") or actor.get("role") or ""),
            "actor_name": str(actor.get("actor_name") or actor.get("name") or actor.get("username") or ""),
        }
    return {
        "actor_id": getattr(actor, "id", None),
        "actor_role": str(getattr(actor, "role", "") or ""),
        "actor_name": str(
            getattr(actor, "display_name", "")
            or getattr(actor, "username", "")
            or getattr(actor, "email", "")
            or ""
        ),
    }


def _context_fields(audit_context: dict[str, Any] | None = None, actor: Any = None, source: str = "") -> dict[str, Any]:
    normalized = audit_context_service.normalize_audit_context(audit_context)
    actor_fields = audit_context_service.extract_actor_from_context(normalized)
    if actor is not None and actor_fields.get("actor_id") is None:
        actor_fields = _actor_fields(actor)
    context_source = normalized.get("source") or "service"
    effective_source = source or context_source
    if audit_context and source == "service" and context_source != "service":
        effective_source = context_source
    return {
        "request_id": normalized.get("request_id", ""),
        "source": effective_source,
        **actor_fields,
    }


def concept_card_snapshot(card: Any | dict[str, Any] | None) -> dict[str, Any]:
    if card is None:
        return {}
    if isinstance(card, dict):
        source = card
        getter = source.get
    else:
        getter = lambda field, default=None: getattr(card, field, default)
    snapshot = {field: getter(field, "") for field in CONCEPT_CARD_SNAPSHOT_FIELDS}
    snapshot["risk_labels"] = _loads_json(snapshot.get("risk_labels"), [])
    return _sanitize_payload(snapshot)


def changed_fields(before_snapshot: dict[str, Any] | None, after_snapshot: dict[str, Any] | None) -> list[str]:
    before = before_snapshot or {}
    after = after_snapshot or {}
    fields = sorted(set(before) | set(after))
    return [field for field in fields if before.get(field) != after.get(field)]


def create_audit_record(
    session: Any,
    audit_model: Any,
    data: dict[str, Any],
    *,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = True,
) -> Any:
    payload = dict(data or {})
    context_fields = _context_fields(audit_context, source=payload.get("source", ""))
    for field, value in context_fields.items():
        payload.setdefault(field, value)
    payload.setdefault("source", "service")
    payload.setdefault("result", "success")
    payload.setdefault("created_at", now_fn() if now_fn else "")
    for field in JSON_FIELDS:
        payload[field] = _normalize_json_field(payload.get(field, [] if field == "changed_fields" else {}))
    record = audit_model(**payload)
    session.add(record)
    if commit:
        session.commit()
    else:
        session.flush()
    return record


def record_concept_card_created(
    session: Any,
    audit_model: Any,
    card: Any,
    *,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    input_payload: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
) -> Any:
    after = concept_card_snapshot(card)
    data = {
        "event_type": "concept_card_created",
        "target_type": CONCEPT_CARD_TARGET_TYPE,
        "target_uid": after.get("card_uid", ""),
        "source": source,
        "after_snapshot": after,
        "input_payload": input_payload or {},
        "output_payload": {"card_uid": after.get("card_uid", ""), "status": after.get("status", "")},
        "changed_fields": sorted(after.keys()),
        "result": "success",
        **_context_fields(audit_context, actor=actor, source=source),
    }
    return create_audit_record(session, audit_model, data, audit_context=audit_context, now_fn=now_fn, commit=commit)


def record_concept_card_updated(
    session: Any,
    audit_model: Any,
    card_before: Any,
    card_after: Any,
    *,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    input_payload: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
) -> Any:
    before = concept_card_snapshot(card_before)
    after = concept_card_snapshot(card_after)
    data = {
        "event_type": "concept_card_updated",
        "target_type": CONCEPT_CARD_TARGET_TYPE,
        "target_uid": after.get("card_uid") or before.get("card_uid", ""),
        "source": source,
        "before_snapshot": before,
        "after_snapshot": after,
        "input_payload": input_payload or {},
        "output_payload": {"card_uid": after.get("card_uid", ""), "status": after.get("status", "")},
        "changed_fields": changed_fields(before, after),
        "result": "success",
        **_context_fields(audit_context, actor=actor, source=source),
    }
    return create_audit_record(session, audit_model, data, audit_context=audit_context, now_fn=now_fn, commit=commit)


def record_concept_card_status_changed(
    session: Any,
    audit_model: Any,
    card_before: Any,
    card_after: Any,
    *,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    input_payload: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
) -> Any:
    before = concept_card_snapshot(card_before)
    after = concept_card_snapshot(card_after)
    data = {
        "event_type": "concept_card_status_changed",
        "target_type": CONCEPT_CARD_TARGET_TYPE,
        "target_uid": after.get("card_uid") or before.get("card_uid", ""),
        "source": source,
        "before_snapshot": before,
        "after_snapshot": after,
        "input_payload": input_payload or {},
        "output_payload": {"card_uid": after.get("card_uid", ""), "status": after.get("status", "")},
        "changed_fields": changed_fields(before, after),
        "result": "success",
        **_context_fields(audit_context, actor=actor, source=source),
    }
    return create_audit_record(session, audit_model, data, audit_context=audit_context, now_fn=now_fn, commit=commit)


def record_concept_card_operation_failed(
    session: Any,
    audit_model: Any,
    *,
    target_uid: str | None = None,
    event_type: str | None = None,
    error: Exception | str | None = None,
    error_code: str | None = None,
    input_payload: dict[str, Any] | None = None,
    actor: Any = None,
    audit_context: dict[str, Any] | None = None,
    source: str = "service",
    now_fn=None,
    commit: bool = True,
) -> Any:
    message = str(error or "")
    data = {
        "event_type": event_type or "concept_card_operation_failed",
        "target_type": CONCEPT_CARD_TARGET_TYPE,
        "target_uid": target_uid or "",
        "source": source,
        "input_payload": input_payload or {},
        "output_payload": {"error_message": message},
        "changed_fields": [],
        "result": "error",
        "error_code": error_code or (error.__class__.__name__ if isinstance(error, Exception) else "operation_failed"),
        "error_message": message,
        **_context_fields(audit_context, actor=actor, source=source),
    }
    return create_audit_record(session, audit_model, data, audit_context=audit_context, now_fn=now_fn, commit=commit)


def get_audit_record(session: Any, audit_model: Any, audit_uid: Any) -> Any:
    if audit_uid in (None, ""):
        raise AuditRecordNotFoundError("AuditRecord not found.")
    record = None
    if isinstance(audit_uid, int) or str(audit_uid).isdigit():
        record = session.get(audit_model, int(audit_uid))
    if record is None:
        record = audit_model.query.filter_by(audit_uid=str(audit_uid)).first()
    if record is None:
        raise AuditRecordNotFoundError("AuditRecord not found.")
    return record


def list_audit_records(session: Any, audit_model: Any, filters: dict[str, Any] | None = None) -> AuditRecordListResult:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    per_page = max(1, min(int(filters.get("per_page") or filters.get("page_size") or 20), 100))
    query = audit_model.query

    for field in ("target_type", "target_uid", "event_type", "result", "request_id"):
        value = str(filters.get(field) or "").strip()
        if value:
            query = query.filter_by(**{field: value})

    total = query.count()
    items = query.order_by(audit_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return AuditRecordListResult(items=items, page=page, per_page=per_page, total=total)


def serialize_audit_record(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "audit_uid": record.audit_uid,
        "event_type": record.event_type,
        "target_type": record.target_type,
        "target_uid": record.target_uid,
        "actor_id": record.actor_id,
        "actor_role": record.actor_role,
        "actor_name": record.actor_name,
        "request_id": record.request_id,
        "source": record.source,
        "before_snapshot": _loads_json(record.before_snapshot, {}),
        "after_snapshot": _loads_json(record.after_snapshot, {}),
        "input_payload": _loads_json(record.input_payload, {}),
        "output_payload": _loads_json(record.output_payload, {}),
        "changed_fields": _loads_json(record.changed_fields, []),
        "result": record.result,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "model_name": record.model_name,
        "prompt_version": record.prompt_version,
        "retrieval_version": record.retrieval_version,
        "latency_ms": record.latency_ms,
        "created_at": record.created_at,
    }
