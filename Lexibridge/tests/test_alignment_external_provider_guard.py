import json
import uuid

import pytest

from services import alignment_providers
from services import alignment_prompting
from services import alignment_verification
from services import audit_records
from services import concept_alignment_cards
from services import llm_provider_config
from services import llm_transport
from services import provider_governance


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="External"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def evidence_item(term, *, language="en", score=0.7, **overrides):
    return {
        "chunk_uid": overrides.get("chunk_uid", f"chunk-{uuid.uuid4().hex}"),
        "source_uid": overrides.get("source_uid", f"src-{uuid.uuid4().hex}"),
        "source_title": overrides.get("source_title", f"{term} Source"),
        "course": overrides.get("course", "External Guard Course"),
        "chapter": overrides.get("chapter", "Provider Safety"),
        "language": language,
        "source_role": overrides.get("source_role", "english_course_material" if language == "en" else "chinese_reference_material"),
        "trust_level": overrides.get("trust_level", "teacher_verified"),
        "quality_status": overrides.get("quality_status", "native_text_ok"),
        "quality_flags": overrides.get("quality_flags", ["native_text_ok"]),
        "source_locator": overrides.get("source_locator", "page:9"),
        "snippet": overrides.get("snippet", f"{term} bounded evidence snippet."),
        "score": score,
        "retrieval_reason": "test lexical evidence",
        "risk_labels": overrides.get("risk_labels", []),
        "parse_uid": overrides.get("parse_uid", f"parse-{uuid.uuid4().hex}"),
        "parse_block_uid": overrides.get("parse_block_uid", f"block-{uuid.uuid4().hex}"),
    }


def valid_payload(**overrides):
    english_term = overrides.get("english_term", unique_token("Fourier"))
    chinese_term = overrides.get("chinese_term", f"傅里叶{uuid.uuid4().hex[:6]}")
    return {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": "External Guard Course",
        "chapter": "Provider Safety",
        "english_evidence": [evidence_item(english_term, language="en")],
        "chinese_evidence": [evidence_item(chinese_term, language="zh", score=0.68)],
        "candidate_info": {
            "candidate_uid": f"cand-{uuid.uuid4().hex}",
            "chinese_term": chinese_term,
            "score": 0.82,
            "risk_labels": ["candidate_not_alignment_verified"],
        },
        "risk_labels": ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
        "retrieval_version": "lexical-v1",
    }


