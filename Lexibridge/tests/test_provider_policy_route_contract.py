import json
import socket
import uuid


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def provider_name(prefix="policy-route-provider"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


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


def policy_payload(**overrides):
    payload = {
        "provider_type": "replay_llm",
        "enabled": True,
        "status": "active",
        "replay_only": True,
        "allow_external_calls": False,
        "allow_attach_to_card": False,
        "allow_production_result": False,
        "allow_auto_approve": True,
        "require_human_review": False,
        "allowed_courses": ["Provider Policy Course"],
        "blocked_courses": ["Blocked Provider Course"],
        "allowed_roles": ["teacher", "admin"],
        "max_calls_per_day": 10,
        "max_calls_per_month": 50,
        "max_estimated_cost_per_call": 0.01,
        "max_estimated_cost_per_day": 0.05,
        "max_prompt_chars": 3000,
        "max_output_chars": 1500,
        "timeout_seconds": 25,
        "max_retries": 2,
    }
    payload.update(overrides)
    return payload


def count_provider_side_effects(app_module):
    return {
        "policies": app_module.AlignmentProviderPolicy.query.count(),
        "usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "preflights": app_module.AlignmentProviderPreflightRun.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "audits": app_module.AuditRecord.query.count(),
    }


def assert_no_secret_values(payload):
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in [
        "TEST_PROVIDER_POLICY_SECRET_VALUE",
        "Bearer secret",
        "Authorization",
        "Cookie",
        "private key",
        "api_key",
        "password",
    ]:
        assert forbidden not in serialized


def test_provider_policy_route_map_contract(app_module):
    actual = route_map(app_module)
    assert (
        actual[("/api/alignment/providers/<path:provider_name>/policy", "POST")]
        == "update_alignment_provider_policy_api"
    )
    assert (
        actual[("/api/alignment/providers/<path:provider_name>/policy", "GET")]
        == "get_alignment_provider_policy_api"
    )
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/alignment/providers/<path:provider_name>/policy" and "POST" in rule.methods
    ) == 1


def test_provider_policy_mutation_preserves_auth_role_contract(
    client,
    app_module,
    admin_token,
    teacher_token,
    student_token,
):
    provider = provider_name()
    unauth = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(),
        headers={"X-Request-ID": "policy-unauth"},
    )
    assert_error(unauth, 401, "policy-unauth")

    student = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(),
        headers={**bearer(student_token), "X-Request-ID": "policy-student"},
    )
    assert_error(student, 403, "policy-student")

    teacher = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(),
        headers={**bearer(teacher_token), "X-Request-ID": "policy-teacher"},
    )
    assert_error(teacher, 403, "policy-teacher")

    admin = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(),
        headers={**bearer(admin_token), "X-Request-ID": "policy-admin-create"},
    )
    body = assert_success(admin, "policy-admin-create")
    policy = body["data"]["policy"]
    assert body["data"]["created"] is True
    assert policy["provider_name"] == provider
    assert policy["enabled"] is True
    assert policy["status"] == "active"
    assert policy["allow_auto_approve"] is False
    assert policy["require_human_review"] is True


def test_provider_policy_mutation_updates_and_get_reflects_policy(client, app_module, admin_token, teacher_token):
    provider = provider_name()
    first = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(allowed_courses=["Course A"]),
        headers={**bearer(admin_token), "X-Request-ID": "policy-create"},
    )
    assert_success(first, "policy-create")

    second = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(enabled=False, status="deprecated", allowed_courses=["Course B"], max_calls_per_day=3),
        headers={**bearer(admin_token), "X-Request-ID": "policy-update"},
    )
    updated = assert_success(second, "policy-update")
    assert updated["data"]["created"] is False
    assert updated["data"]["policy"]["enabled"] is False
    assert updated["data"]["policy"]["status"] == "deprecated"
    assert updated["data"]["policy"]["allowed_courses"] == ["Course B"]
    assert updated["data"]["policy"]["max_calls_per_day"] == 3

    fetched = client.get(
        f"/api/alignment/providers/{provider}/policy",
        headers={**bearer(teacher_token), "X-Request-ID": "policy-get-after-update"},
    )
    fetched_body = assert_success(fetched, "policy-get-after-update")
    assert fetched_body["data"]["policy"]["policy_uid"] == updated["data"]["policy"]["policy_uid"]
    assert fetched_body["data"]["policy"]["allowed_courses"] == ["Course B"]


def test_provider_policy_mutation_freezes_current_payload_normalization(client, admin_token):
    provider = provider_name()
    response = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(
            status="not-a-real-status",
            max_calls_per_day=-5,
            max_prompt_chars=100,
            max_output_chars=100,
            timeout_seconds=999,
            max_retries=99,
            unknown_policy_field="ignored",
        ),
        headers={**bearer(admin_token), "X-Request-ID": "policy-normalized"},
    )
    body = assert_success(response, "policy-normalized")
    policy = body["data"]["policy"]
    assert policy["status"] == "disabled"
    assert policy["max_calls_per_day"] == 0
    assert policy["max_prompt_chars"] == 500
    assert policy["max_output_chars"] == 500
    assert policy["timeout_seconds"] == 120
    assert policy["max_retries"] == 3
    assert "unknown_policy_field" not in policy


