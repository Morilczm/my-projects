import json
import uuid

import pytest

from services import alignment_output_parser
from services import alignment_prompting
from services import alignment_providers
from services import alignment_verification
from services import audit_records
from services import concept_alignment_cards


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="FakeLLM"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def evidence_item(term, *, language="en", score=0.72, **overrides):
    return {
        "chunk_uid": overrides.get("chunk_uid", f"chunk-{uuid.uuid4().hex}"),
        "source_uid": overrides.get("source_uid", f"src-{uuid.uuid4().hex}"),
        "source_title": overrides.get("source_title", f"{term} Source"),
        "course": overrides.get("course", "Fake LLM Course"),
        "chapter": overrides.get("chapter", "Verification"),
        "language": language,
        "source_role": overrides.get("source_role", "english_course_material" if language == "en" else "chinese_reference_material"),
        "trust_level": overrides.get("trust_level", "teacher_verified"),
        "quality_status": overrides.get("quality_status", "native_text_ok"),
        "quality_flags": overrides.get("quality_flags", ["native_text_ok"]),
        "source_locator": overrides.get("source_locator", "page:1"),
        "snippet": overrides.get("snippet", f"{term} short evidence snippet."),
        "score": score,
        "retrieval_reason": "test lexical evidence",
        "risk_labels": overrides.get("risk_labels", []),
        "parse_uid": overrides.get("parse_uid", f"parse-{uuid.uuid4().hex}"),
        "parse_block_uid": overrides.get("parse_block_uid", f"block-{uuid.uuid4().hex}"),
    }


def valid_payload():
    english_term = unique_token("Fourier")
    chinese_term = f"傅里叶{uuid.uuid4().hex[:6]}"
    return {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": "Fake LLM Course",
        "chapter": "Verification",
        "english_evidence": [evidence_item(english_term, language="en")],
        "chinese_evidence": [evidence_item(chinese_term, language="zh", score=0.68)],
        "candidate_info": {
            "candidate_uid": f"cand-{uuid.uuid4().hex}",
            "chinese_term": chinese_term,
            "score": 0.83,
            "risk_labels": ["candidate_not_alignment_verified"],
        },
        "risk_labels": ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
        "retrieval_version": "lexical-v1",
    }


