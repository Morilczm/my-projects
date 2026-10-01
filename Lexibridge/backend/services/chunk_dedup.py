"""Chunk normalization and deterministic duplicate detection."""

from __future__ import annotations

import hashlib
import re


def normalize_chunk_text(text: str) -> str:
    normalized = str(text or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff\s.,;:()\-+/=]", "", normalized)
    return normalized.strip()


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(normalize_chunk_text(text).encode("utf-8")).hexdigest()


def is_too_short_chunk(text: str, min_chars: int = 12) -> bool:
    return len(normalize_chunk_text(text)) < min_chars


def find_duplicate_chunk(content_hash: str, kb_version_id: int, chunks) -> object | None:
    for chunk in chunks:
        if getattr(chunk, "knowledge_base_version_id", None) != kb_version_id:
            continue
        if getattr(chunk, "content_hash", "") == content_hash and not bool(getattr(chunk, "is_duplicate", False)):
            return chunk
    return None


def mark_duplicate_chunk(chunk, duplicate_of_chunk_id: int) -> None:
    chunk.is_duplicate = True
    chunk.duplicate_of_chunk_id = duplicate_of_chunk_id
    chunk.index_status = "duplicate"
    chunk.is_active = False