def test_provider_policy_secret_like_payload_is_not_persisted_returned_or_audited(
    client,
    app_module,
    admin_token,
    monkeypatch,
):
    provider = provider_name()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_PROVIDER_POLICY_SECRET_VALUE")
    payload = policy_payload(
        api_key="TEST_PROVIDER_POLICY_SECRET_VALUE",
        secret="TEST_PROVIDER_POLICY_SECRET_VALUE",
        token="TEST_PROVIDER_POLICY_SECRET_VALUE",
        authorization="Bearer secret",
        cookie="Cookie: secret",
        password="TEST_PROVIDER_POLICY_SECRET_VALUE",
        private_key="private key",
        base_url="https://user:TEST_PROVIDER_POLICY_SECRET_VALUE@example.invalid",
    )
    response = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=payload,
        headers={**bearer(admin_token), "X-Request-ID": "policy-secret-payload"},
    )
    body = assert_success(response, "policy-secret-payload")
    assert_no_secret_values(body)

    with app_module.app.app_context():
        policy = app_module.AlignmentProviderPolicy.query.filter_by(provider_name=provider).one()
        serialized_policy = json.dumps({
            "allowed_courses": policy.allowed_courses,
            "blocked_courses": policy.blocked_courses,
            "allowed_roles": policy.allowed_roles,
            "status": policy.status,
        }, ensure_ascii=False)
        assert_no_secret_values(serialized_policy)
        audit = app_module.AuditRecord.query.filter_by(
            request_id="policy-secret-payload",
            event_type="provider_policy_created",
        ).one()
        assert_no_secret_values({
            "input_payload": audit.input_payload,
            "output_payload": audit.output_payload,
            "error_message": audit.error_message,
        })


def test_provider_policy_mutation_no_network_and_no_execution_side_effects(
    client,
    app_module,
    admin_token,
    monkeypatch,
):
    provider = provider_name()

    def blocked_connect(*args, **kwargs):
        raise AssertionError("provider policy mutation attempted external network access")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    with app_module.app.app_context():
        before = count_provider_side_effects(app_module)

    response = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(allow_external_calls=True, replay_only=False, status="active", enabled=True),
        headers={**bearer(admin_token), "X-Request-ID": "policy-no-network"},
    )
    assert_success(response, "policy-no-network")

    with app_module.app.app_context():
        after = count_provider_side_effects(app_module)
    assert after["policies"] == before["policies"] + 1
    assert after["audits"] == before["audits"] + 1
    assert after["usage"] == before["usage"]
    assert after["preflights"] == before["preflights"]
    assert after["verification_runs"] == before["verification_runs"]


def test_provider_policy_unauthorized_update_does_not_modify_existing_policy(
    client,
    app_module,
    admin_token,
    teacher_token,
):
    provider = provider_name()
    created = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(enabled=True, allowed_courses=["Allowed"]),
        headers={**bearer(admin_token), "X-Request-ID": "policy-authz-create"},
    )
    body = assert_success(created, "policy-authz-create")
    policy_uid = body["data"]["policy"]["policy_uid"]

    denied = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(enabled=False, allowed_courses=["Denied"]),
        headers={**bearer(teacher_token), "X-Request-ID": "policy-authz-denied"},
    )
    assert_error(denied, 403, "policy-authz-denied")

    with app_module.app.app_context():
        policy = app_module.AlignmentProviderPolicy.query.filter_by(policy_uid=policy_uid).one()
        assert policy.enabled is True
        assert json.loads(policy.allowed_courses) == ["Allowed"]


def test_provider_policy_audit_event_contract(client, app_module, admin_token):
    provider = provider_name()
    created = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(),
        headers={**bearer(admin_token), "X-Request-ID": "policy-audit-created"},
    )
    assert_success(created, "policy-audit-created")
    updated = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=policy_payload(enabled=False, status="disabled"),
        headers={**bearer(admin_token), "X-Request-ID": "policy-audit-updated"},
    )
    assert_success(updated, "policy-audit-updated")

    with app_module.app.app_context():
        created_audit = app_module.AuditRecord.query.filter_by(
            request_id="policy-audit-created",
            event_type="provider_policy_created",
        ).one()
        updated_audit = app_module.AuditRecord.query.filter_by(
            request_id="policy-audit-updated",
            event_type="provider_policy_updated",
        ).one()
        assert created_audit.target_type == "alignment_provider_policy"
        assert updated_audit.target_type == "alignment_provider_policy"
        assert provider in created_audit.output_payload
        assert provider in updated_audit.output_payload
