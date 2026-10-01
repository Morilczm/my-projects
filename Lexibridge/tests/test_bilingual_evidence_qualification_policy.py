from dataclasses import replace

from services import bilingual_evidence_qualification as qualification
from test_bilingual_evidence_qualification_contract import _input
from services.document_alignment_item_verification_adapter import (
    PreparedEvidenceSnippet,
    PreparedFormalItemVerificationInput,
)


def test_source_language_status_and_independence_are_hard_gates():
    withdrawn = qualification.qualify_bilingual_evidence(
        _input(chinese_source_status="withdrawn")
    )
    wrong_language = qualification.qualify_bilingual_evidence(
        _input(chinese_source_language="en")
    )
    same_source = qualification.qualify_bilingual_evidence(
        _input(chinese_source_uid="en-source-1")
    )
    assert qualification.EVIDENCE_SOURCE_NOT_ELIGIBLE in withdrawn.reason_codes
    assert qualification.EVIDENCE_LANGUAGE_SCOPE_INVALID in wrong_language.reason_codes
    assert qualification.EVIDENCE_LANGUAGE_SCOPE_INVALID in same_source.reason_codes
    assert all(result.decision == qualification.REJECTED for result in (withdrawn, wrong_language, same_source))


def test_existing_governed_bilingual_source_policy_is_not_globally_forbidden():
    result = qualification.qualify_bilingual_evidence(_input(
        chinese_source_uid="en-source-1",
        english_source_language="mixed",
        chinese_source_language="mixed",
        english_source_role="bilingual_reference",
        chinese_source_role="bilingual_reference",
        require_independent_sources=False,
    ))
    assert qualification.EVIDENCE_LANGUAGE_SCOPE_INVALID not in result.reason_codes


def test_missing_provenance_and_context_fail_closed():
    incomplete = qualification.qualify_bilingual_evidence(
        replace(_input(), english_chunk_uid="")
    )
    context = qualification.qualify_bilingual_evidence(
        replace(_input(), chinese_context="")
    )
    assert qualification.EVIDENCE_PROVENANCE_INCOMPLETE in incomplete.reason_codes
    assert qualification.EVIDENCE_CONTEXT_INSUFFICIENT in context.reason_codes


def test_score_components_and_policy_thresholds_are_auditable():
    result = qualification.qualify_bilingual_evidence(_input())
    assert set(result.score_components) >= {
        "english_span_validity",
        "chinese_span_validity",
        "provenance_completeness",
        "source_governance",
        "pair_semantic_score",
        "pair_margin_score",
        "retrieval_support",
        "extraction_support",
    }
    assert result.thresholds == qualification.policy_manifest()["thresholds"]


def test_qualified_result_is_carried_into_formal_readiness_input():
    prepared = PreparedFormalItemVerificationInput(
        workflow_run_uid="run-1", workflow_item_uid="item-1",
        workflow_item_key="item-key", english_term="electric potential",
        chinese_candidate_values=("电势",),
        chinese_candidate_provenance_refs=("candidate-1",),
        english_evidence_refs=("en-ref",), chinese_evidence_refs=("zh-ref",),
        english_snippets=(PreparedEvidenceSnippet("en-ref", "English evidence"),),
        chinese_snippets=(PreparedEvidenceSnippet("zh-ref", "中文证据"),),
        source_uid="source-1", source_version="v1", course="physics",
        chapter="fields", workflow_version="v1", retrieval_version="v1",
        provider_name="mock", model_identity="mock", prompt_version="v1",
        parser_version="v1", output_schema_version="v1",
        evidence_qualification_result_id="evidence-qualification:" + "a" * 64,
        evidence_qualification_decision=qualification.QUALIFIED,
        evidence_qualification_policy=f"{qualification.POLICY_ID}@{qualification.POLICY_VERSION}",
    )
    assert prepared.evidence_qualification_decision == qualification.QUALIFIED
