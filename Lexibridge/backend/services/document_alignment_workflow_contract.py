"""Formal document alignment workflow contract constants and pure keys.

This module is deliberately free of Flask, database sessions, environment
configuration, provider clients, and execution logic. It is the single source
for workflow root/item status and stage strings used by the model layer.
"""

import hashlib
import json
import re
import unicodedata

WORKFLOW_NAME = "FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION"
CANONICAL_INPUT = "GOVERNED_KNOWLEDGE_SOURCE"
EXECUTION_MODEL = "ASYNC_JOB_ORCHESTRATION"
DATA_POLICY = "NO_LEGACY_AND_FORMAL_DUAL_WRITE"
WORKFLOW_VERSION_V1 = "formal-document-alignment-v1"
FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION = WORKFLOW_VERSION_V1
FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE = "formal_document_alignment_workflow_v1"
FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1 = 3
FORMAL_DOCUMENT_ALIGNMENT_MAX_REQUEUES_V1 = FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1 - 1

ROOT_STATUS_QUEUED = "queued"
ROOT_STATUS_VALIDATING = "validating"
ROOT_STATUS_PROCESSING = "processing"
ROOT_STATUS_READY_FOR_REVIEW = "ready_for_review"
ROOT_STATUS_COMPLETED_WITH_WARNINGS = "completed_with_warnings"
ROOT_STATUS_BLOCKED = "blocked"
ROOT_STATUS_FAILED = "failed"

DOCUMENT_ALIGNMENT_WORKFLOW_STATUSES = frozenset({
    ROOT_STATUS_QUEUED,
    ROOT_STATUS_VALIDATING,
    ROOT_STATUS_PROCESSING,
    ROOT_STATUS_READY_FOR_REVIEW,
    ROOT_STATUS_COMPLETED_WITH_WARNINGS,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_FAILED,
})

ROOT_STAGE_QUEUED = "queued"
ROOT_STAGE_SOURCE_VALIDATION = "source_validation"
ROOT_STAGE_TERM_EXTRACTION = "term_extraction"
ROOT_STAGE_EVIDENCE_RETRIEVAL = "evidence_retrieval"
ROOT_STAGE_DRAFT_CREATION = "draft_creation"
ROOT_STAGE_VERIFICATION = "verification"
ROOT_STAGE_FINALIZATION = "finalization"
ROOT_STAGE_TERMINAL = "terminal"

DOCUMENT_ALIGNMENT_WORKFLOW_STAGES = frozenset({
    ROOT_STAGE_QUEUED,
    ROOT_STAGE_SOURCE_VALIDATION,
    ROOT_STAGE_TERM_EXTRACTION,
    ROOT_STAGE_EVIDENCE_RETRIEVAL,
    ROOT_STAGE_DRAFT_CREATION,
    ROOT_STAGE_VERIFICATION,
    ROOT_STAGE_FINALIZATION,
    ROOT_STAGE_TERMINAL,
})

ITEM_STATUS_CANDIDATE = "candidate"
ITEM_STATUS_EVIDENCE_READY = "evidence_ready"
ITEM_STATUS_DRAFT_CREATED = "draft_created"
ITEM_STATUS_VERIFICATION_COMPLETED = "verification_completed"
ITEM_STATUS_NEEDS_REVIEW = "needs_review"
ITEM_STATUS_BLOCKED = "blocked"
ITEM_STATUS_FAILED = "failed"

DOCUMENT_ALIGNMENT_ITEM_STATUSES = frozenset({
    ITEM_STATUS_CANDIDATE,
    ITEM_STATUS_EVIDENCE_READY,
    ITEM_STATUS_DRAFT_CREATED,
    ITEM_STATUS_VERIFICATION_COMPLETED,
    ITEM_STATUS_NEEDS_REVIEW,
    ITEM_STATUS_BLOCKED,
    ITEM_STATUS_FAILED,
})

