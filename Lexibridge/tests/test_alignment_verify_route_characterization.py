import json
import socket
import uuid

from services import audit_records
from services import llm_provider_config
from services import concept_alignment_cards
from services import provider_governance


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


def unique_token(prefix="VerifyBoundary"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def evidence_item(term, *, language="en", course="Verify Boundary Course", score=0.72, **overrides):
    return {
        "chunk_uid": overrides.get("chunk_uid", f"chunk-{uuid.uuid4().hex}"),
        "source_uid": overrides.get("source_uid", f"src-{uuid.uuid4().hex}"),
        "source_title": overrides.get("source_title", f"{term} Source"),
        "course": course,
        "chapter": overrides.get("chapter", "Execution Boundary"),
        "language": language,
        "source_role": overrides.get(
            "source_role",
            "english_course_material" if language == "en" else "chinese_reference_material",
        ),
        "trust_level": overrides.get("trust_level", "teacher_verified"),
        "quality_status": overrides.get("quality_status", "native_text_ok"),
        "quality_flags": overrides.get("quality_flags", ["native_text_ok"]),
        "source_locator": overrides.get("source_locator", "page:7"),
        "snippet": overrides.get("snippet", f"{term} bounded evidence snippet."),
        "score": score,
        "retrieval_reason": "route boundary characterization",
        "risk_labels": overrides.get("risk_labels", []),
        "parse_uid": overrides.get("parse_uid", f"parse-{uuid.uuid4().hex}"),
        "parse_block_uid": overrides.get("parse_block_uid", f"block-{uuid.uuid4().hex}"),
    }


def valid_payload(**overrides):
    course = overrides.pop("course", "Verify Boundary Course")
    english_term = overrides.pop("english_term", unique_token("Fourier"))
    chinese_term = overrides.pop("chinese_term", f"傅里叶{uuid.uuid4().hex[:6]}")
    payload = {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": course,
        "chapter": "Execution Boundary",
        "english_evidence": [evidence_item(english_term, language="en", course=course)],
        "chinese_evidence": [evidence_item(chinese_term, language="zh", course=course, score=0.68)],
        "candidate_info": {
            "candidate_uid": f"cand-{uuid.uuid4().hex}",
            "chinese_term": chinese_term,
            "score": 0.82,
            "risk_labels": ["candidate_not_alignment_verified"],
        },
        "risk_labels": ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
        "retrieval_version": "lexical-v1",
    }
    payload.update(overrides)
    return payload


def create_card(app_module, payload=None, **overrides):
    payload = payload or valid_payload()
    card = app_module.ConceptAlignmentCard(
        english_term=payload["english_term"],
        chinese_term=payload.get("chinese_term", ""),
        course=payload.get("course", "Verify Boundary Course"),
        chapter=payload.get("chapter", "Execution Boundary"),
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


def upsert_replay_policy(app_module, *, allow_attach=False, allowed_courses=None, allowed_roles=None, **overrides):
    payload = {
        "provider_type": "replay_llm",
        "enabled": True,
        "status": "active",
        "replay_only": True,
        "allow_external_calls": False,
        "allow_attach_to_card": allow_attach,
        "allow_production_result": False,
        "allow_auto_approve": False,
        "require_human_review": True,
        "allowed_courses": allowed_courses or ["Verify Boundary Course"],
        "allowed_roles": allowed_roles or ["teacher", "admin"],
    }
    payload.update(overrides)
    return provider_governance.create_or_update_provider_policy(
        app_module.db.session,
        app_module.AlignmentProviderPolicy,
        "external-llm-replay-v1",
        payload,
        now_fn=app_module.current_time_text,
        commit=True,
    )[0]


def side_effect_counts(app_module):
    return {
        "runs": app_module.AlignmentVerificationRun.query.count(),
        "usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "audits": app_module.AuditRecord.query.count(),
        "cards": app_module.ConceptAlignmentCard.query.count(),
        "policies": app_module.AlignmentProviderPolicy.query.count(),
    }


def assert_success(response, request_id):
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "success"
    assert body["request_id"] == request_id
    assert "data" in body
    return body


def assert_error(response, status_code, request_id):
    assert response.status_code == status_code, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "error"
    assert body["request_id"] == request_id
    return body


def assert_no_secret_values(payload):
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in [
        "LEXIBRIDGE_SENTINEL_SECRET_9C4D",
        "Bearer sentinel",
        "Authorization",
        "Cookie",
        "private key",
        "password",
        "api_key",
    ]:
        assert forbidden not in serialized


def test_alignment_verify_route_map_contract(app_module):
    actual = route_map(app_module)
    assert actual[("/api/alignment/verify", "POST")] == "verify_alignment_api"
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/alignment/verify" and "POST" in rule.methods
    ) == 1


def test_alignment_verify_auth_and_role_contract(client, teacher_token, student_token, admin_token):
    unauth = client.post(
        "/api/alignment/verify",
        json=valid_payload(),
        headers={"X-Request-ID": "verify-auth-unauth"},
    )
    assert_error(unauth, 401, "verify-auth-unauth")

    student = client.post(
        "/api/alignment/verify",
        json=valid_payload(provider="mock-rule-v1"),
        headers={**bearer(student_token), "X-Request-ID": "verify-auth-student"},
    )
    student_body = assert_success(student, "verify-auth-student")
    assert student_body["data"]["provider_name"] == "mock-rule-v1"
    assert student_body["data"]["verification_status"] == "mock_only"

    teacher = client.post(
        "/api/alignment/verify",
        json=valid_payload(provider="mock-rule-v1"),
        headers={**bearer(teacher_token), "X-Request-ID": "verify-auth-teacher"},
    )
    assert_success(teacher, "verify-auth-teacher")

    admin = client.post(
        "/api/alignment/verify",
        json=valid_payload(provider="mock-rule-v1"),
        headers={**bearer(admin_token), "X-Request-ID": "verify-auth-admin"},
    )
    assert_success(admin, "verify-auth-admin")


def test_alignment_verify_provider_modes_and_write_set(client, app_module, teacher_token, monkeypatch):
    monkeypatch.setenv(llm_provider_config.EXTERNAL_LLM_ENABLED_ENV, "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "LEXIBRIDGE_FAKE_DEEPSEEK_KEY_FOR_TESTS_ONLY")
    with app_module.app.app_context():
        upsert_replay_policy(app_module, allow_attach=False)
        before = side_effect_counts(app_module)

    requests = [
        (
            "verify-mode-mock",
            {**valid_payload(), "provider": "mock-rule-v1"},
            "mock",
            "mock_only",
            "",
        ),
        (
            "verify-mode-fake-valid",
            {**valid_payload(), "provider": "fake-llm-v1", "fake_response_type": "valid"},
            "fake_llm",
            "needs_review",
            "parsed",
        ),
        (
            "verify-mode-fake-non-json",
            {**valid_payload(), "provider": "fake-llm-v1", "fake_response_type": "non_json"},
            "fake_llm",
            "failed",
            "parse_failed",
        ),
        (
            "verify-mode-replay",
            {**valid_payload(), "provider": "external-llm-replay-v1", "replay_response_type": "valid"},
            "replay_llm",
            "needs_review",
            "replayed",
        ),
        (
            "verify-mode-disabled-external",
            {**valid_payload(), "provider": "deepseek-alignment-v1-disabled"},
            "external_llm",
            "failed",
            "provider_policy_missing",
        ),
        (
            "verify-mode-formal-deepseek",
            {**valid_payload(), "provider": llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME},
            "external_llm",
            "failed",
            "provider_policy_missing",
        ),
    ]

    for request_id, payload, provider_type, verification_status, provider_response_status in requests:
        response = client.post(
            "/api/alignment/verify",
            json=payload,
            headers={**bearer(teacher_token), "X-Request-ID": request_id},
        )
        body = assert_success(response, request_id)
        data = body["data"]
        assert data["provider_type"] == provider_type
        assert data["verification_status"] == verification_status
        assert data["can_auto_approve"] is False
        assert data["is_production_result"] is False
        if provider_response_status:
            assert data["provider_response_status"] == provider_response_status

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["runs"] == before["runs"] + len(requests)
        assert after["usage"] == before["usage"] + len(requests)
        assert after["cards"] == before["cards"]
        disabled_blocked = app_module.AuditRecord.query.filter_by(
            request_id="verify-mode-disabled-external",
            event_type="alignment_verification_blocked_by_policy",
        ).one()
        formal_deepseek_blocked = app_module.AuditRecord.query.filter_by(
            request_id="verify-mode-formal-deepseek",
            event_type="alignment_verification_blocked_by_policy",
        ).one()
        usage = app_module.AuditRecord.query.filter_by(
            request_id="verify-mode-replay",
            event_type="provider_usage_recorded",
        ).one()
        assert disabled_blocked.error_code == "provider_policy_missing"
        assert formal_deepseek_blocked.error_code == "provider_policy_missing"
        assert usage.target_type == "alignment_provider_policy"


def test_alignment_verify_validation_lookup_and_error_mapping(client, app_module, teacher_token):
    with app_module.app.app_context():
        before = side_effect_counts(app_module)

    malformed = client.post(
        "/api/alignment/verify",
        data="{",
        content_type="application/json",
        headers={**bearer(teacher_token), "X-Request-ID": "verify-malformed-json"},
    )
    malformed_body = assert_error(malformed, 400, "verify-malformed-json")
    assert malformed_body["audit_error_code"] == "alignment_verification_validation_error"

    empty = client.post(
        "/api/alignment/verify",
        json={},
        headers={**bearer(teacher_token), "X-Request-ID": "verify-empty-body"},
    )
    assert_error(empty, 400, "verify-empty-body")

    unknown_provider = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "provider-not-enabled"},
        headers={**bearer(teacher_token), "X-Request-ID": "verify-unknown-provider"},
    )
    unknown_body = assert_error(unknown_provider, 400, "verify-unknown-provider")
    assert unknown_body["audit_error_code"] == "unknown_provider"

    missing_card = client.post(
        "/api/alignment/verify",
        json={"card_uid": f"missing-card-{uuid.uuid4().hex}", "provider": "mock-rule-v1"},
        headers={**bearer(teacher_token), "X-Request-ID": "verify-missing-card"},
    )
    missing_body = assert_error(missing_card, 404, "verify-missing-card")
    assert missing_body["audit_error_code"] == "concept_card_not_found"

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["runs"] == before["runs"]
        assert after["usage"] == before["usage"]
        assert app_module.AuditRecord.query.filter_by(
            request_id="verify-unknown-provider",
            event_type="alignment_verification_failed",
        ).one()


