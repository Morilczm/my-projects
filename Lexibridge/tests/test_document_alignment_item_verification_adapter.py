import ast
import dataclasses
import inspect

import pytest

from services import alignment_verification
from services import concept_card_drafts
from services import document_alignment_item_verification_adapter as adapter


def _prepared_input(**overrides):
    values = {
        "workflow_run_uid": "formal-run-1",
        "workflow_item_uid": "formal-item-1",
        "workflow_item_key": "item-key-v1:formal-item-1",
        "english_term": "Fourier transform",
        "chinese_candidate_values": ("傅里叶变换",),
        "chinese_candidate_provenance_refs": ("candidate-ref-1",),
        "english_evidence_refs": ("chunk-en-1",),
        "chinese_evidence_refs": ("chunk-zh-1",),
        "english_snippets": (
            adapter.PreparedEvidenceSnippet("chunk-en-1", "Bounded English evidence."),
        ),
        "chinese_snippets": (
            adapter.PreparedEvidenceSnippet("chunk-zh-1", "有界中文证据。"),
        ),
        "source_uid": "source-1",
        "source_version": "1",
        "course": "Signals",
        "chapter": "Frequency",
        "workflow_version": "formal-document-alignment-v1",
        "retrieval_version": "governed-bilingual-v1",
        "provider_name": "mock-rule-v1",
        "model_identity": "mock-rule-v1:v1",
        "prompt_version": "alignment-verification-v1",
        "parser_version": "alignment-output-parser-v1",
        "output_schema_version": "alignment-output-v1",
        "risk_labels": ("bilingual_alignment_not_verified",),
    }
    values.update(overrides)
    return adapter.PreparedFormalItemVerificationInput(**values)


def test_adapter_module_boundary_and_frozen_contracts():
    source = inspect.getsource(adapter)
    tree = ast.parse(source)
    imported_roots = {
        node.module.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_roots.update(
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert "flask" not in imported_roots
    assert "backend" not in imported_roots
    assert "routes" not in imported_roots
    assert "os" not in imported_roots

    prepared = _prepared_input()
    command = adapter.ExecuteDocumentAlignmentItemVerificationCommand(
        workflow_run_uid=prepared.workflow_run_uid,
        workflow_item_uid=prepared.workflow_item_uid,
        job_uid="formal-job-1",
        worker_id="worker-1",
        execution_attempt=1,
        lease_token="LEXIBRIDGE_SENTINEL_SECRET_9C5B_V2_LEASE",
        prepared_input=prepared,
    )
    assert dataclasses.is_dataclass(prepared)
    assert dataclasses.is_dataclass(command)
    assert dataclasses.is_dataclass(adapter.ExecuteDocumentAlignmentItemVerificationResult)
    assert adapter.DocumentAlignmentItemVerificationModels.__dataclass_params__.frozen is True
    assert adapter.DraftVerificationCollaborator.__dataclass_params__.frozen is True
    assert adapter.ProviderGovernanceCollaborator.__dataclass_params__.frozen is True
    assert adapter.VerificationCollaborator.__dataclass_params__.frozen is True
    assert adapter.RecordingCollaborator.__dataclass_params__.frozen is True
    assert adapter.DocumentAlignmentItemVerificationDependencies.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        command.worker_id = "other-worker"
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5B_V2_LEASE" not in repr(command)


def test_internal_draft_and_verification_helpers_are_transaction_neutral():
    draft_source = inspect.getsource(
        concept_card_drafts.create_or_reuse_prepared_concept_card_draft
    )
    verification_source = inspect.getsource(
        alignment_verification.create_safe_alignment_verification_run
    )
    protected_attach_source = inspect.getsource(
        alignment_verification.apply_verification_result_to_card_protected
    )
    for source in (draft_source, verification_source, protected_attach_source):
        assert ".commit(" not in source
        assert ".rollback(" not in source
        assert "session.flush()" in source


def test_prepared_input_is_normalized_bounded_and_does_not_expose_snippets_in_repr():
    prepared = _prepared_input(
        english_term="  Fourier\u3000transform  ",
        chinese_candidate_values=(" 傅里叶变换 ", "傅里叶变换"),
        risk_labels=("risk-b", "risk-a", "risk-a"),
    )
    assert prepared.english_term == "Fourier transform"
    assert prepared.chinese_candidate_values == ("傅里叶变换",)
    assert prepared.risk_labels == ("risk-a", "risk-b")
    assert "Bounded English evidence" not in repr(prepared)

    with pytest.raises(ValueError, match="bounded"):
        _prepared_input(
            english_snippets=(
                adapter.PreparedEvidenceSnippet("chunk-en-1", "x" * 501),
            )
        )

    with pytest.raises(ValueError, match="one selected Chinese candidate"):
        _prepared_input(
            chinese_candidate_values=("傅里叶变换", "傅里叶转换"),
            chinese_candidate_provenance_refs=("candidate-ref-1", "candidate-ref-2"),
        )


def test_result_contains_only_safe_typed_state():
    field_names = {
        field.name for field in dataclasses.fields(adapter.ExecuteDocumentAlignmentItemVerificationResult)
    }
    assert {
        "outcome",
        "workflow_run_uid",
        "workflow_item_uid",
        "execution_key",
        "execution_status",
        "item_status",
        "draft_card_uid",
        "preflight_run_uid",
        "verification_run_uid",
        "provider_executed",
        "usage_recorded",
        "audit_events_created",
        "retryable",
        "error_code",
        "error_message",
    } <= field_names
    assert not {
        "raw_prompt",
        "raw_evidence",
        "raw_output",
        "credential",
        "lease_token",
        "orm_object",
    } & field_names