ITEM_STAGE_CANDIDATE = "candidate"
ITEM_STAGE_EVIDENCE_RETRIEVAL = "evidence_retrieval"
ITEM_STAGE_DRAFT_CREATION = "draft_creation"
ITEM_STAGE_VERIFICATION = "verification"
ITEM_STAGE_TERMINAL = "terminal"

DOCUMENT_ALIGNMENT_ITEM_STAGES = frozenset({
    ITEM_STAGE_CANDIDATE,
    ITEM_STAGE_EVIDENCE_RETRIEVAL,
    ITEM_STAGE_DRAFT_CREATION,
    ITEM_STAGE_VERIFICATION,
    ITEM_STAGE_TERMINAL,
})

DOCUMENT_ALIGNMENT_ITEM_KEY_VERSION = "item-key-v1"

FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION = "item-verification-execution-v1"

ITEM_VERIFICATION_EXECUTION_STATUS_PREPARED = "prepared"
ITEM_VERIFICATION_EXECUTION_STATUS_DRAFT_READY = "draft_ready"
ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_PASSED = "preflight_passed"
ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_BLOCKED = "preflight_blocked"
ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_STARTED = "provider_started"
ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_COMPLETED = "provider_completed"
ITEM_VERIFICATION_EXECUTION_STATUS_VERIFICATION_PERSISTED = "verification_persisted"
ITEM_VERIFICATION_EXECUTION_STATUS_ATTACH_PENDING = "attach_pending"
ITEM_VERIFICATION_EXECUTION_STATUS_ATTACHED = "attached"
ITEM_VERIFICATION_EXECUTION_STATUS_NEEDS_REVIEW = "needs_review"
ITEM_VERIFICATION_EXECUTION_STATUS_BLOCKED = "blocked"
ITEM_VERIFICATION_EXECUTION_STATUS_FAILED = "failed"

DOCUMENT_ALIGNMENT_ITEM_VERIFICATION_EXECUTION_STATUSES = frozenset({
    ITEM_VERIFICATION_EXECUTION_STATUS_PREPARED,
    ITEM_VERIFICATION_EXECUTION_STATUS_DRAFT_READY,
    ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_PASSED,
    ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_BLOCKED,
    ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_STARTED,
    ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_COMPLETED,
    ITEM_VERIFICATION_EXECUTION_STATUS_VERIFICATION_PERSISTED,
    ITEM_VERIFICATION_EXECUTION_STATUS_ATTACH_PENDING,
    ITEM_VERIFICATION_EXECUTION_STATUS_ATTACHED,
    ITEM_VERIFICATION_EXECUTION_STATUS_NEEDS_REVIEW,
    ITEM_VERIFICATION_EXECUTION_STATUS_BLOCKED,
    ITEM_VERIFICATION_EXECUTION_STATUS_FAILED,
})


def _normalize_item_key_term(normalized_term):
    text = unicodedata.normalize("NFKC", str(normalized_term or "")).strip()
    text = re.sub(r"\s+", " ", text).casefold()
    if not text:
        raise ValueError("normalized_term is required.")
    return text


def _normalize_chunk_ids(source_chunk_ids):
    chunk_ids = []
    for value in source_chunk_ids or []:
        text = str(value or "").strip()
        if text:
            chunk_ids.append(text)
    chunk_ids = sorted(set(chunk_ids))
    if not chunk_ids:
        raise ValueError("source_chunk_ids are required.")
    return chunk_ids


def build_document_alignment_item_key(normalized_term, source_chunk_ids):
    """Build a deterministic, scope-aware workflow item key.

    The key intentionally stores only a version prefix and digest. Raw terms,
    raw chunk text, and ordered chunk lists do not appear in the key.
    """
    payload = {
        "version": DOCUMENT_ALIGNMENT_ITEM_KEY_VERSION,
        "normalized_term": _normalize_item_key_term(normalized_term),
        "source_chunk_ids": _normalize_chunk_ids(source_chunk_ids),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{DOCUMENT_ALIGNMENT_ITEM_KEY_VERSION}:{digest}"
