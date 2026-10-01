import json
import uuid

import pytest

from services import alignment_providers
from services import alignment_verification
from services import audit_records
from services import concept_alignment_cards


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="Verify"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def evidence_item(term, *, chunk_uid=None, score=0.72, **overrides):
    return {
        "chunk_uid": chunk_uid or f"chunk-{uuid.uuid4().hex}",
        "source_uid": overrides.get("source_uid", f"src-{uuid.uuid4().hex}"),
        "source_title": overrides.get("source_title", f"{term} Source"),
        "course": overrides.get("course", "Verification Course"),
        "chapter": overrides.get("chapter", "Verification Chapter"),
        "language": overrides.get("language", "en"),
        "source_role": overrides.get("source_role", "english_course_material"),
        "trust_level": overrides.get("trust_level", "teacher_verified"),
        "quality_status": overrides.get("quality_status", "native_text_ok"),
        "quality_flags": overrides.get("quality_flags", ["native_text_ok"]),
        "source_locator": overrides.get("source_locator", "page:3"),
        "snippet": overrides.get("snippet", f"{term} bounded evidence snippet."),
        "score": score,
        "retrieval_reason": "test lexical evidence",
        "risk_labels": overrides.get("risk_labels", []),
        "parse_uid": overrides.get("parse_uid", f"parse-{uuid.uuid4().hex}"),
        "parse_block_uid": overrides.get("parse_block_uid", f"block-{uuid.uuid4().hex}"),
    }


def valid_payload(english_term=None, chinese_term=None):
    english_term = english_term or unique_token("Fourier")
    chinese_term = chinese_term or f"傅里叶{uuid.uuid4().hex[:6]}"
    return {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": "Verification Course",
        "chapter": "Verification Chapter",
        "english_evidence": [evidence_item(english_term, language="en")],
        "chinese_evidence": [
            evidence_item(
                chinese_term,
                language="zh",
                source_role="chinese_reference_material",
                trust_level="reference_material",
            )
        ],
        "candidate_info": {
            "candidate_uid": f"cand-{uuid.uuid4().hex}",
            "chinese_term": chinese_term,
            "score": 0.81,
            "risk_labels": ["candidate_not_alignment_verified"],
        },
        "retrieval_version": "lexical-v1",
        "risk_labels": ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
    }


def create_concept_card(app_module, payload=None, **overrides):
    payload = payload or valid_payload()
    card = app_module.ConceptAlignmentCard(
        english_term=payload["english_term"],
        chinese_term=payload.get("chinese_term", ""),
        course=payload.get("course", "Verification Course"),
        chapter=payload.get("chapter", "Verification Chapter"),
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


def test_alignment_verification_run_model_and_json_fields(app_module):
    with app_module.app.app_context():
        payload = valid_payload()
        run, output = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            payload,
            now_fn=app_module.current_time_text,
        )
        serialized = alignment_verification.serialize_alignment_verification_run(run)

        assert run.run_uid
        assert serialized["input_payload"]["english_term"] == payload["english_term"]
        assert serialized["output_payload"]["provider_type"] == "mock"
        assert serialized["retrieval_score_summary"]["max"] == 0.72
        assert serialized["candidate_score_summary"]["selected_candidate_score"] == 0.81
        assert 0 <= serialized["alignment_confidence"] <= 1


def test_alignment_verification_run_rejects_invalid_confidence(app_module):
    with app_module.app.app_context():
        with pytest.raises(ValueError):
            app_module.AlignmentVerificationRun(
                english_term="Invalid Confidence",
                alignment_confidence=1.2,
            )


def test_input_schema_redacts_sensitive_fields_and_adds_missing_risks():
    payload = {
        "english_term": "Fourier transform",
        "course": "Signals",
        "english_evidence": [{
            "snippet": "x" * 500,
            "Authorization": "Bearer secret-token",
            "Cookie": "session=secret",
        }],
        "DEEPSEEK_API_KEY": "secret",
    }

    normalized = alignment_verification.validate_alignment_verification_input(payload)

    assert normalized["chinese_term"] == ""
    assert "missing_chinese_term" in normalized["risk_labels"]
    assert "no_chinese_evidence" in normalized["risk_labels"]
    assert len(normalized["english_evidence"][0]["snippet"]) <= 303
    assert "secret-token" not in json.dumps(normalized, ensure_ascii=False)
    assert "DEEPSEEK_API_KEY" not in json.dumps(normalized, ensure_ascii=False)


def test_input_schema_rejects_missing_english_term():
    with pytest.raises(alignment_verification.AlignmentVerificationError):
        alignment_verification.validate_alignment_verification_input({"course": "No English"})