def provider_json(**overrides):
    payload = {
        "alignment_decision": "likely_aligned",
        "alignment_confidence": 0.66,
        "recommendation": "ready_for_human_review",
        "risk_labels": ["candidate_not_alignment_verified"],
        "evidence_assessment": {
            "english_evidence_supported": True,
            "chinese_evidence_supported": True,
            "cross_language_support": "moderate",
            "evidence_limitations": [],
        },
        "term_assessment": {
            "english_term_ok": True,
            "chinese_term_ok": True,
            "candidate_ambiguity": "none",
            "notes": "fixture",
        },
        "course_context_assessment": {
            "course_match": True,
            "chapter_match": True,
            "notes": "fixture",
        },
        "explanation": "fixture explanation",
        "limitations": ["fake"],
        "auto_approve": True,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def create_concept_card(app_module, payload=None, **overrides):
    payload = payload or valid_payload()
    card = app_module.ConceptAlignmentCard(
        english_term=payload["english_term"],
        chinese_term=payload.get("chinese_term", ""),
        course=payload.get("course", "Fake LLM Course"),
        chapter=payload.get("chapter", "Verification"),
        english_evidence=payload.get("english_evidence", []),
        chinese_evidence=payload.get("chinese_evidence", []),
        risk_labels=payload.get("risk_labels", []),
        status=overrides.get("status", "draft"),
        confidence_score=overrides.get("confidence_score"),
        retrieval_version=payload.get("retrieval_version", "lexical-v1"),
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def test_provider_registry_exposes_only_non_production_providers():
    mock_provider = alignment_providers.get_alignment_provider("mock-rule-v1")
    fake_provider = alignment_providers.get_alignment_provider("fake-llm-v1")

    assert mock_provider.provider_type == "mock"
    assert fake_provider.provider_type == "fake_llm"
    assert fake_provider.supports_external_calls is False
    assert fake_provider.is_production_provider is False
    assert {"mock-rule-v1", "fake-llm-v1"} <= {item["provider_name"] for item in alignment_providers.list_alignment_providers()}
    with pytest.raises(alignment_providers.AlignmentProviderError):
        alignment_providers.get_alignment_provider("real-provider-not-enabled")


def test_alignment_prompt_is_versioned_json_only_and_redacts_sensitive_values():
    payload = valid_payload()
    payload["Authorization"] = "Bearer secret-token"
    payload["Cookie"] = "session=secret"
    payload["DEEPSEEK_API_KEY"] = "secret-key"
    payload["english_evidence"][0]["snippet"] = "x" * 700

    prompt = alignment_prompting.build_alignment_prompt(payload)

    assert "alignment-v1" in alignment_prompting.list_prompt_versions()
    assert "Output JSON only" in prompt
    assert "insufficient_evidence" in prompt
    assert "retrieval_score" in prompt
    assert "candidate_score" in prompt
    assert "alignment_confidence" in prompt
    assert "Authorization" not in prompt
    assert "Cookie" not in prompt
    assert "DEEPSEEK_API_KEY" not in prompt
    assert "secret-token" not in prompt
    assert "x" * 500 not in prompt


def test_alignment_output_parser_success_and_auto_approve_ignored():
    parsed = alignment_output_parser.parse_alignment_provider_output(
        provider_json(explanation="x" * 1500)
    )

    assert parsed["alignment_decision"] == "likely_aligned"
    assert parsed["alignment_confidence"] == 0.66
    assert parsed["can_auto_approve"] is False
    assert parsed["is_production_result"] is False
    assert "auto_approve" not in parsed
    assert len(parsed["explanation"]) <= 1003


@pytest.mark.parametrize(
    "raw_output",
    [
        "not-json",
        provider_json(recommendation="approved"),
        provider_json(alignment_decision="approved"),
        provider_json(alignment_confidence=-0.1),
        provider_json(alignment_confidence=1.3),
        provider_json(risk_labels="not-list"),
    ],
)
def test_alignment_output_parser_rejects_invalid_outputs(raw_output):
    with pytest.raises(alignment_output_parser.AlignmentOutputParserError):
        alignment_output_parser.parse_alignment_provider_output(raw_output)


def test_alignment_output_parser_rejects_missing_fields():
    raw = json.dumps({"alignment_confidence": 0.5, "risk_labels": []})

    with pytest.raises(alignment_output_parser.AlignmentOutputParserError):
        alignment_output_parser.parse_alignment_provider_output(raw)


@pytest.mark.parametrize(
    "fake_response_type, expected_status, expected_risk",
    [
        ("valid", "needs_review", "candidate_not_alignment_verified"),
        ("insufficient_evidence", "needs_review", "no_chinese_evidence"),
        ("ambiguous_candidate", "needs_review", "ambiguous_chinese_candidates"),
        ("non_json", "failed", "alignment_provider_output_invalid"),
        ("missing_fields", "failed", "alignment_provider_output_invalid"),
        ("confidence_out_of_range", "failed", "alignment_provider_output_invalid"),
    ],
)
def test_fake_llm_provider_fixture_paths(fake_response_type, expected_status, expected_risk):
    provider = alignment_providers.FakeLLMAlignmentProvider()
    payload = alignment_verification.validate_alignment_verification_input({
        **valid_payload(),
        "fake_response_type": fake_response_type,
    })

    output = provider.verify_alignment(payload)

    assert output["provider_name"] == "fake-llm-v1"
    assert output["provider_type"] == "fake_llm"
    assert output["verification_status"] == expected_status
    assert output["can_auto_approve"] is False
    assert output["is_production_result"] is False
    assert expected_risk in output["risk_labels"]
    assert output["prompt_version"] == alignment_prompting.PROMPT_VERSION
    assert output["parser_version"] == "alignment-parser-v1"
    assert output["output_schema_version"] == "alignment-output-v1"
    assert output["provider_response_status"] in {"parsed", "parse_failed"}


def test_verify_alignment_fake_provider_creates_run_with_prompt_metadata(app_module):
    with app_module.app.app_context():
        run, output = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            {**valid_payload(), "provider": "fake-llm-v1", "fake_response_type": "valid"},
            provider_name="fake-llm-v1",
            now_fn=app_module.current_time_text,
        )
        serialized = alignment_verification.serialize_alignment_verification_run(run)

        assert output["provider_type"] == "fake_llm"
        assert serialized["provider_type"] == "fake_llm"
        assert serialized["prompt_version"] == alignment_prompting.PROMPT_VERSION
        assert serialized["parser_version"] == "alignment-parser-v1"
        assert serialized["output_schema_version"] == "alignment-output-v1"
        assert serialized["provider_response_status"] == "parsed"
        assert serialized["alignment_decision"] == "likely_aligned"
        assert serialized["prompt_summary"]["stores_full_prompt"] is False
        assert serialized["raw_output_summary"]["stores_full_raw_output"] is False


def test_verify_concept_card_fake_provider_attach_never_approves_or_writes_confidence(app_module):
    with app_module.app.app_context():
        card = create_concept_card(app_module)
        run, output, _ = alignment_verification.verify_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.AlignmentVerificationRun,
            card.card_uid,
            provider_name="fake-llm-v1",
            provider_options={"fake_response_type": "valid"},
            now_fn=app_module.current_time_text,
            commit=False,
        )
        attached = alignment_verification.apply_verification_result_to_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            run,
            commit=True,
        )
        serialized = concept_alignment_cards.serialize_concept_card(attached)

        assert output["alignment_confidence"] > 0.5
        assert serialized["status"] == "needs_review"
        assert serialized["status"] != "approved"
        assert serialized["confidence_score"] is None
        assert "alignment_verification_fake_only" in serialized["risk_labels"]


