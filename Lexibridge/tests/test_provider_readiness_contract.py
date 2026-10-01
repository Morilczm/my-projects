from dataclasses import replace

from services import provider_readiness as readiness
from services.document_alignment_item_verification_adapter import (
    PreparedEvidenceSnippet,
    PreparedFormalItemVerificationInput,
)


def _input(**overrides):
    values = {
        "qualification_decision": "QUALIFIED",
        "qualification_policy": "governed-bilingual-evidence-qualification@1.1.0",
        "qualification_result_id": "qualification:" + "a" * 64,
        "qualification_score": 0.91,
        "qualification_reason_codes": (),
        "qualification_risk_labels": (),
        "english_term": "electric potential",
        "chinese_term": "电势",
        "english_evidence_refs": ("en-source:en-chunk:0:20",),
        "chinese_evidence_refs": ("zh-source:zh-chunk:0:8",),
        "pair_rank": 1,
        "pair_score": 0.88,
        "pair_model_metadata_complete": True,
        "provider_id": "mock-rule-v1",
        "provider_policy_id": "formal-provider-policy@1.0.0",
        "provider_allowed": True,
        "provider_config_complete": True,
        "credential_reference_configured": True,
        "prompt_registry_id": "term_alignment",
        "prompt_version": "v1",
        "prompt_approved": True,
        "privacy_classification": "SYNTHETIC",
        "privacy_gate_passed": True,
        "provenance_gate_passed": True,
        "source_governance_passed": True,
        "request_token_budget": 1200,
        "cost_ceiling": 0.05,
        "retry_budget": 0,
        "timeout_seconds": 30,
        "idempotency_key": "formal-readiness-item-1",
        "audit_context": "formal_workflow",
    }
    values.update(overrides)
    return readiness.ProviderReadinessInput(**values)


def test_qualified_complete_input_is_ready_and_deterministic():
    first = readiness.evaluate_provider_readiness(_input())
    second = readiness.evaluate_provider_readiness(_input())
    assert first.decision == readiness.READY
    assert first == second
    assert first.execution_admission is True
    assert first.readiness_id.startswith("provider-readiness:")


def test_review_rejected_missing_and_old_policy_never_ready():
    cases = (
        replace(_input(), qualification_decision="REVIEW_REQUIRED"),
        replace(_input(), qualification_decision="REJECTED"),
        replace(_input(), qualification_decision=""),
        replace(
            _input(),
            qualification_policy="governed-bilingual-evidence-qualification@1.0.0",
        ),
    )
    results = [readiness.evaluate_provider_readiness(value) for value in cases]
    assert results[0].decision == readiness.REVIEW_REQUIRED
    assert all(result.decision != readiness.READY for result in results)
    assert all(result.reason_codes for result in results)


def test_readiness_does_not_replace_top1_or_accept_incomplete_pair():
    result = readiness.evaluate_provider_readiness(_input(pair_rank=2))
    assert result.decision == readiness.NOT_READY
    assert readiness.PROVIDER_READINESS_QUALIFICATION_NOT_APPROVED in result.reason_codes


def test_formal_adapter_uses_server_owned_local_configuration_without_credentials():
    class Query:
        def filter_by(self, **_values):
            return self

        def first(self):
            return None

    class Session:
        def query(self, _model):
            return Query()

    prepared = PreparedFormalItemVerificationInput(
        workflow_run_uid="run-1",
        workflow_item_uid="item-1",
        workflow_item_key="key-1",
        english_term="electric potential",
        chinese_candidate_values=("电势",),
        chinese_candidate_provenance_refs=("candidate-1",),
        english_evidence_refs=("en-chunk",),
        chinese_evidence_refs=("zh-chunk",),
        english_snippets=(PreparedEvidenceSnippet("en-chunk", "Bounded evidence."),),
        chinese_snippets=(PreparedEvidenceSnippet("zh-chunk", "有界中文证据。"),),
        source_uid="source-1",
        source_version="v1",
        course="physics",
        chapter="fields",
        workflow_version="v1",
        retrieval_version="v1",
        provider_name="mock-rule-v1",
        model_identity="mock-rule-v1:v1",
        prompt_version="alignment-v1",
        parser_version="v1",
        output_schema_version="v1",
        evidence_qualification_result_id="qualification:" + "a" * 64,
        evidence_qualification_decision="QUALIFIED",
        evidence_qualification_policy=readiness.ACTIVE_QUALIFICATION_POLICY,
    )
    result = readiness.evaluate_formal_prepared_readiness(
        prepared,
        session=Session(),
        policy_model=object,
        execution_key="formal-execution-key",
    )
    assert result.decision == readiness.READY
    assert result.network_called is False
    assert result.credential_value_read is False