def test_alignment_verify_attach_gate_blocks_and_allows_card_update(client, app_module, teacher_token):
    with app_module.app.app_context():
        upsert_replay_policy(app_module, allow_attach=False)
        blocked_card = create_card(app_module)
        blocked_uid = blocked_card.card_uid

    blocked = client.post(
        "/api/alignment/verify",
        json={
            "card_uid": blocked_uid,
            "provider": "external-llm-replay-v1",
            "replay_response_type": "valid",
            "attach_to_card": True,
        },
        headers={**bearer(teacher_token), "X-Request-ID": "verify-attach-blocked"},
    )
    blocked_body = assert_success(blocked, "verify-attach-blocked")
    assert blocked_body["data"]["attach_blocked_reason"] == "provider_attach_not_allowed"
    assert blocked_body["data"]["card"]["status"] == "draft"

    with app_module.app.app_context():
        refreshed = app_module.ConceptAlignmentCard.query.filter_by(card_uid=blocked_uid).one()
        assert concept_alignment_cards.serialize_concept_card(refreshed)["status"] == "draft"
        upsert_replay_policy(app_module, allow_attach=True)
        allowed_card = create_card(app_module)
        allowed_uid = allowed_card.card_uid

    allowed = client.post(
        "/api/alignment/verify",
        json={
            "card_uid": allowed_uid,
            "provider": "external-llm-replay-v1",
            "replay_response_type": "valid",
            "attach_to_card": "yes",
        },
        headers={**bearer(teacher_token), "X-Request-ID": "verify-attach-allowed"},
    )
    allowed_body = assert_success(allowed, "verify-attach-allowed")
    assert allowed_body["data"]["card"]["status"] == "needs_review"
    assert allowed_body["data"]["card"]["status"] != "approved"
    assert allowed_body["data"]["card"]["confidence_score"] is None

    with app_module.app.app_context():
        refreshed = app_module.ConceptAlignmentCard.query.filter_by(card_uid=allowed_uid).one()
        serialized_card = concept_alignment_cards.serialize_concept_card(refreshed)
        assert "alignment_verification_replay_only" in serialized_card["risk_labels"]
        assert app_module.AuditRecord.query.filter_by(
            request_id="verify-attach-allowed",
            event_type="alignment_verification_attached_to_card",
        ).one()


