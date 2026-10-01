import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable

from services.document_alignment_workflow_contract import (
    FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION,
)

FORMAL_ITEM_VERIFICATION_INPUT_FINGERPRINT_VERSION = "item-verification-input-v1"
FORMAL_ITEM_AUDIT_EVENT_IDENTITY_VERSION = "item-audit-event-v1"

_SAFE_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalized_text(value: str, *, field: str, casefold: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if casefold:
        normalized = normalized.casefold()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _normalized_values(values: Iterable[str], *, field: str) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field} must be a collection")
    try:
        normalized = {
            _normalized_text(value, field=field)
            for value in values
        }
    except TypeError:
        raise
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return sorted(normalized)


def _normalized_refs(values: Iterable[str], *, field: str) -> list[str]:
    normalized = _normalized_values(values, field=field)
    if any(any(character.isspace() for character in value) for value in normalized):
        raise ValueError(f"{field} must contain reference IDs, not text bodies")
    if any(len(value) > 300 for value in normalized):
        raise ValueError(f"{field} contains an oversized reference ID")
    return normalized


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_formal_item_verification_input_fingerprint(
    *,
    workflow_run_uid: str,
    workflow_item_uid: str,
    workflow_item_key: str,
    english_term: str,
    chinese_candidate_values: Iterable[str],
    chinese_candidate_provenance_refs: Iterable[str],
    english_evidence_refs: Iterable[str],
    chinese_evidence_refs: Iterable[str],
    source_uid: str,
    source_version: str,
    course: str,
    chapter: str,
    retrieval_version: str,
    evidence_qualification_result_id: str = "",
    evidence_qualification_policy: str = "",
) -> str:
    payload = {
        "version": FORMAL_ITEM_VERIFICATION_INPUT_FINGERPRINT_VERSION,
        "workflow_run_uid": _normalized_text(workflow_run_uid, field="workflow_run_uid"),
        "workflow_item_uid": _normalized_text(workflow_item_uid, field="workflow_item_uid"),
        "workflow_item_key": _normalized_text(workflow_item_key, field="workflow_item_key"),
        "english_term": _normalized_text(english_term, field="english_term", casefold=True),
        "chinese_candidate_values": _normalized_values(
            chinese_candidate_values,
            field="chinese_candidate_values",
        ),
        "chinese_candidate_provenance_refs": _normalized_refs(
            chinese_candidate_provenance_refs,
            field="chinese_candidate_provenance_refs",
        ),
        "english_evidence_refs": _normalized_refs(
            english_evidence_refs,
            field="english_evidence_refs",
        ),
        "chinese_evidence_refs": _normalized_refs(
            chinese_evidence_refs,
            field="chinese_evidence_refs",
        ),
        "source_uid": _normalized_text(source_uid, field="source_uid"),
        "source_version": _normalized_text(source_version, field="source_version"),
        "course": _normalized_text(course, field="course"),
        "chapter": _normalized_text(chapter, field="chapter"),
        "retrieval_version": _normalized_text(retrieval_version, field="retrieval_version"),
    }
    if evidence_qualification_result_id:
        payload["evidence_qualification_result_id"] = _normalized_text(
            evidence_qualification_result_id,
            field="evidence_qualification_result_id",
        )
        payload["evidence_qualification_policy"] = _normalized_text(
            evidence_qualification_policy,
            field="evidence_qualification_policy",
        )
    return _digest(payload)


def build_formal_item_verification_execution_key(
    *,
    workflow_run_uid: str,
    workflow_item_uid: str,
    workflow_item_key: str,
    workflow_version: str,
    safe_input_fingerprint: str,
    provider_name: str,
    model_identity: str,
    retrieval_version: str,
    prompt_version: str,
    parser_version: str,
    output_schema_version: str,
) -> str:
    if not isinstance(safe_input_fingerprint, str) or not _SAFE_FINGERPRINT_RE.fullmatch(
        safe_input_fingerprint
    ):
        raise ValueError("safe_input_fingerprint must be a lowercase SHA-256 digest")
    digest = _digest(
        {
            "version": FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION,
            "workflow_run_uid": _normalized_text(workflow_run_uid, field="workflow_run_uid"),
            "workflow_item_uid": _normalized_text(workflow_item_uid, field="workflow_item_uid"),
            "workflow_item_key": _normalized_text(workflow_item_key, field="workflow_item_key"),
            "workflow_version": _normalized_text(workflow_version, field="workflow_version"),
            "safe_input_fingerprint": safe_input_fingerprint,
            "provider_name": _normalized_text(provider_name, field="provider_name"),
            "model_identity": _normalized_text(model_identity, field="model_identity"),
            "retrieval_version": _normalized_text(retrieval_version, field="retrieval_version"),
            "prompt_version": _normalized_text(prompt_version, field="prompt_version"),
            "parser_version": _normalized_text(parser_version, field="parser_version"),
            "output_schema_version": _normalized_text(
                output_schema_version,
                field="output_schema_version",
            ),
        }
    )
    return f"{FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION}:{digest}"


def build_formal_item_audit_event_identity(execution_key: str, event_type: str) -> str:
    digest = _digest(
        {
            "version": FORMAL_ITEM_AUDIT_EVENT_IDENTITY_VERSION,
            "execution_key": _normalized_text(execution_key, field="execution_key"),
            "event_type": _normalized_text(event_type, field="event_type"),
        }
    )
    return f"{FORMAL_ITEM_AUDIT_EVENT_IDENTITY_VERSION}:{digest}"
