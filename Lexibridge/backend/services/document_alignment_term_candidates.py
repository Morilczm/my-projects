"""Pure chunk-scoped term candidates for formal document alignment."""

from __future__ import annotations

import re
import hashlib
import json
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable


FORMAL_DOCUMENT_TERM_EXTRACTION_VERSION = "formal-chunk-term-extraction-v1"
FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS = 50
FORMAL_TERM_MAX_CHUNK_REFS_PER_CANDIDATE = 100
FORMAL_TERM_MAX_LENGTH = 220
MULTI_CONTEXT_TERM_CANDIDATE = "MULTI_CONTEXT_TERM_CANDIDATE"
CANDIDATE_SET_OVERFLOW = "CANDIDATE_SET_OVERFLOW"
CANDIDATE_GOVERNANCE_ADMITTED = "admitted"
CANDIDATE_GOVERNANCE_OVERFLOW_REJECTED = "overflow_rejected"
CANDIDATE_GOVERNANCE_WITHIN_LIMIT = "within_item_limit"
CANDIDATE_GOVERNANCE_LIMIT_EXCEEDED = "candidate_set_item_limit_exceeded"

EXTRACTION_OUTCOME_EXTRACTED = "extracted"
EXTRACTION_OUTCOME_NO_CANDIDATES = "no_candidates"
EXTRACTION_OUTCOME_ITEM_LIMIT_EXCEEDED = "item_limit_exceeded"
EXTRACTION_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED = "term_scope_limit_exceeded"
EXTRACTION_OUTCOME_INVALID_CHUNK_SCOPE = "invalid_chunk_scope"
EXTRACTION_OUTCOME_EXTRACTION_FAILED = "extraction_failed"

ERROR_ITEM_LIMIT_EXCEEDED = "DOCUMENT_ALIGNMENT_ITEM_LIMIT_EXCEEDED"
ERROR_TERM_SCOPE_LIMIT_EXCEEDED = "DOCUMENT_ALIGNMENT_TERM_SCOPE_LIMIT_EXCEEDED"
ERROR_INVALID_CHUNK_SCOPE = "DOCUMENT_ALIGNMENT_CHUNK_NOT_AVAILABLE"
ERROR_EXTRACTION_FAILED = "DOCUMENT_ALIGNMENT_TERM_EXTRACTION_FAILED"


