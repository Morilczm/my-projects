import json
import socket
import uuid

from services import audit_records
from services import provider_governance


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def provider_name(prefix="preflight-route-provider"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


def safe_preflight_policy(**overrides):
    payload = {
        "provider_type": "replay_llm",
        "enabled": True,
        "status": "active",
        "replay_only": True,
        "allow_external_calls": False,
        "allow_attach_to_card": False,
        "allow_production_result": False,
        "allow_auto_approve": False,
        "require_human_review": True,
        "allowed_courses": ["Preflight Route Course"],
        "blocked_courses": ["Blocked Preflight Route Course"],
        "allowed_roles": ["teacher", "admin"],
        "max_calls_per_day": 10,
        "max_calls_per_month": 100,
        "max_estimated_cost_per_call": 0.25,
        "max_estimated_cost_per_day": 1.0,
        "max_prompt_chars": 8000,
        "max_output_chars": 4000,
        "timeout_seconds": 30,
        "max_retries": 0,
    }
    payload.update(overrides)
    return payload


def upsert_policy(app_module, provider, **overrides):
    policy, _ = provider_governance.create_or_update_provider_policy(
        app_module.db.session,
        app_module.AlignmentProviderPolicy,
        provider,
        safe_preflight_policy(**overrides),
        now_fn=app_module.current_time_text,
        commit=True,
    )
    return policy


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
        "TEST_PREFLIGHT_SECRET_VALUE_DO_NOT_RETURN",
        "Bearer secret",
        "Authorization",
        "Cookie",
        "private key",
        "super-secret-password",
    ]:
        assert forbidden not in serialized


def side_effect_counts(app_module):
    return {
        "policies": app_module.AlignmentProviderPolicy.query.count(),
        "preflights": app_module.AlignmentProviderPreflightRun.query.count(),
        "usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "audits": app_module.AuditRecord.query.count(),
    }


def test_provider_preflight_route_map_contract(app_module):
    actual = route_map(app_module)
    assert (
        actual[("/api/alignment/providers/<path:provider_name>/preflight", "POST")]
        == "run_alignment_provider_preflight_api"
    )
    assert (
        actual[("/api/alignment/providers/<path:provider_name>/preflight", "GET")]
        == "list_alignment_provider_preflights_api"
    )
    assert (
        actual[("/api/alignment/providers/preflight/<preflight_uid>", "GET")]
        == "get_alignment_provider_preflight_api"
    )
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/alignment/providers/<path:provider_name>/preflight" and "POST" in rule.methods
    ) == 1


def test_provider_preflight_preserves_auth_role_contract(client, app_module, admin_token, teacher_token, student_token):
    provider = provider_name()
    with app_module.app.app_context():
        upsert_policy(app_module, provider)

    unauth = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Route Course"},
        headers={"X-Request-ID": "preflight-unauth"},
    )
    assert_error(unauth, 401, "preflight-unauth")

    student = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Route Course"},
        headers={**bearer(student_token), "X-Request-ID": "preflight-student"},
    )
    assert_error(student, 403, "preflight-student")

    teacher = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Route Course"},
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-teacher"},
    )
    teacher_body = assert_success(teacher, "preflight-teacher")
    assert teacher_body["data"]["provider_name"] == provider

    admin = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Route Course", "include_replay_dry_run": "yes"},
        headers={**bearer(admin_token), "X-Request-ID": "preflight-admin"},
    )
    admin_body = assert_success(admin, "preflight-admin")
    assert admin_body["data"]["provider_name"] == provider


def test_provider_preflight_valid_request_creates_record_and_get_routes_read_it(
    client,
    app_module,
    teacher_token,
):
    provider = "external-llm-replay-v1"
    with app_module.app.app_context():
        policy = upsert_policy(app_module, provider)
        policy_uid = policy.policy_uid
        before_policy = provider_governance.serialize_provider_policy(policy)

    response = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Route Course", "include_replay_dry_run": True, "unknown_field": "ignored"},
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-valid"},
    )
    body = assert_success(response, "preflight-valid")
    data = body["data"]
    assert data["preflight_uid"]
    assert data["provider_name"] == provider
    assert data["policy_uid"] == policy_uid
    assert data["course"] == "Preflight Route Course"
    assert data["check_status"] == "passed"
    assert data["overall_ready"] is True
    assert data["replay_dry_run_status"] == "passed"
    assert data["external_calls_enabled"] is False
    assert data["allow_auto_approve"] is False
    assert data["allow_production_result"] is False
    assert "unknown_field" not in json.dumps(data, ensure_ascii=False)

    history = client.get(
        f"/api/alignment/providers/{provider}/preflight",
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-history-after-post"},
    )
    history_body = assert_success(history, "preflight-history-after-post")
    assert any(item["preflight_uid"] == data["preflight_uid"] for item in history_body["data"]["items"])

    detail = client.get(
        f"/api/alignment/providers/preflight/{data['preflight_uid']}",
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-detail-after-post"},
    )
    detail_body = assert_success(detail, "preflight-detail-after-post")
    assert detail_body["data"]["preflight"]["preflight_uid"] == data["preflight_uid"]

    with app_module.app.app_context():
        policy = app_module.AlignmentProviderPolicy.query.filter_by(policy_uid=policy_uid).one()
        assert provider_governance.serialize_provider_policy(policy) == before_policy
        run = app_module.AlignmentProviderPreflightRun.query.filter_by(preflight_uid=data["preflight_uid"]).one()
        assert run.provider_name == provider
        assert run.check_status == "passed"