def test_mock_provider_output_rules_and_risks():
    provider = alignment_providers.MockAlignmentProvider()
    payload = valid_payload()
    payload["chinese_term_candidates"] = [
        {"chinese_term": payload["chinese_term"], "score": 0.74},
        {"chinese_term": f"歧义{uuid.uuid4().hex[:6]}", "score": 0.71},
    ]
    payload["english_evidence"][0]["quality_status"] = "partial_text"
    payload["english_evidence"][0]["quality_flags"] = ["partial_text"]
    payload["english_evidence"][0]["course"] = "Other Course"
    normalized = alignment_verification.validate_alignment_verification_input(payload)

    output = provider.verify_alignment(normalized)

    assert output["verification_status"] == "mock_only"
    assert output["provider_name"] == "mock-rule-v1"
    assert output["provider_type"] == "mock"
    assert output["is_production_result"] is False
    assert output["can_auto_approve"] is False
    assert output["recommendation"] in {"candidate_ambiguous", "needs_review"}
    assert "ambiguous_chinese_candidates" in output["risk_labels"]
    assert "evidence_from_partial_text" in output["risk_labels"]
    assert "course_mismatch" in output["risk_labels"]
    assert "bilingual_alignment_not_verified" in output["risk_labels"]
    assert "candidate_not_alignment_verified" in output["risk_labels"]
    assert "Mock rule-based" in output["explanation"]


def test_mock_provider_missing_evidence_returns_insufficient_evidence():
    provider = alignment_providers.MockAlignmentProvider()
    payload = alignment_verification.validate_alignment_verification_input({
        "english_term": "No Evidence Term",
        "chinese_term": "无证据术语",
        "course": "No Evidence Course",
    })

    output = provider.verify_alignment(payload)

    assert output["recommendation"] == "insufficient_evidence"
    assert "no_english_evidence" in output["risk_labels"]
    assert "no_chinese_evidence" in output["risk_labels"]
    assert output["can_auto_approve"] is False


def test_verify_concept_card_and_attach_does_not_approve_or_write_confidence(app_module):
    with app_module.app.app_context():
        card = create_concept_card(app_module)

        run, output, loaded_card = alignment_verification.verify_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.AlignmentVerificationRun,
            card.card_uid,
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

        assert loaded_card.card_uid == card.card_uid
        assert output["can_auto_approve"] is False
        assert serialized["status"] == "needs_review"
        assert serialized["status"] != "approved"
        assert serialized["confidence_score"] is None
        assert "alignment_verification_mock_only" in serialized["risk_labels"]
        assert "bilingual_alignment_not_verified" in serialized["risk_labels"]


def test_alignment_verify_api_payload_card_attach_and_audit(client, app_module, teacher_token):
    request_id = f"alignment-verify-{uuid.uuid4().hex[:6]}"
    payload = valid_payload()
    long_text = "Sensitive full evidence text should not enter audit. " + ("x" * 400)
    payload["english_evidence"][0]["snippet"] = long_text
    with app_module.app.app_context():
        card = create_concept_card(app_module, payload)
        card_uid = card.card_uid

    response = client.post(
        "/api/alignment/verify",
        json={"card_uid": card_uid, "provider": "mock-rule-v1", "attach_to_card": True},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    data = body["data"]
    assert body["request_id"] == request_id
    assert data["run_uid"]
    assert data["provider_type"] == "mock"
    assert data["verification_status"] == "mock_only"
    assert data["can_auto_approve"] is False
    assert data["is_production_result"] is False
    assert data["card"]["status"] == "needs_review"
    assert data["card"]["confidence_score"] is None
    with app_module.app.app_context():
        completed = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="alignment_verification_completed",
        ).first()
        attached = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="alignment_verification_attached_to_card",
        ).first()
        assert completed is not None
        assert attached is not None
        serialized = audit_records.serialize_audit_record(completed)
        assert serialized["output_payload"]["provider_type"] == "mock"
        assert "Sensitive full evidence text" not in str(serialized["input_payload"])
        assert "Sensitive full evidence text" not in str(serialized["output_payload"])
        assert "Authorization" not in str(serialized["input_payload"])


def test_alignment_verify_api_direct_payload_and_validation_errors(client, app_module, teacher_token):
    request_id = f"alignment-payload-{uuid.uuid4().hex[:6]}"
    response = client.post(
        "/api/alignment/verify",
        json=valid_payload(),
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )
    missing = client.post(
        "/api/alignment/verify",
        json={"course": "Missing English"},
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-missing"},
    )
    bad_provider = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "real-provider-not-configured"},
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-provider"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["provider_name"] == "mock-rule-v1"
    assert data["alignment_confidence"] is not None
    assert data["can_auto_approve"] is False
    assert missing.status_code == 400
    assert missing.get_json()["request_id"] == f"{request_id}-missing"
    assert bad_provider.status_code == 400
    assert bad_provider.get_json()["audit_error_code"] == "unknown_provider"
    with app_module.app.app_context():
        failed = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-provider",
            event_type="alignment_verification_failed",
        ).first()
        assert failed is not None