def test_verify_alignment_fake_provider_failed_output_creates_failed_run(app_module):
    with app_module.app.app_context():
        run, output = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            {**valid_payload(), "fake_response_type": "non_json"},
            provider_name="fake-llm-v1",
            now_fn=app_module.current_time_text,
        )

        assert run.verification_status == "failed"
        assert run.error_code == "provider_output_not_json"
        assert output["provider_response_status"] == "parse_failed"
        assert run.alignment_confidence is None


def test_alignment_verify_api_fake_provider_success_failure_and_audit(client, app_module, teacher_token):
    success_request_id = f"fake-api-{uuid.uuid4().hex[:6]}"
    success = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "fake-llm-v1", "fake_response_type": "valid"},
        headers={**bearer(teacher_token), "X-Request-ID": success_request_id},
    )
    failure_request_id = f"fake-api-fail-{uuid.uuid4().hex[:6]}"
    failed = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "fake-llm-v1", "fake_response_type": "non_json"},
        headers={**bearer(teacher_token), "X-Request-ID": failure_request_id},
    )
    unknown = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "provider-not-enabled"},
        headers={**bearer(teacher_token), "X-Request-ID": f"{failure_request_id}-unknown"},
    )

    assert success.status_code == 200, success.get_data(as_text=True)
    success_data = success.get_json()["data"]
    assert success_data["provider_name"] == "fake-llm-v1"
    assert success_data["provider_type"] == "fake_llm"
    assert success_data["prompt_version"] == alignment_prompting.PROMPT_VERSION
    assert success_data["output_schema_version"] == "alignment-output-v1"
    assert success_data["alignment_decision"] == "likely_aligned"
    assert success_data["can_auto_approve"] is False
    assert success_data["is_production_result"] is False
    assert failed.status_code == 200, failed.get_data(as_text=True)
    failed_data = failed.get_json()["data"]
    assert failed_data["verification_status"] == "failed"
    assert failed_data["provider_response_status"] == "parse_failed"
    assert failed_data["can_auto_approve"] is False
    assert unknown.status_code == 400
    assert unknown.get_json()["audit_error_code"] == "unknown_provider"

    with app_module.app.app_context():
        completed = app_module.AuditRecord.query.filter_by(
            request_id=success_request_id,
            event_type="alignment_verification_completed",
        ).first()
        failed_audit = app_module.AuditRecord.query.filter_by(
            request_id=failure_request_id,
            event_type="alignment_verification_failed",
        ).first()
        assert completed is not None
        assert failed_audit is not None
        completed_payload = audit_records.serialize_audit_record(completed)["output_payload"]
        failed_payload = audit_records.serialize_audit_record(failed_audit)["output_payload"]
        assert completed_payload["provider_type"] == "fake_llm"
        assert (
            completed_payload["prompt_version"]
            == alignment_prompting.PROMPT_VERSION
        )
        assert completed_payload["output_schema_version"] == "alignment-output-v1"
        assert completed_payload["alignment_decision"] == "likely_aligned"
        assert failed_payload["provider_response_status"] == "parse_failed"
        assert "raw_output_preview" not in str(completed_payload)
        assert "english_evidence" not in str(completed_payload)


def test_alignment_verify_api_fake_provider_card_attach_stays_needs_review(client, app_module, teacher_token):
    request_id = f"fake-attach-{uuid.uuid4().hex[:6]}"
    with app_module.app.app_context():
        card = create_concept_card(app_module)
        card_uid = card.card_uid

    response = client.post(
        "/api/alignment/verify",
        json={
            "card_uid": card_uid,
            "provider": "fake-llm-v1",
            "fake_response_type": "valid",
            "attach_to_card": True,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["card"]["status"] == "needs_review"
    assert data["card"]["status"] != "approved"
    assert data["card"]["confidence_score"] is None
    assert data["can_auto_approve"] is False
    assert data["is_production_result"] is False
    with app_module.app.app_context():
        attached = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="alignment_verification_attached_to_card",
        ).first()
        assert attached is not None
