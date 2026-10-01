"""Unified governed knowledge ingestion helpers.

This layer orchestrates parse-record quality gates and governed
KnowledgeSource/KnowledgeChunk creation. It does not create embeddings, vector
indexes, reranker artifacts, or model outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services import audit_records
from services import knowledge_governance


ALLOWED_PARSE_STATUSES = {"native_text_ok", "ocr_text_ok", "partial_text"}
BLOCKED_PARSE_STATUSES = knowledge_governance.BLOCKED_PARSE_STATUSES | {
    "empty_text",
    "ocr_required",
    "ocr_unavailable",
    "parse_failed",
    "unsupported_file_type",
}


@dataclass(frozen=True)
class KnowledgeIngestionModels:
    source_model: Any
    chunk_model: Any
    version_model: Any | None = None
    audit_model: Any | None = None


@dataclass(frozen=True)
class KnowledgeIngestionResult:
    source: Any
    chunks: list[Any]
    parse_record: Any
    ingestion_status: str
    blocked_reason: str = ""
    warnings: list[str] | None = None

    @property
    def chunk_uids(self) -> list[str]:
        return [getattr(chunk, "chunk_uid", "") for chunk in self.chunks if getattr(chunk, "chunk_uid", "")]


class KnowledgeIngestionError(ValueError):
    """Base error for governed knowledge ingestion."""


class KnowledgeIngestionBlockedError(KnowledgeIngestionError):
    """Raised when parse quality or empty content blocks ingestion."""

    def __init__(self, message: str, *, parse_record: Any = None, blocked_reason: str = ""):
        super().__init__(message)
        self.parse_record = parse_record
        self.blocked_reason = blocked_reason or message


def _quality_status(parse_record: Any) -> str:
    return str(getattr(parse_record, "quality_status", "") or "")


def _json_list(value: Any) -> list[Any]:
    return knowledge_governance.normalize_list(value)


def should_ingest_parse_record(parse_record: Any) -> bool:
    return _quality_status(parse_record) in ALLOWED_PARSE_STATUSES


def ingestion_status_for_parse(parse_record: Any) -> str:
    return "partial" if _quality_status(parse_record) == "partial_text" else "ingested"


def blocked_reason_for_parse(parse_record: Any) -> str:
    quality_status = _quality_status(parse_record) or "unknown"
    return f"Blocked by parse quality gate: {quality_status}"


def _audit_summary(parse_record: Any, metadata: dict[str, Any] | None = None, **extra) -> dict[str, Any]:
    metadata = metadata or {}
    payload = {
        "parse_uid": getattr(parse_record, "parse_uid", ""),
        "course": metadata.get("course", ""),
        "chapter": metadata.get("chapter", ""),
        "language": metadata.get("language", ""),
        "source_type": metadata.get("source_type", ""),
        "source_role": metadata.get("source_role", ""),
        "trust_level": metadata.get("trust_level", ""),
        "quality_status": _quality_status(parse_record),
    }
    payload.update({key: value for key, value in extra.items() if value not in (None, "")})
    return payload


def record_knowledge_ingestion_completed(
    session: Any,
    audit_model: Any | None,
    *,
    source: Any,
    chunks: list[Any],
    parse_record: Any,
    metadata: dict[str, Any] | None = None,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = False,
) -> Any | None:
    if audit_model is None:
        return None
    return audit_records.create_audit_record(
        session,
        audit_model,
        {
            "event_type": "knowledge_ingestion_completed",
            "target_type": "knowledge_source",
            "target_uid": getattr(source, "source_uid", ""),
            "source": "api" if audit_context else "service",
            "input_payload": _audit_summary(parse_record, metadata),
            "output_payload": _audit_summary(
                parse_record,
                metadata,
                source_uid=getattr(source, "source_uid", ""),
                chunk_count=len(chunks),
                ingestion_status=ingestion_status_for_parse(parse_record),
            ),
            "changed_fields": [],
            "result": "success",
        },
        audit_context=audit_context,
        now_fn=now_fn,
        commit=commit,
    )


def record_knowledge_ingestion_blocked(
    session: Any,
    audit_model: Any | None,
    *,
    parse_record: Any,
    metadata: dict[str, Any] | None = None,
    blocked_reason: str,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = False,
) -> Any | None:
    if audit_model is None:
        return None
    return audit_records.create_audit_record(
        session,
        audit_model,
        {
            "event_type": "knowledge_ingestion_blocked",
            "target_type": "document_parse_record",
            "target_uid": getattr(parse_record, "parse_uid", ""),
            "source": "api" if audit_context else "service",
            "input_payload": _audit_summary(parse_record, metadata),
            "output_payload": _audit_summary(
                parse_record,
                metadata,
                ingestion_status="blocked",
                blocked_reason=blocked_reason,
                chunk_count=0,
            ),
            "changed_fields": [],
            "result": "error",
            "error_code": "blocked_by_quality_gate",
            "error_message": blocked_reason,
        },
        audit_context=audit_context,
        now_fn=now_fn,
        commit=commit,
    )


def _normalize_metadata(parse_record: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(metadata or {})
    metadata.setdefault("title", getattr(parse_record, "source_filename", "") or "Untitled knowledge source")
    metadata.setdefault("source_filename", getattr(parse_record, "source_filename", ""))
    metadata.setdefault("file_type", getattr(parse_record, "file_type", "unknown") or "unknown")
    metadata.setdefault("parse_uid", getattr(parse_record, "parse_uid", ""))
    quality_status = _quality_status(parse_record)
    metadata.setdefault("quality_status", quality_status)
    flags = set(_json_list(metadata.get("quality_flags", [])))
    flags.update(_json_list(getattr(parse_record, "quality_flags", [])))
    if quality_status:
        flags.add(quality_status)
    metadata["quality_flags"] = sorted(flag for flag in flags if flag)
    if quality_status == "partial_text":
        metadata["trust_level"] = "low_quality"
    return metadata


def get_or_create_knowledge_source_for_parse(
    session: Any,
    models: KnowledgeIngestionModels,
    parse_record: Any,
    metadata: dict[str, Any] | None = None,
    *,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
) -> Any:
    metadata = _normalize_metadata(parse_record, metadata)
    parse_uid = getattr(parse_record, "parse_uid", "")
    document_id = metadata.get("document_id")
    query = models.source_model.query.filter_by(parse_uid=parse_uid)
    if document_id not in (None, ""):
        query = query.filter_by(document_id=document_id)
    source = query.first()
    if source is not None:
        if not getattr(source, "source_uid", ""):
            import uuid

            source.source_uid = str(uuid.uuid4())
        for field in (
            "title",
            "name",
            "source_title",
            "course",
            "chapter",
            "language",
            "source_type",
            "source_role",
            "owner_type",
            "owner_id",
            "visibility",
            "trust_level",
            "quality_status",
            "quality_flags",
            "source_filename",
            "file_type",
            "content_hash",
            "license_status",
            "license_type",
            "authorization_status",
            "source_quality",
            "allow_full_text_indexing",
            "allow_student_search",
            "allow_derivative_cards",
            "knowledge_base_type",
            "scope_type",
            "document_id",
            "owner_user_id",
        ):
            if field in metadata and hasattr(source, field):
                value = metadata[field]
                if field == "quality_flags":
                    value = knowledge_governance.dumps_json_list(value)
                setattr(source, field, value)
        source.updated_at = now_fn() if now_fn else getattr(source, "updated_at", "")
        session.flush()
        return source
    source_data = knowledge_governance.build_knowledge_source_from_parse_record(parse_record, metadata)
    return knowledge_governance.create_knowledge_source(
        session,
        models.source_model,
        source_data,
        version_model=models.version_model,
        audit_model=models.audit_model,
        audit_context=audit_context,
        now_fn=now_fn,
        commit=False,
    )


def ingest_parse_blocks_to_chunks(
    session: Any,
    models: KnowledgeIngestionModels,
    source: Any,
    parse_record: Any,
    parse_blocks: list[Any],
    metadata: dict[str, Any] | None = None,
    *,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
) -> list[Any]:
    metadata = _normalize_metadata(parse_record, metadata)
    chunk_data = knowledge_governance.build_knowledge_chunks_from_parse_blocks(
        parse_record,
        parse_blocks,
        getattr(source, "source_uid", ""),
        metadata,
    )
    if not chunk_data:
        raise KnowledgeIngestionBlockedError(
            "Parse record has no valid text blocks for governed knowledge chunks.",
            parse_record=parse_record,
            blocked_reason="Parse record has no valid text blocks for governed knowledge chunks.",
        )
    return knowledge_governance.create_knowledge_chunks(
        session,
        models.chunk_model,
        source,
        chunk_data,
        audit_model=models.audit_model,
        audit_context=audit_context,
        now_fn=now_fn,
        commit=False,
    )


def ingest_parse_record_to_governed_knowledge(
    session: Any,
    models: KnowledgeIngestionModels,
    parse_record: Any,
    parse_blocks: list[Any],
    metadata: dict[str, Any] | None = None,
    *,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = True,
) -> KnowledgeIngestionResult:
    metadata = _normalize_metadata(parse_record, metadata)
    if not should_ingest_parse_record(parse_record):
        blocked_reason = blocked_reason_for_parse(parse_record)
        record_knowledge_ingestion_blocked(
            session,
            models.audit_model,
            parse_record=parse_record,
            metadata=metadata,
            blocked_reason=blocked_reason,
            audit_context=audit_context,
            now_fn=now_fn,
            commit=False,
        )
        if commit:
            session.commit()
        raise KnowledgeIngestionBlockedError(blocked_reason, parse_record=parse_record, blocked_reason=blocked_reason)

    source = get_or_create_knowledge_source_for_parse(
        session,
        models,
        parse_record,
        metadata,
        audit_context=audit_context,
        now_fn=now_fn,
    )
    try:
        chunks = ingest_parse_blocks_to_chunks(
            session,
            models,
            source,
            parse_record,
            parse_blocks,
            metadata,
            audit_context=audit_context,
            now_fn=now_fn,
        )
    except KnowledgeIngestionBlockedError as exc:
        record_knowledge_ingestion_blocked(
            session,
            models.audit_model,
            parse_record=parse_record,
            metadata=metadata,
            blocked_reason=exc.blocked_reason,
            audit_context=audit_context,
            now_fn=now_fn,
            commit=False,
        )
        if commit:
            session.commit()
        raise

    record_knowledge_ingestion_completed(
        session,
        models.audit_model,
        source=source,
        chunks=chunks,
        parse_record=parse_record,
        metadata=metadata,
        audit_context=audit_context,
        now_fn=now_fn,
        commit=False,
    )
    if commit:
        session.commit()
    return KnowledgeIngestionResult(
        source=source,
        chunks=chunks,
        parse_record=parse_record,
        ingestion_status=ingestion_status_for_parse(parse_record),
        warnings=_json_list(getattr(parse_record, "warnings", [])),
    )


def sync_legacy_knowledge_from_governed_chunks(source: Any, chunks: list[Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    legacy_record = metadata.get("legacy_record")
    if legacy_record is not None:
        if hasattr(legacy_record, "parse_uid"):
            legacy_record.parse_uid = getattr(source, "parse_uid", getattr(legacy_record, "parse_uid", ""))
        if hasattr(legacy_record, "chunk_count"):
            legacy_record.chunk_count = len(chunks)
        if hasattr(legacy_record, "text_length"):
            legacy_record.text_length = sum(len(getattr(chunk, "content", "") or "") for chunk in chunks)
    return {
        "source_uid": getattr(source, "source_uid", ""),
        "chunk_count": len(chunks),
        "chunk_uids": [getattr(chunk, "chunk_uid", "") for chunk in chunks if getattr(chunk, "chunk_uid", "")],
    }


def build_ingestion_response(
    source: Any,
    chunks: list[Any],
    parse_record: Any,
    warnings: list[str] | None = None,
    *,
    blocked_reason: str = "",
) -> dict[str, Any]:
    quality_status = _quality_status(parse_record)
    ingestion_status = "blocked" if blocked_reason else ingestion_status_for_parse(parse_record)
    return {
        "source_uid": getattr(source, "source_uid", "") if source is not None else "",
        "chunk_count": len(chunks or []),
        "chunk_uids": [getattr(chunk, "chunk_uid", "") for chunk in (chunks or [])[:20] if getattr(chunk, "chunk_uid", "")],
        "parse_uid": getattr(parse_record, "parse_uid", ""),
        "quality_status": quality_status,
        "quality_flags": _json_list(getattr(parse_record, "quality_flags", [])),
        "ingestion_status": ingestion_status,
        "blocked_reason": blocked_reason,
        "warnings": warnings or _json_list(getattr(parse_record, "warnings", [])),
    }