def create_concept_card(app_module, payload=None):
    payload = payload or valid_payload()
    card = app_module.ConceptAlignmentCard(
        english_term=payload["english_term"],
        chinese_term=payload.get("chinese_term", ""),
        course=payload.get("course", "External Guard Course"),
        chapter=payload.get("chapter", "Provider Safety"),
        english_evidence=payload.get("english_evidence", []),
        chinese_evidence=payload.get("chinese_evidence", []),
        risk_labels=payload.get("risk_labels", []),
        status="draft",
        retrieval_version=payload.get("retrieval_version", "lexical-v1"),
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def allow_replay_policy(app_module, *, allow_attach=True):
    with app_module.app.app_context():
        provider_governance.create_or_update_provider_policy(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            "external-llm-replay-v1",
            {
                "provider_type": "replay_llm",
                "enabled": True,
                "status": "active",
                "replay_only": True,
                "allow_attach_to_card": allow_attach,
                "allowed_roles": ["teacher", "admin"],
            },
            now_fn=app_module.current_time_text,
            commit=True,
        )


def test_llm_provider_config_defaults_and_sanitization(monkeypatch):
    monkeypatch.delenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = llm_provider_config.get_llm_provider_config("deepseek-alignment-v1-disabled")
    sanitized = llm_provider_config.sanitize_provider_config({
        **config,
        "api_key": "real-key-should-not-return",
        "base_url": "https://user:secret@example.test/v1?api_key=secret",
    })

    assert llm_provider_config.is_external_llm_enabled() is False
    assert config["enabled"] is False
    assert sanitized["base_url"] == "https://example.test/v1"
    assert "api_key" not in sanitized
    assert "real-key-should-not-return" not in json.dumps(sanitized)
    assert sanitized["api_key_env_name"] == "DEEPSEEK_API_KEY"
    with pytest.raises(llm_provider_config.LLMProviderConfigError) as disabled:
        llm_provider_config.require_external_llm_enabled("deepseek-alignment-v1-disabled", config=config)
    assert disabled.value.error_code == "provider_disabled"
    with pytest.raises(llm_provider_config.LLMProviderConfigError) as still_disabled:
        llm_provider_config.require_external_llm_enabled(
            "deepseek-alignment-v1-disabled",
            config={**config, "enabled": True, "replay_mode": False, "api_key_env_name": "LEXIBRIDGE_TEST_MISSING_KEY"},
        )
    assert still_disabled.value.error_code == "provider_disabled"

    formal = llm_provider_config.get_llm_provider_config(
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        env={llm_provider_config.EXTERNAL_LLM_ENABLED_ENV: "1"},
    )
    with pytest.raises(llm_provider_config.LLMProviderConfigError) as missing_key:
        llm_provider_config.require_external_llm_enabled(
            llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
            config=formal,
        )
    assert missing_key.value.error_code == "credential_missing"


def test_cost_timeout_and_retry_helpers():
    config = llm_provider_config.get_llm_provider_config("external-llm-replay-v1", overrides={"max_estimated_cost": 0.00001})
    estimate = llm_provider_config.estimate_alignment_call_cost(
        {"prompt_chars": 10000, "expected_output_chars": 2000},
        "external-llm-replay-v1",
        config=config,
    )

    assert llm_provider_config.normalize_provider_timeout("999") == 120
    assert llm_provider_config.normalize_provider_timeout("bad") == 30
    assert llm_provider_config.normalize_provider_retry_policy({"max_retries": 99})["max_retries"] == 3
    assert estimate["cost_is_estimate"] is True
    assert estimate["exceeds_limit"] is True
    assert {
        "provider_disabled",
        "missing_api_key",
        "provider_timeout",
        "provider_rate_limited",
        "provider_non_json_output",
        "provider_schema_invalid",
        "provider_confidence_out_of_range",
        "provider_cost_limit_exceeded",
        "provider_output_too_long",
    } <= llm_provider_config.LLM_PROVIDER_ERROR_CODES


def test_provider_registry_includes_disabled_and_replay_providers():
    names = {item["provider_name"] for item in alignment_providers.list_alignment_providers()}
    disabled = alignment_providers.get_alignment_provider("deepseek-alignment-v1-disabled")
    replay = alignment_providers.get_alignment_provider("external-llm-replay-v1")

    assert {"mock-rule-v1", "fake-llm-v1", "deepseek-alignment-v1-disabled", "external-llm-replay-v1"} <= names
    assert disabled.provider_type == "external_llm"
    assert disabled.supports_external_calls is True
    assert disabled.is_production_provider is True
    assert replay.provider_type == "replay_llm"
    assert replay.supports_external_calls is False
    assert replay.is_production_provider is False
    with pytest.raises(alignment_providers.AlignmentProviderError):
        alignment_providers.get_alignment_provider("external-provider-not-configured")


def test_transport_fixtures_do_not_call_network_or_record_sensitive_headers():
    disabled = llm_transport.DisabledLLMTransport().generate("prompt", {"provider_name": "disabled"}, {"Authorization": "Bearer secret"})
    fake = llm_transport.FakeLLMTransport().generate("prompt", {}, {"fake_response_type": "valid", "Cookie": "session=secret"})
    replay = llm_transport.ReplayLLMTransport().generate("prompt", {}, {"replay_response_type": "valid", "api_key": "secret"})
    http = llm_transport.HTTPTransport().generate("prompt", {}, {})

    assert disabled.error_code == "provider_disabled"
    assert fake.status == "success"
    assert replay.status == "success"
    assert http.error_code == "provider_disabled"
    assert "Authorization" not in fake.raw_output
    assert "Cookie" not in replay.raw_output
    assert "secret" not in replay.raw_output


def test_disabled_external_provider_creates_failed_run_without_network(app_module):
    with app_module.app.app_context():
        run, output = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            valid_payload(),
            provider_name="deepseek-alignment-v1-disabled",
            now_fn=app_module.current_time_text,
        )
        serialized = alignment_verification.serialize_alignment_verification_run(run)

        assert output["error_code"] == "provider_disabled"
        assert run.verification_status == "failed"
        assert serialized["provider_type"] == "external_llm"
        assert serialized["provider_response_status"] == "provider_disabled"
        assert serialized["alignment_confidence"] is None
        assert "provider_disabled" in serialized["risk_labels"]


def test_replay_provider_parses_fixture_and_records_prompt_metadata(app_module):
    with app_module.app.app_context():
        run, output = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            {**valid_payload(), "provider": "external-llm-replay-v1", "replay_response_type": "valid"},
            provider_name="external-llm-replay-v1",
            now_fn=app_module.current_time_text,
        )
        serialized = alignment_verification.serialize_alignment_verification_run(run)

        assert output["provider_response_status"] == "replayed"
        assert output["can_auto_approve"] is False
        assert output["is_production_result"] is False
        assert serialized["provider_type"] == "replay_llm"
        assert serialized["prompt_version"] == alignment_prompting.PROMPT_VERSION
        assert serialized["parser_version"] == "alignment-parser-v1"
        assert serialized["output_schema_version"] == "alignment-output-v1"
        assert serialized["estimated_cost"]["cost_is_estimate"] is True


