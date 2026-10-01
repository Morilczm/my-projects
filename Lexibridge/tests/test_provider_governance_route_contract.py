import json
import socket
import uuid

from services import provider_governance


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def provider_name(prefix="route-provider"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


def create_policy_usage_and_preflight(app_module, provider):
    policy, _ = provider_governance.create_or_update_provider_policy(
        app_module.db.session,
        app_module.AlignmentProviderPolicy,
        provider,
        {
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_external_calls": False,
            "allow_attach_to_card": False,
            "allowed_roles": ["teacher", "admin"],
            "allowed_courses": ["Provider Contract Course"],
            "max_calls_per_day": 10,
            "max_calls_per_month": 100,
            "max_estimated_cost_per_call": 0.01,
            "max_estimated_cost_per_day": 0.05,
        },
        now_fn=app_module.current_time_text,
        commit=True,
    )
    usage = provider_governance.record_provider_usage(
        app_module.db.session,
        app_module.AlignmentProviderUsageRecord,
        provider,
        input_summary={"course": "Provider Contract Course"},
        result_summary={
            "provider_type": "replay_llm",
            "provider_response_status": "replayed",
            "estimated_cost": {"estimated_input_tokens": 10, "estimated_output_tokens": 5, "estimated_cost": 0.0001},
        },
        audit_context={"request_id": "provider-contract-setup"},
        now_fn=app_module.current_time_text,
        commit=True,
    )
    preflight = app_module.AlignmentProviderPreflightRun(
        provider_name=provider,
        provider_type="replay_llm",
        policy_uid=policy.policy_uid,
        course="Provider Contract Course",
        check_status="passed",
        overall_ready=True,
        external_calls_enabled=False,
        replay_only=True,
        api_key_present=True,
        api_key_env_name="DEEPSEEK_API_KEY",
        policy_summary=provider_governance.serialize_provider_policy(policy),
        check_results={"network_called": False},
        blocking_reasons=[],
        warnings=[],
        replay_dry_run_status="passed",
        max_calls_per_day=10,
        max_calls_per_month=100,
        require_human_review=True,
        allow_auto_approve=False,
        allow_production_result=False,
    )
    app_module.db.session.add(preflight)
    app_module.db.session.commit()
    return policy, usage, preflight


def assert_success_contract(response, request_id):
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "success"
    assert body["request_id"] == request_id
    assert "data" in body
    return body


def assert_stable_forbidden(response, request_id):
    assert response.status_code == 403, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "error"
    assert body["request_id"] == request_id
    assert "message" in body


def assert_no_secret_values(payload):
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "TEST_PROVIDER_SECRET_VALUE_DO_NOT_RETURN" not in serialized
    assert "Bearer secret" not in serialized
    assert "Authorization" not in serialized
    assert "Cookie" not in serialized
    assert "private key" not in serialized.lower()


def test_provider_governance_route_map_contract(app_module):
    expected = {
        ("/api/alignment/providers", "GET"): "list_alignment_providers_api",
        ("/api/alignment/providers/<path:provider_name>/policy", "GET"): "get_alignment_provider_policy_api",
        ("/api/alignment/providers/<path:provider_name>/usage", "GET"): "list_alignment_provider_usage_api",
        ("/api/alignment/providers/preflight/<preflight_uid>", "GET"): "get_alignment_provider_preflight_api",
        ("/api/alignment/providers/<path:provider_name>/preflight", "GET"): "list_alignment_provider_preflights_api",
        ("/api/alignment/providers/<path:provider_name>/policy", "POST"): "update_alignment_provider_policy_api",
        ("/api/alignment/providers/<path:provider_name>/preflight", "POST"): "run_alignment_provider_preflight_api",
    }
    actual = route_map(app_module)
    for key, endpoint in expected.items():
        assert actual.get(key) == endpoint
        assert sum(1 for rule in app_module.app.url_map.iter_rules() if rule.rule == key[0] and key[1] in rule.methods) == 1


def test_provider_governance_read_routes_preserve_auth_and_role_contract(
    client,
    app_module,
    teacher_token,
    admin_token,
    student_token,
):
    provider = provider_name()
    with app_module.app.app_context():
        _, _, preflight = create_policy_usage_and_preflight(app_module, provider)
        preflight_uid = preflight.preflight_uid

    unauth = client.get("/api/alignment/providers", headers={"X-Request-ID": "provider-unauth"})
    assert unauth.status_code == 401
    assert unauth.get_json()["request_id"] == "provider-unauth"

    student = client.get(
        "/api/alignment/providers",
        headers={**bearer(student_token), "X-Request-ID": "provider-student"},
    )
    assert_stable_forbidden(student, "provider-student")

    calls = [
        ("providers", "/api/alignment/providers", "provider-list"),
        ("policy", f"/api/alignment/providers/{provider}/policy", "provider-policy"),
        ("usage", f"/api/alignment/providers/{provider}/usage?page=1&per_page=10", "provider-usage"),
        ("preflight_detail", f"/api/alignment/providers/preflight/{preflight_uid}", "provider-preflight-detail"),
        ("preflight_list", f"/api/alignment/providers/{provider}/preflight?page=1&per_page=10", "provider-preflight-list"),
    ]
    for _, path, request_id in calls:
        body = assert_success_contract(
            client.get(path, headers={**bearer(teacher_token), "X-Request-ID": request_id}),
            request_id,
        )
        assert_no_secret_values(body)

    admin_body = assert_success_contract(
        client.get(f"/api/alignment/providers/{provider}/policy", headers={**bearer(admin_token), "X-Request-ID": "provider-admin"}),
        "provider-admin",
    )
    assert admin_body["data"]["policy"]["provider_name"] == provider


def test_provider_governance_read_routes_do_not_write_or_execute_network(
    client,
    app_module,
    teacher_token,
    monkeypatch,
):
    provider = provider_name()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_PROVIDER_SECRET_VALUE_DO_NOT_RETURN")
    with app_module.app.app_context():
        _, _, preflight = create_policy_usage_and_preflight(app_module, provider)
        preflight_uid = preflight.preflight_uid
        before = {
            "policies": app_module.AlignmentProviderPolicy.query.count(),
            "usage": app_module.AlignmentProviderUsageRecord.query.count(),
            "preflights": app_module.AlignmentProviderPreflightRun.query.count(),
            "verification_runs": app_module.AlignmentVerificationRun.query.count(),
            "audits": app_module.AuditRecord.query.count(),
        }

    def blocked_connect(*args, **kwargs):
        raise AssertionError("provider governance GET route attempted external network access")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    responses = [
        client.get("/api/alignment/providers", headers={**bearer(teacher_token), "X-Request-ID": "provider-nowrite-list"}),
        client.get(
            f"/api/alignment/providers/{provider}/policy",
            headers={**bearer(teacher_token), "X-Request-ID": "provider-nowrite-policy"},
        ),
        client.get(
            f"/api/alignment/providers/{provider}/usage?course=Provider%20Contract%20Course",
            headers={**bearer(teacher_token), "X-Request-ID": "provider-nowrite-usage"},
        ),
        client.get(
            f"/api/alignment/providers/preflight/{preflight_uid}",
            headers={**bearer(teacher_token), "X-Request-ID": "provider-nowrite-preflight-detail"},
        ),
        client.get(
            f"/api/alignment/providers/{provider}/preflight?course=Provider%20Contract%20Course",
            headers={**bearer(teacher_token), "X-Request-ID": "provider-nowrite-preflight-list"},
        ),
    ]
    for response in responses:
        assert response.status_code == 200, response.get_data(as_text=True)
        assert_no_secret_values(response.get_json())

    with app_module.app.app_context():
        after = {
            "policies": app_module.AlignmentProviderPolicy.query.count(),
            "usage": app_module.AlignmentProviderUsageRecord.query.count(),
            "preflights": app_module.AlignmentProviderPreflightRun.query.count(),
            "verification_runs": app_module.AlignmentVerificationRun.query.count(),
            "audits": app_module.AuditRecord.query.count(),
        }
    assert after == before


def test_provider_preflight_missing_detail_error_contract(client, teacher_token):
    response = client.get(
        "/api/alignment/providers/preflight/not-a-real-preflight",
        headers={**bearer(teacher_token), "X-Request-ID": "provider-preflight-missing"},
    )
    assert response.status_code == 404
    body = response.get_json()
    assert body["status"] == "error"
    assert body["request_id"] == "provider-preflight-missing"
    assert body["audit_error_code"] == "provider_preflight_not_found"


def test_openapi_provider_governance_methods_match_route_map(app_module):
    actual = route_map(app_module)
    assert actual[("/api/alignment/providers", "GET")] == "list_alignment_providers_api"
    assert actual[("/api/alignment/providers/<path:provider_name>/policy", "GET")] == "get_alignment_provider_policy_api"
    assert actual[("/api/alignment/providers/<path:provider_name>/usage", "GET")] == "list_alignment_provider_usage_api"
    assert actual[("/api/alignment/providers/<path:provider_name>/preflight", "GET")] == "list_alignment_provider_preflights_api"
    assert actual[("/api/alignment/providers/preflight/<preflight_uid>", "GET")] == "get_alignment_provider_preflight_api"
