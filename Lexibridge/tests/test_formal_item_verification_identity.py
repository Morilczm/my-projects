import inspect
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _fingerprint(**overrides):
    from services.formal_item_verification_identity import (
        build_formal_item_verification_input_fingerprint,
    )

    payload = {
        "workflow_run_uid": "workflow-run-identity",
        "workflow_item_uid": "workflow-item-identity",
        "workflow_item_key": "item-key-v1:abc123",
        "english_term": " Fourier   Transform ",
        "chinese_candidate_values": ["傅里叶变换"],
        "chinese_candidate_provenance_refs": ["candidate:zh:1"],
        "english_evidence_refs": ["chunk:en:2", "chunk:en:1"],
        "chinese_evidence_refs": ["chunk:zh:1"],
        "source_uid": "source-identity",
        "source_version": "source-v1",
        "course": "Signals",
        "chapter": "Frequency",
        "retrieval_version": "retrieval-v1",
    }
    payload.update(overrides)
    return build_formal_item_verification_input_fingerprint(**payload)


def _execution_key(**overrides):
    from services.formal_item_verification_identity import (
        build_formal_item_verification_execution_key,
    )

    payload = {
        "workflow_run_uid": "workflow-run-identity",
        "workflow_item_uid": "workflow-item-identity",
        "workflow_item_key": "item-key-v1:abc123",
        "workflow_version": "formal-document-alignment-v1",
        "safe_input_fingerprint": _fingerprint(),
        "provider_name": "replay-llm-v1",
        "model_identity": "replay-model-v1",
        "retrieval_version": "retrieval-v1",
        "prompt_version": "prompt-v1",
        "parser_version": "parser-v1",
        "output_schema_version": "alignment-output-v1",
    }
    payload.update(overrides)
    return build_formal_item_verification_execution_key(**payload)


def test_identity_module_is_pure_and_has_no_runtime_or_transport_dependencies():
    source = (
        ROOT / "backend" / "services" / "formal_item_verification_identity.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "from flask",
        "import flask",
        "backend.app",
        "os.environ",
        "urllib",
        "requests",
        "httpx",
        "socket",
    ):
        assert forbidden not in source


def test_safe_input_fingerprint_is_deterministic_and_normalizes_reference_order():
    first = _fingerprint()
    second = _fingerprint(
        english_term="Fourier Transform",
        english_evidence_refs=["chunk:en:1", "chunk:en:2", "chunk:en:1"],
    )

    assert first == second
    assert len(first) == 64
    assert "Fourier" not in first
    assert "chunk:en:1" not in first


def test_identity_functions_exclude_request_worker_attempt_lease_time_and_raw_payload_parameters():
    from services import formal_item_verification_identity as identity

    fingerprint_parameters = inspect.signature(
        identity.build_formal_item_verification_input_fingerprint
    ).parameters
    execution_parameters = inspect.signature(
        identity.build_formal_item_verification_execution_key
    ).parameters
    forbidden = {
        "request_id",
        "worker_id",
        "execution_attempt",
        "lease_token",
        "timestamp",
        "evidence_body",
        "prompt",
        "provider_output",
        "credential",
    }

    assert forbidden.isdisjoint(fingerprint_parameters)
    assert forbidden.isdisjoint(execution_parameters)
    with pytest.raises((TypeError, ValueError)):
        _fingerprint(english_evidence_refs=[{"chunk_uid": "chunk:en:1", "snippet": "raw evidence"}])
    with pytest.raises((TypeError, ValueError)):
        _fingerprint(english_evidence_refs=["Raw evidence sentence must not be an identity reference."])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_item_uid", "workflow-item-other"),
        ("workflow_item_key", "item-key-v1:other"),
        ("english_evidence_refs", ["chunk:en:other"]),
        ("chinese_candidate_provenance_refs", ["candidate:zh:other"]),
        ("source_version", "source-v2"),
        ("retrieval_version", "retrieval-v2"),
    ],
)
def test_safe_input_fingerprint_changes_for_canonical_input_fields(field, value):
    assert _fingerprint(**{field: value}) != _fingerprint()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_item_uid", "workflow-item-other"),
        ("workflow_item_key", "item-key-v1:other"),
        ("safe_input_fingerprint", "f" * 64),
        ("provider_name", "fake-llm-v1"),
        ("model_identity", "model-v2"),
        ("retrieval_version", "retrieval-v2"),
        ("prompt_version", "prompt-v2"),
        ("parser_version", "parser-v2"),
        ("output_schema_version", "alignment-output-v2"),
    ],
)
def test_execution_key_changes_for_execution_identity_fields(field, value):
    assert _execution_key(**{field: value}) != _execution_key()


def test_execution_key_and_audit_event_identity_are_versioned_safe_digests():
    from services.formal_item_verification_identity import (
        FORMAL_ITEM_AUDIT_EVENT_IDENTITY_VERSION,
        FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION,
        build_formal_item_audit_event_identity,
    )

    execution_key = _execution_key()
    requested = build_formal_item_audit_event_identity(
        execution_key,
        "item_verification_requested",
    )
    requested_repeat = build_formal_item_audit_event_identity(
        execution_key,
        "item_verification_requested",
    )
    attached = build_formal_item_audit_event_identity(
        execution_key,
        "item_verification_attached",
    )

    assert execution_key.startswith(f"{FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION}:")
    assert requested.startswith(f"{FORMAL_ITEM_AUDIT_EVENT_IDENTITY_VERSION}:")
    assert requested == requested_repeat
    assert requested != attached
    assert "item_verification_requested" not in requested
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5B1" not in requested