def test_replay_provider_failure_paths_for_non_json_output_length_and_cost(app_module):
    with app_module.app.app_context():
        non_json, _ = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            {**valid_payload(), "replay_response_type": "non_json"},
            provider_name="external-llm-replay-v1",
            now_fn=app_module.current_time_text,
        )
        too_long, _ = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            {**valid_payload(), "replay_response_type": "output_too_long", "max_output_chars": 500},
            provider_name="external-llm-replay-v1",
            now_fn=app_module.current_time_text,
        )
        cost_blocked, _ = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            {**valid_payload(), "replay_response_type": "valid", "max_estimated_cost": 0.00000001},
            provider_name="external-llm-replay-v1",
            now_fn=app_module.current_time_text,
        )

        assert non_json.error_code == "provider_non_json_output"
        assert too_long.error_code == "provider_output_too_long"
        assert cost_blocked.error_code == "provider_cost_limit_exceeded"
        assert non_json.verification_status == "failed"
        assert too_long.verification_status == "failed"
        assert cost_blocked.verification_status == "failed"


def test_prompt_length_gate_marks_truncated_prompt(app_module):
    payload = valid_payload()
    payload["english_evidence"][0]["snippet"] = "long evidence " * 500
    with app_module.app.app_context():
        run, output = alignment_verification.verify_alignment(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            {**payload, "replay_response_type": "valid", "max_prompt_chars": 500},
            provider_name="external-llm-replay-v1",
            now_fn=app_module.current_time_text,
        )
        serialized = alignment_verification.serialize_alignment_verification_run(run)

        assert output["provider_response_status"] == "replayed"
        assert serialized["prompt_summary"]["prompt_truncated"] is True
        assert "prompt_truncated" in serialized["risk_labels"]


def test_alignment_verify_api_disabled_and_replay_provider_audit(client, app_module, teacher_token):
    disabled_request_id = f"disabled-provider-{uuid.uuid4().hex[:6]}"
    replay_request_id = f"replay-provider-{uuid.uuid4().hex[:6]}"
    allow_replay_policy(app_module, allow_attach=True)
    disabled = client.post(
        "/api/alignment/verify",
        json={
            **valid_payload(),
            "provider": "deepseek-alignment-v1-disabled",
            "Authorization": "redacted-test-header",
            "DEEPSEEK_API_KEY": "should-not-persist",
        },
        headers={**bearer(teacher_token), "X-Request-ID": disabled_request_id},
    )
    replay = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "external-llm-replay-v1", "replay_response_type": "valid"},
        headers={**bearer(teacher_token), "X-Request-ID": replay_request_id},
    )

    assert disabled.status_code == 200, disabled.get_data(as_text=True)
    disabled_data = disabled.get_json()["data"]
    assert disabled_data["verification_status"] == "failed"
    assert disabled_data["provider_response_status"] in {"provider_policy_missing", "provider_disabled_by_policy"}
    assert disabled_data["can_auto_approve"] is False
    assert replay.status_code == 200, replay.get_data(as_text=True)
    replay_data = replay.get_json()["data"]
    assert replay_data["provider_response_status"] == "replayed"
    assert replay_data["can_auto_approve"] is False
    assert replay_data["is_production_result"] is False
    with app_module.app.app_context():
        failed_audit = app_module.AuditRecord.query.filter_by(
            request_id=disabled_request_id,
            event_type="alignment_verification_blocked_by_policy",
        ).first()
        completed_audit = app_module.AuditRecord.query.filter_by(
            request_id=replay_request_id,
            event_type="alignment_verification_completed",
        ).first()
        assert failed_audit is not None
        assert completed_audit is not None
        failed_payload = audit_records.serialize_audit_record(failed_audit)
        completed_payload = audit_records.serialize_audit_record(completed_audit)
        assert failed_payload["output_payload"]["provider_response_status"] in {"provider_policy_missing", "provider_disabled_by_policy"}
        assert completed_payload["output_payload"]["provider_response_status"] == "replayed"
        serialized = json.dumps(failed_payload, ensure_ascii=False) + json.dumps(completed_payload, ensure_ascii=False)
        assert "should-not-persist" not in serialized
        assert "Authorization" not in serialized
        assert "DEEPSEEK_API_KEY" not in serialized
        assert "english_evidence" not in serialized


def test_alignment_verify_api_replay_card_attach_stays_needs_review(client, app_module, teacher_token):
    request_id = f"replay-attach-{uuid.uuid4().hex[:6]}"
    allow_replay_policy(app_module, allow_attach=True)
    with app_module.app.app_context():
        card = create_concept_card(app_module)
        card_uid = card.card_uid

    response = client.post(
        "/api/alignment/verify",
        json={
            "card_uid": card_uid,
            "provider": "external-llm-replay-v1",
            "replay_response_type": "valid",
            "attach_to_card": True,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["card"]["status"] == "needs_review"
    assert data["card"]["status"] != "approved"
    assert data["card"]["confidence_score"] is None
    assert data["provider_response_status"] == "replayed"
    assert data["can_auto_approve"] is False
    with app_module.app.app_context():
        attached = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="alignment_verification_attached_to_card",
        ).first()
        refreshed = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uid).first()
        serialized_card = concept_alignment_cards.serialize_concept_card(refreshed)
        assert attached is not None
        assert "alignment_verification_replay_only" in serialized_card["risk_labels"]
