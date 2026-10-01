import dataclasses

import pytest

from services import controlled_provider_evaluation as cpe


def test_input_contract_is_frozen_and_fingerprinted():
    item = cpe.build_evaluation_input({
        "evaluation_item_uid": "eval-item-001",
        "course_or_domain": "signals",
        "english_term": "impulse response",
        "normalized_english_term": "impulse response",
        "bounded_context": "The impulse response characterizes an LTI system.",
        "context_source_type": "synthetic_fixture",
        "privacy_classification": "SYNTHETIC",
    })

    assert item.privacy_classification == "SYNTHETIC"
    assert item.input_fingerprint.startswith("sha256:")
    assert len(item.input_fingerprint) == len("sha256:") + 64
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.english_term = "mutated"


def test_provider_proposal_is_not_document_evidence_or_auto_approval():
    proposal = cpe.parse_provider_proposal(
        '{"chinese_term":"冲激响应","chinese_explanation":"系统对冲激输入的响应。",'
        '"alignment_rationale":"The term is a standard signals concept.",'
        '"alternative_candidates":[],"risk_labels":["provider_generated_candidate"],'
        '"abstain":false,"abstain_reason":"","provider_name":"loopback-provider",'
        '"model_name":"candidate-model","prompt_version":"provider-chinese-candidate-evaluation-v1",'
        '"output_schema_version":"provider-chinese-candidate-proposal-v1"}',
        expected_provider="loopback-provider",
        expected_model="candidate-model",
    )
    result = cpe.build_success_result(
        item=cpe.build_evaluation_input({
            "evaluation_item_uid": "eval-item-002",
            "course_or_domain": "signals",
            "english_term": "impulse response",
            "normalized_english_term": "impulse response",
            "bounded_context": "Synthetic bounded context.",
            "context_source_type": "synthetic_fixture",
            "privacy_classification": "SYNTHETIC",
        }),
        proposal=proposal,
        latency_ms=12,
        input_tokens=18,
        output_tokens=22,
        estimated_cost=0.0003,
        retry_count=0,
        request_count=1,
    )

    assert proposal.proposal_kind == "provider_generated_proposal"
    assert proposal.evidence_kind != "document_explicit_evidence"
    assert result.status == "SUCCEEDED"
    assert result.can_auto_approve is False
    assert result.writes_document_evidence is False
    assert result.writes_concept_card is False


def test_abstain_contract_allows_empty_chinese_term_with_reason():
    proposal = cpe.parse_provider_proposal(
        '{"chinese_term":"","chinese_explanation":"","alignment_rationale":"Input is too ambiguous.",'
        '"alternative_candidates":[],"risk_labels":["ambiguous_without_context"],'
        '"abstain":true,"abstain_reason":"ambiguous_without_context",'
        '"provider_name":"loopback-provider","model_name":"candidate-model",'
        '"prompt_version":"provider-chinese-candidate-evaluation-v1",'
        '"output_schema_version":"provider-chinese-candidate-proposal-v1"}',
        expected_provider="loopback-provider",
        expected_model="candidate-model",
    )

    assert proposal.abstain is True
    assert proposal.chinese_term == ""
    assert proposal.abstain_reason == "ambiguous_without_context"