def test_provider_preflight_disabled_missing_and_malformed_requests_preserve_current_contract(
    client,
    app_module,
    teacher_token,
):
    disabled_provider = "external-llm-replay-v1"
    with app_module.app.app_context():
        upsert_policy(app_module, disabled_provider, enabled=False, status="disabled")

    disabled = client.post(
        f"/api/alignment/providers/{disabled_provider}/preflight",
        json={"course": "Preflight Route Course"},
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-disabled"},
    )
    disabled_body = assert_success(disabled, "preflight-disabled")
    assert disabled_body["data"]["preflight_uid"]
    assert disabled_body["data"]["policy_summary"]["status"] == "disabled"

    missing_provider = provider_name("missing-preflight-provider")
    missing = client.post(
        f"/api/alignment/providers/{missing_provider}/preflight",
        json={"course": "Preflight Route Course"},
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-missing-policy"},
    )
    missing_body = assert_success(missing, "preflight-missing-policy")
    assert missing_body["data"]["overall_ready"] is False
    assert "provider_policy_missing" in missing_body["data"]["blocking_reasons"]

    malformed = client.post(
        f"/api/alignment/providers/{missing_provider}/preflight",
        data="{",
        content_type="application/json",
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-malformed-json"},
    )
    malformed_body = assert_success(malformed, "preflight-malformed-json")
    assert malformed_body["data"]["overall_ready"] is False


def test_provider_preflight_no_network_and_no_usage_or_verification_side_effects(
    client,
    app_module,
    teacher_token,
    monkeypatch,
):
    provider = "external-llm-replay-v1"
    with app_module.app.app_context():
        upsert_policy(app_module, provider, allow_external_calls=True, replay_only=False)
        before = side_effect_counts(app_module)

    def blocked_connect(*args, **kwargs):
        raise AssertionError("provider preflight attempted external network access")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    response = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Route Course", "include_replay_dry_run": "true"},
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-no-network"},
    )
    body = assert_success(response, "preflight-no-network")
    assert body["data"]["check_results"]["network_called"] is False

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
    assert after["policies"] == before["policies"]
    assert after["preflights"] == before["preflights"] + 1
    assert after["audits"] == before["audits"] + 2
    assert after["usage"] == before["usage"]
    assert after["verification_runs"] == before["verification_runs"]


def test_provider_preflight_secret_like_payload_is_not_returned_stored_or_audited(
    client,
    app_module,
    teacher_token,
    monkeypatch,
):
    provider = "external-llm-replay-v1"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_PREFLIGHT_SECRET_VALUE_DO_NOT_RETURN")
    with app_module.app.app_context():
        upsert_policy(app_module, provider)

    response = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={
            "course": "Preflight Route Course",
            "include_replay_dry_run": True,
            "api_key": "TEST_PREFLIGHT_SECRET_VALUE_DO_NOT_RETURN",
            "secret": "TEST_PREFLIGHT_SECRET_VALUE_DO_NOT_RETURN",
            "authorization": "Bearer secret",
            "cookie": "Cookie: secret",
            "password": "super-secret-password",
            "private_key": "private key",
        },
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-secret"},
    )
    body = assert_success(response, "preflight-secret")
    assert_no_secret_values(body)

    with app_module.app.app_context():
        run = app_module.AlignmentProviderPreflightRun.query.filter_by(preflight_uid=body["data"]["preflight_uid"]).one()
        assert_no_secret_values({
            "policy_summary": run.policy_summary,
            "check_results": run.check_results,
            "blocking_reasons": run.blocking_reasons,
            "warnings": run.warnings,
        })
        completed = app_module.AuditRecord.query.filter_by(
            request_id="preflight-secret",
            event_type="provider_preflight_completed",
        ).one()
        serialized_audit = audit_records.serialize_audit_record(completed)
        assert_no_secret_values(serialized_audit)


def test_provider_preflight_audit_event_contract(client, app_module, teacher_token):
    provider = "external-llm-replay-v1"
    with app_module.app.app_context():
        upsert_policy(app_module, provider)

    ready = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Route Course"},
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-audit-ready"},
    )
    assert_success(ready, "preflight-audit-ready")

    missing_provider = provider_name("audit-preflight-missing-provider")
    failed = client.post(
        f"/api/alignment/providers/{missing_provider}/preflight",
        json={"course": "Preflight Route Course"},
        headers={**bearer(teacher_token), "X-Request-ID": "preflight-audit-failed"},
    )
    assert_success(failed, "preflight-audit-failed")

    with app_module.app.app_context():
        requested = app_module.AuditRecord.query.filter_by(
            request_id="preflight-audit-ready",
            event_type="provider_preflight_requested",
        ).one()
        completed = app_module.AuditRecord.query.filter_by(
            request_id="preflight-audit-ready",
            event_type="provider_preflight_completed",
        ).one()
        failed_audit = app_module.AuditRecord.query.filter_by(
            request_id="preflight-audit-failed",
            event_type="provider_preflight_failed",
        ).one()
        assert requested.target_type == "alignment_provider_preflight"
        assert completed.target_type == "alignment_provider_preflight"
        assert failed_audit.target_type == "alignment_provider_preflight"
        assert provider in completed.output_payload
        assert "provider_policy_missing" in failed_audit.error_code
        assert_no_secret_values({
            "requested": audit_records.serialize_audit_record(requested),
            "completed": audit_records.serialize_audit_record(completed),
            "failed": audit_records.serialize_audit_record(failed_audit),
        })
