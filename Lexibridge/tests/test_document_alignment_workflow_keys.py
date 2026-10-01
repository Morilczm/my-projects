import json

import pytest

from services.document_alignment_workflow_contract import (
    DOCUMENT_ALIGNMENT_ITEM_KEY_VERSION,
    build_document_alignment_item_key,
)
from services.document_alignment_workflow_application import (
    build_document_alignment_idempotency_fingerprint,
)


def _fingerprint(**overrides):
    payload = {
        "source_uid": "source-a",
        "parse_uid": "parse-a",
        "source_version": "1",
        "course": "Signals",
        "chapter": "Frequency",
        "workflow_version": "formal-document-alignment-v1",
        "request_id": "request-a",
        "idempotency_key": "key-a",
    }
    payload.update(overrides)
    return build_document_alignment_idempotency_fingerprint(**payload)


def test_idempotency_fingerprint_is_stable_and_excludes_request_scope_noise():
    first = _fingerprint()
    second = _fingerprint(request_id="request-b", idempotency_key="key-b")

    assert first == second
    assert len(first) == 64
    assert first != str(hash(json.dumps({"source_uid": "source-a"})))


def test_idempotency_fingerprint_changes_only_for_canonical_payload_fields():
    baseline = _fingerprint()

    assert _fingerprint(source_uid="source-b") != baseline
    assert _fingerprint(parse_uid="parse-b") != baseline
    assert _fingerprint(source_version="2") != baseline
    assert _fingerprint(course="Control") != baseline
    assert _fingerprint(chapter="Time") != baseline
    assert _fingerprint(workflow_version="formal-document-alignment-v2") != baseline


def test_item_key_is_deterministic_and_canonicalizes_term_and_chunk_scope():
    key = build_document_alignment_item_key("  Laplace   Transform ", ["chunk-b", "chunk-a", "chunk-a"])

    assert key == build_document_alignment_item_key("laplace transform", ["chunk-a", "chunk-b"])
    assert key == build_document_alignment_item_key("LAPLACE TRANSFORM", [" chunk-b ", "", "chunk-a"])
    assert key.startswith(f"{DOCUMENT_ALIGNMENT_ITEM_KEY_VERSION}:")
    assert "Laplace" not in key
    assert "chunk-a" not in key


def test_item_key_handles_unicode_nfkc_and_rejects_empty_inputs():
    assert build_document_alignment_item_key("Ｆｏｕｒｉｅｒ", ["chunk-a"]) == build_document_alignment_item_key(
        "fourier",
        ["chunk-a"],
    )
    assert build_document_alignment_item_key("fourier", ["chunk-a"]) != build_document_alignment_item_key(
        "laplace",
        ["chunk-a"],
    )
    assert build_document_alignment_item_key("fourier", ["chunk-a"]) != build_document_alignment_item_key(
        "fourier",
        ["chunk-b"],
    )

    with pytest.raises(ValueError):
        build_document_alignment_item_key("   ", ["chunk-a"])
    with pytest.raises(ValueError):
        build_document_alignment_item_key("fourier", ["", "  "])