def _required_text(value: Any, field_name: str, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if max_length is not None and len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _optional_text(value: Any, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    return text if max_length is None else text[:max_length]


def _safe_error_message(message: Any, fallback: str) -> str:
    text = str(message or fallback).strip() or fallback
    forbidden = ("LEXIBRIDGE_SENTINEL_SECRET", "Authorization:", "Cookie:", "Bearer ", "sk-")
    if any(marker in text for marker in forbidden):
        return fallback
    return text[:500]


def _normalize_display_term(value: Any) -> str:
    raw = str(value or "")
    if any(unicodedata.category(char).startswith("C") and not char.isspace() for char in raw):
        raise ValueError("candidate term contains control characters.")
    text = unicodedata.normalize("NFKC", raw)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("candidate term is required.")
    if len(text) > FORMAL_TERM_MAX_LENGTH:
        raise ValueError("candidate term is too long.")
    return text


def _normalize_term(value: Any) -> str:
    return _normalize_display_term(value).casefold()


@dataclass(frozen=True)
class GovernedSourceChunkSnapshot:
    chunk_uid: str
    source_uid: str
    parse_uid: str
    source_version: str
    chunk_index: int
    text: str = field(repr=False)
    language: str = ""
    chapter_scope: str = ""

    def __post_init__(self):
        object.__setattr__(self, "chunk_uid", _required_text(self.chunk_uid, "chunk_uid", 64))
        object.__setattr__(self, "source_uid", _required_text(self.source_uid, "source_uid", 64))
        object.__setattr__(self, "parse_uid", _required_text(self.parse_uid, "parse_uid", 64))
        object.__setattr__(self, "source_version", _required_text(self.source_version, "source_version", 80))
        index = int(self.chunk_index)
        if index < 0:
            raise ValueError("chunk_index must be non-negative.")
        object.__setattr__(self, "chunk_index", index)
        object.__setattr__(self, "text", str(self.text or ""))
        object.__setattr__(self, "language", _optional_text(self.language, 30))
        object.__setattr__(self, "chapter_scope", _optional_text(self.chapter_scope, 160))


@dataclass(frozen=True)
class ChunkScopedTermCandidate:
    candidate_term: str
    normalized_term: str
    source_chunk_uids: tuple[str, ...]
    occurrence_count: int
    first_chunk_index: int
    extraction_method: str
    risk_labels: tuple[str, ...] = ()
    source_uid: str = ""
    candidate_id: str = ""
    governance_status: str = CANDIDATE_GOVERNANCE_ADMITTED
    governance_reason: str = CANDIDATE_GOVERNANCE_WITHIN_LIMIT

    def __post_init__(self):
        display = _normalize_display_term(self.candidate_term)
        normalized = _normalize_term(self.normalized_term)
        refs = tuple(sorted({_required_text(value, "source_chunk_uid", 64) for value in self.source_chunk_uids}))
        if not refs:
            raise ValueError("source_chunk_uids are required.")
        occurrences = int(self.occurrence_count)
        first_index = int(self.first_chunk_index)
        if occurrences <= 0:
            raise ValueError("occurrence_count must be positive.")
        if first_index < 0:
            raise ValueError("first_chunk_index must be non-negative.")
        object.__setattr__(self, "candidate_term", display)
        object.__setattr__(self, "normalized_term", normalized)
        object.__setattr__(self, "source_chunk_uids", refs)
        object.__setattr__(self, "occurrence_count", occurrences)
        object.__setattr__(self, "first_chunk_index", first_index)
        object.__setattr__(self, "extraction_method", _required_text(self.extraction_method, "extraction_method", 80))
        object.__setattr__(self, "risk_labels", tuple(sorted({_required_text(value, "risk_label", 120) for value in self.risk_labels})))
        source_uid = _optional_text(self.source_uid, 64)
        object.__setattr__(self, "source_uid", source_uid)
        candidate_id = _optional_text(self.candidate_id, 80)
        if not candidate_id:
            identity = json.dumps(
                {
                    "normalized_term": normalized,
                    "source_chunk_uids": refs,
                    "source_uid": source_uid,
                    "version": FORMAL_DOCUMENT_TERM_EXTRACTION_VERSION,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            candidate_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        object.__setattr__(self, "candidate_id", candidate_id)
        status = _required_text(self.governance_status, "governance_status", 80)
        if status not in {
            CANDIDATE_GOVERNANCE_ADMITTED,
            CANDIDATE_GOVERNANCE_OVERFLOW_REJECTED,
        }:
            raise ValueError("governance_status is invalid.")
        object.__setattr__(self, "governance_status", status)
        object.__setattr__(
            self,
            "governance_reason",
            _required_text(self.governance_reason, "governance_reason", 120),
        )


@dataclass(frozen=True)
class ChunkScopedTermCandidateExtractionResult:
    outcome: str
    candidates: tuple[ChunkScopedTermCandidate, ...] = ()
    source_chunk_count: int = 0
    raw_occurrence_count: int = 0
    canonical_candidate_count: int = 0
    warning_count: int = 0
    admitted_candidate_count: int = 0
    overflow_candidate_count: int = 0
    overflow_candidates: tuple[ChunkScopedTermCandidate, ...] = ()
    item_limit: int = FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS
    governance_status: str = CANDIDATE_GOVERNANCE_ADMITTED
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self):
        object.__setattr__(self, "candidates", tuple(self.candidates or ()))
        object.__setattr__(self, "overflow_candidates", tuple(self.overflow_candidates or ()))
        for name in (
            "source_chunk_count",
            "raw_occurrence_count",
            "canonical_candidate_count",
            "warning_count",
            "admitted_candidate_count",
            "overflow_candidate_count",
            "item_limit",
        ):
            value = int(getattr(self, name) or 0)
            if value < 0:
                raise ValueError(f"{name} must be non-negative.")
            object.__setattr__(self, name, value)
        admitted = len(self.candidates)
        overflow = len(self.overflow_candidates)
        object.__setattr__(self, "admitted_candidate_count", admitted)
        object.__setattr__(self, "overflow_candidate_count", overflow)
        if admitted + overflow > self.canonical_candidate_count:
            raise ValueError("governed candidate counts exceed canonical candidate count.")
        object.__setattr__(
            self,
            "governance_status",
            (
                CANDIDATE_GOVERNANCE_OVERFLOW_REJECTED
                if overflow
                else CANDIDATE_GOVERNANCE_ADMITTED
            ),
        )
        object.__setattr__(self, "error_code", _optional_text(self.error_code, 120))
        object.__setattr__(self, "error_message", _safe_error_message(self.error_message, "Term extraction failed.") if self.error_message else "")


def _failure(outcome: str, chunks: int, occurrences: int, candidates: int, code: str, message: str):
    return ChunkScopedTermCandidateExtractionResult(
        outcome=outcome,
        source_chunk_count=chunks,
        raw_occurrence_count=occurrences,
        canonical_candidate_count=candidates,
        error_code=code,
        error_message=message,
    )


def _candidate_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("candidate_term") or value.get("english_term") or value.get("term")
    return getattr(value, "candidate_term", None) or getattr(value, "english_term", None) or value


def _candidate_occurrences(value: Any) -> int:
    raw = value.get("occurrence_count", 1) if isinstance(value, dict) else getattr(value, "occurrence_count", 1)
    count = int(raw or 1)
    if count <= 0:
        raise ValueError("occurrence_count must be positive.")
    return count


def extract_chunk_scoped_term_candidates(
    chunks: Iterable[GovernedSourceChunkSnapshot],
    deterministic_extractor: Callable[[str], Iterable[Any]],
    *,
    expected_source_uid: str,
    expected_parse_uid: str,
    expected_source_version: str,
    max_items: int = FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS,
    max_chunk_refs: int = FORMAL_TERM_MAX_CHUNK_REFS_PER_CANDIDATE,
) -> ChunkScopedTermCandidateExtractionResult:
    expected_source = _required_text(expected_source_uid, "expected_source_uid", 64)
    expected_parse = _required_text(expected_parse_uid, "expected_parse_uid", 64)
    expected_version = _required_text(expected_source_version, "expected_source_version", 80)
    item_limit = min(int(max_items), FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS)
    scope_limit = int(max_chunk_refs)
    if item_limit <= 0 or scope_limit <= 0:
        raise ValueError("candidate limits must be positive.")

    ordered = sorted(tuple(chunks or ()), key=lambda chunk: (chunk.chunk_index, chunk.chunk_uid))
    if any(
        chunk.source_uid != expected_source
        or chunk.parse_uid != expected_parse
        or chunk.source_version != expected_version
        for chunk in ordered
    ):
        return _failure(
            EXTRACTION_OUTCOME_INVALID_CHUNK_SCOPE,
            len(ordered),
            0,
            0,
            ERROR_INVALID_CHUNK_SCOPE,
            "Governed chunk scope does not match the workflow source snapshot.",
        )

    grouped: dict[str, dict[str, Any]] = {}
    raw_occurrences = 0
    try:
        for chunk in ordered:
            if not chunk.text.strip():
                continue
            extracted = tuple(deterministic_extractor(chunk.text) or ())
            for raw_candidate in extracted:
                display = _normalize_display_term(_candidate_value(raw_candidate))
                normalized = _normalize_term(display)
                occurrences = _candidate_occurrences(raw_candidate)
                raw_occurrences += occurrences
                group = grouped.setdefault(
                    normalized,
                    {
                        "display": display,
                        "chunk_uids": set(),
                        "chunk_indexes": set(),
                        "occurrences": 0,
                        "first_index": chunk.chunk_index,
                    },
                )
                group["chunk_uids"].add(chunk.chunk_uid)
                group["chunk_indexes"].add(chunk.chunk_index)
                group["occurrences"] += occurrences
    except Exception as exc:
        return _failure(
            EXTRACTION_OUTCOME_EXTRACTION_FAILED,
            len(ordered),
            raw_occurrences,
            0,
            ERROR_EXTRACTION_FAILED,
            _safe_error_message(exc, "Term extraction failed."),
        )

    canonical_count = len(grouped)
    if canonical_count == 0:
        return ChunkScopedTermCandidateExtractionResult(
            outcome=EXTRACTION_OUTCOME_NO_CANDIDATES,
            source_chunk_count=len(ordered),
        )
    candidates = []
    for normalized, group in grouped.items():
        refs = tuple(sorted(group["chunk_uids"]))
        if len(refs) > scope_limit:
            return _failure(
                EXTRACTION_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED,
                len(ordered),
                raw_occurrences,
                canonical_count,
                ERROR_TERM_SCOPE_LIMIT_EXCEEDED,
                f"A candidate chunk scope exceeds the server limit {scope_limit}.",
            )
        indexes = sorted(group["chunk_indexes"])
        risks = ()
        if any(current - previous > 1 for previous, current in zip(indexes, indexes[1:])):
            risks = (MULTI_CONTEXT_TERM_CANDIDATE,)
        candidates.append(
            ChunkScopedTermCandidate(
                candidate_term=group["display"],
                normalized_term=normalized,
                source_chunk_uids=refs,
                occurrence_count=group["occurrences"],
                first_chunk_index=group["first_index"],
                extraction_method=FORMAL_DOCUMENT_TERM_EXTRACTION_VERSION,
                risk_labels=risks,
                source_uid=expected_source,
            )
        )
    candidates.sort(key=lambda candidate: (candidate.first_chunk_index, candidate.normalized_term, candidate.candidate_term))
    admitted = tuple(candidates[:item_limit])
    overflow = tuple(
        replace(
            candidate,
            risk_labels=tuple(sorted({*candidate.risk_labels, CANDIDATE_SET_OVERFLOW})),
            governance_status=CANDIDATE_GOVERNANCE_OVERFLOW_REJECTED,
            governance_reason=CANDIDATE_GOVERNANCE_LIMIT_EXCEEDED,
        )
        for candidate in candidates[item_limit:]
    )
    return ChunkScopedTermCandidateExtractionResult(
        outcome=EXTRACTION_OUTCOME_EXTRACTED,
        candidates=admitted,
        overflow_candidates=overflow,
        item_limit=item_limit,
        source_chunk_count=len(ordered),
        raw_occurrence_count=raw_occurrences,
        canonical_candidate_count=canonical_count,
        warning_count=(
            sum(bool(candidate.risk_labels) for candidate in admitted)
            + sum(bool(candidate.risk_labels) for candidate in overflow)
        ),
    )