def test_alignment_verify_secret_redaction_and_no_network(client, app_module, teacher_token, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "LEXIBRIDGE_SENTINEL_SECRET_9C4D")

    def blocked_connect(*args, **kwargs):
        raise AssertionError("alignment verify attempted external network access")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    payload = valid_payload(
        provider="fake-llm-v1",
        fake_response_type="valid",
        api_key="LEXIBRIDGE_SENTINEL_SECRET_9C4D",
        secret="LEXIBRIDGE_SENTINEL_SECRET_9C4D",
        token="LEXIBRIDGE_SENTINEL_SECRET_9C4D",
        password="password",
        private_key="private key",
    )
    payload["english_evidence"][0]["Authorization"] = "Bearer sentinel"
    payload["english_evidence"][0]["Cookie"] = "Cookie: sentinel"

    response = client.post(
        "/api/alignment/verify",
        json=payload,
        headers={**bearer(teacher_token), "X-Request-ID": "verify-secret-no-network"},
    )
    body = assert_success(response, "verify-secret-no-network")
    assert_no_secret_values(body)

    with app_module.app.app_context():
        run = app_module.AlignmentVerificationRun.query.filter_by(run_uid=body["data"]["run_uid"]).one()
        audits = app_module.AuditRecord.query.filter_by(request_id="verify-secret-no-network").all()
        usage = app_module.AlignmentProviderUsageRecord.query.filter_by(run_uid=run.run_uid).one()
        assert_no_secret_values({
            "input_payload": run.input_payload,
            "output_payload": run.output_payload,
            "usage": {
                "error_code": usage.error_code,
                "error_message": usage.error_message,
                "provider_response_status": usage.provider_response_status,
            },
            "audits": [audit_records.serialize_audit_record(item) for item in audits],
        })


