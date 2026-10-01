"""Local lexical knowledge indexing helpers."""

from __future__ import annotations

import json

from services.chunk_dedup import compute_content_hash, is_too_short_chunk, normalize_chunk_text
from services import knowledge_governance


INDEX_BACKEND = "local_lexical"
INDEX_VERSION = "local_lexical_v1"
RETRIEVAL_VERSION = "local_lexical_v1"


def build_knowledge_chunk_fields(document, document_chunk, source, kb_version_id: int, chunk_index: int) -> dict:
    text = getattr(document_chunk, "content", "") or ""
    normalized = normalize_chunk_text(text)
    content_hash = compute_content_hash(text)
    quality_flags = _loads_json(getattr(document_chunk, "quality_flags_json", "[]"), [])
    quality_status = next((flag for flag in quality_flags if flag in knowledge_governance.REVIEW_PARSE_STATUSES or flag in knowledge_governance.BLOCKED_PARSE_STATUSES or flag in {"native_text_ok", "ocr_text_ok"}), "")
    chunk_status = "blocked" if quality_status in knowledge_governance.BLOCKED_PARSE_STATUSES else ("needs_review" if quality_status in knowledge_governance.REVIEW_PARSE_STATUSES else "active")
    scope_type = getattr(document, "scope_type", "course") or "course"
    if scope_type == "personal":
        kb_type = "student_personal_kb"
        visibility = "private"
    else:
        kb_type = "en_course_kb" if getattr(document, "language", "") == "en" else "zh_course_kb"
        visibility = "global" if scope_type == "global" else "course"
    index_status = "skipped" if is_too_short_chunk(text) else "pending"
    return {
        "knowledge_base_version_id": kb_version_id,
        "knowledge_source_id": getattr(source, "id", None),
        "source_id": getattr(source, "id", None),
        "source_uid": getattr(source, "source_uid", ""),
        "document_id": getattr(document, "id", None),
        "course_id": getattr(document, "course_id", None),
        "scope_type": scope_type,
        "owner_user_id": str(getattr(document, "owner_user_id", "") or ""),
        "parse_uid": getattr(document_chunk, "parse_uid", "") or getattr(document, "parse_uid", ""),
        "parse_block_uid": getattr(document_chunk, "parse_block_uid", ""),
        "language": getattr(document_chunk, "language", "") or getattr(document, "language", ""),
        "knowledge_base_type": kb_type,
        "visibility": visibility,
        "chunk_index": chunk_index,
        "content": text,
        "normalized_text": normalized,
        "content_hash": content_hash,
        "source_page": getattr(document_chunk, "source_location", "") or (f"page {getattr(document_chunk, 'page_number', '')}" if getattr(document_chunk, "page_number", None) else ""),
        "source_locator": getattr(document_chunk, "source_location", ""),
        "page_number": getattr(document_chunk, "page_number", None),
        "slide_number": getattr(document_chunk, "slide_number", None),
        "block_type": "text",
        "token_count": len(normalized.split()),
        "char_count": len(text),
        "source_slide": str(getattr(document_chunk, "slide_number", "") or ""),
        "source_section": getattr(document_chunk, "section_title", "") or "",
        "source_citation": f"{getattr(document, 'filename', '')} {getattr(document_chunk, 'source_location', '') or ''}".strip(),
        "quality_status": quality_status,
        "quality_flags": json.dumps(quality_flags, ensure_ascii=False),
        "trust_level": getattr(source, "trust_level", "") or "unknown",
        "status": chunk_status,
        "embedding_status": "not_started",
        "index_status": index_status,
        "is_active": index_status != "skipped" and chunk_status != "blocked",
    }


def _loads_json(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, list) else fallback