def test_alignment_verify_rollback_when_usage_write_fails(client, app_module, teacher_token, monkeypatch):
    with app_module.app.app_context():
        before = side_effect_counts(app_module)

    def fail_usage(*args, **kwargs):
        raise RuntimeError("forced usage failure for characterization")

    monkeypatch.setattr(app_module, "record_alignment_provider_usage", fail_usage)
    response = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "mock-rule-v1"},
        headers={**bearer(teacher_token), "X-Request-ID": "verify-usage-rollback"},
    )
    body = assert_error(response, 500, "verify-usage-rollback")
    assert body["audit_error_code"] == "alignment_verification_failed"

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["runs"] == before["runs"]
        assert after["usage"] == before["usage"]
        failed = app_module.AuditRecord.query.filter_by(
            request_id="verify-usage-rollback",
            event_type="alignment_verification_failed",
        ).one()
        assert failed.error_code == "alignment_verification_failed"
        assert app_module.AlignmentVerificationRun.query.count() == after["runs"]


def test_alignment_verify_repeated_identical_request_creates_independent_runs_and_usage(
    client,
    app_module,
    teacher_token,
):
    payload = {**valid_payload(), "provider": "mock-rule-v1"}
    with app_module.app.app_context():
        before = side_effect_counts(app_module)

    first = client.post(
        "/api/alignment/verify",
        json=payload,
        headers={**bearer(teacher_token), "X-Request-ID": "verify-repeat-first"},
    )
    second = client.post(
        "/api/alignment/verify",
        json=payload,
        headers={**bearer(teacher_token), "X-Request-ID": "verify-repeat-second"},
    )
    first_data = assert_success(first, "verify-repeat-first")["data"]
    second_data = assert_success(second, "verify-repeat-second")["data"]
    assert first_data["run_uid"] != second_data["run_uid"]

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["runs"] == before["runs"] + 2
        assert after["usage"] == before["usage"] + 2
