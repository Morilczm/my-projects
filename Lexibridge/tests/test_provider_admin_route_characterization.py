import json
import socket
from pathlib import Path

import pytest
import yaml

from provider_admin_state_isolation import (
    capture_provider_admin_state,
    restore_provider_admin_state,
)


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4F"

ROUTE_CONTRACT = {
    ("/api/admin/alignment-runs", "GET"): "admin_alignment_runs",
    ("/api/admin/ai/providers", "GET"): "admin_ai_providers",
    ("/api/admin/ai/models", "GET"): "admin_ai_models",
    ("/api/admin/ai/prompts", "GET"): "admin_ai_prompts",
    ("/api/admin/ai/prompts", "POST"): "admin_ai_prompts",
    ("/api/admin/ai/calls", "GET"): "admin_ai_calls",
    ("/api/admin/ai/usage", "GET"): "admin_ai_usage",
    ("/api/admin/ai/health", "GET"): "admin_ai_health",
    ("/api/admin/ai/healthcheck", "POST"): "admin_ai_healthcheck",
    ("/api/alignment/run", "POST"): "run_alignment",
    ("/api/alignment/runs", "GET"): "alignment_runs",
    ("/api/alignment/runs/<int:run_id>", "GET"): "alignment_run_detail",
}

ADMIN_AI_GETS = [
    "/api/admin/ai/providers",
    "/api/admin/ai/models",
    "/api/admin/ai/prompts",
    "/api/admin/ai/calls",
    "/api/admin/ai/usage",
    "/api/admin/ai/health",
]


@pytest.fixture(autouse=True)
def isolate_provider_admin_state(app_module):
    snapshot = capture_provider_admin_state(app_module)
    restore_provider_admin_state(app_module, snapshot)
    yield
    restore_provider_admin_state(app_module, snapshot)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError(f"network access attempted: args={args!r}")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


def side_effect_counts(app_module):
    return {
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_policy": app_module.AlignmentProviderPolicy.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "ai_provider_config": app_module.AIProviderConfig.query.count(),
        "ai_models": app_module.AIModelRegistry.query.count(),
        "prompts": app_module.PromptTemplate.query.count(),
        "ai_call_logs": app_module.AICallLog.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
    }


def assert_no_sentinel(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    forbidden = [
        SENTINEL,
        "Authorization",
        "Cookie",
        "private key",
        "api_key",
        "bearer ",
        "password",
        "secret",
    ]
    for item in forbidden:
        assert item.lower() not in serialized.lower()


def test_provider_admin_route_map_contract(app_module):
    actual = route_map(app_module)
    for key, endpoint in ROUTE_CONTRACT.items():
        assert actual.get(key) == endpoint
        assert sum(
            1
            for rule in app_module.app.url_map.iter_rules()
            if rule.rule == key[0] and key[1] in rule.methods
        ) == 1


def test_admin_alignment_runs_contract_and_permissions(app_module, client, admin_token, teacher_token, student_token):
    with app_module.app.app_context():
        run = app_module.AlignmentRun(
            triggered_by=1,
            provider="mock",
            model_name="mock",
            ai_provider="mock",
            ai_provider_mode="mock",
            ai_model="mock",
            prompt_key="term_alignment",
            prompt_version="v1",
            retrieval_version="test",
            term_count=2,
            status="completed",
            started_at=app_module.current_time_text(),
            finished_at=app_module.current_time_text(),
        )
        app_module.db.session.add(run)
        app_module.db.session.commit()
        before = side_effect_counts(app_module)

    unauth = client.get("/api/admin/alignment-runs")
    assert unauth.status_code == 401
    student = client.get("/api/admin/alignment-runs", headers=bearer(student_token))
    assert student.status_code == 403
    teacher = client.get("/api/admin/alignment-runs", headers=bearer(teacher_token))
    assert teacher.status_code == 403

    response = client.get("/api/admin/alignment-runs", headers={**bearer(admin_token), "X-Request-ID": "admin-runs"})
    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"status", "runs"}
    assert payload["status"] == "success"
    assert "request_id" not in payload
    assert payload["runs"]
    first_run = payload["runs"][0]
    assert {
        "id",
        "provider",
        "model_name",
        "ai_provider",
        "ai_provider_mode",
        "prompt_version",
        "retrieval_version",
        "status",
        "metrics",
        "error_message",
    } <= set(first_run)
    assert_no_sentinel(payload)

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after == before


def test_admin_ai_provider_views_contract_permissions_secret_redaction_and_no_network(
    app_module,
    client,
    admin_token,
    teacher_token,
    student_token,
    monkeypatch,
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SENTINEL)
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    no_network(monkeypatch)

    for path in ADMIN_AI_GETS:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=bearer(student_token)).status_code == 403
        assert client.get(path, headers=bearer(teacher_token)).status_code == 403

    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
        app_module.db.session.commit()
        seeded_before = side_effect_counts(app_module)

    responses = {}
    for path in ADMIN_AI_GETS:
        response = client.get(path, headers={**bearer(admin_token), "X-Request-ID": f"char-{path.rsplit('/', 1)[-1]}"})
        assert response.status_code == 200, response.get_data(as_text=True)
        payload = response.get_json()
        responses[path] = payload
        assert payload["status"] == "success"
        assert "message" in payload
        assert "data" in payload
        assert "request_id" not in payload
        assert_no_sentinel(payload)

    provider_data = responses["/api/admin/ai/providers"]["data"]
    assert set(provider_data) == {"items", "current"}
    assert provider_data["items"]
    provider_item = provider_data["items"][0]
    assert {
        "provider_name",
        "provider_mode",
        "base_url",
        "default_model",
        "is_enabled",
        "is_default",
        "health_status",
    } <= set(provider_item)
    assert "api_key" not in provider_item

    assert "items" in responses["/api/admin/ai/models"]["data"]
    assert "items" in responses["/api/admin/ai/prompts"]["data"]
    assert "items" in responses["/api/admin/ai/calls"]["data"]
    assert {"summary", "recent"} <= set(responses["/api/admin/ai/usage"]["data"])
    assert "items" in responses["/api/admin/ai/health"]["data"]

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["verification_runs"] == seeded_before["verification_runs"]
        assert after["provider_usage"] == seeded_before["provider_usage"]
        assert after["provider_policy"] == seeded_before["provider_policy"]
        assert after["provider_preflight"] == seeded_before["provider_preflight"]
        assert after["alignment_runs"] == seeded_before["alignment_runs"]
        assert after["audit_records"] == seeded_before["audit_records"]
        assert after["ai_provider_config"] == seeded_before["ai_provider_config"]
        assert after["ai_models"] == seeded_before["ai_models"]
        assert after["prompts"] == seeded_before["prompts"]


def test_admin_ai_get_handlers_include_registry_seed_boundary():
    source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    configuration_source = (
        ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py"
    ).read_text(encoding="utf-8")
    for handler_name in [
        "admin_ai_providers",
        "admin_ai_models",
        "admin_ai_prompts",
    ]:
        assert f"def {handler_name}(" in configuration_source
    assert "seed_registry(user.id)" in configuration_source
    assert "registry_seed_service(" in configuration_source
    assert "ensure_ai_registry_seed" not in configuration_source
    assert "prompt_post_handler" not in configuration_source
    assert "LegacyPromptMutationRequest.from_payload" in configuration_source
    assert "prompt_mutation_service(" in configuration_source
    assert "def admin_ai_prompts_post_handler(user):" not in source
    assert "register_legacy_provider_admin_configuration_routes(" in source
    assert "registry_seed_service=ensure_legacy_provider_registry_seed" in source
    assert "prompt_mutation_service=execute_legacy_prompt_mutation" in source
    assert "prompt_mutation_dependencies=legacy_prompt_mutation_dependencies()" in source
    module_source = (ROOT / "backend" / "routes" / "legacy_provider_admin_observability.py").read_text(encoding="utf-8")
    assert "def admin_ai_health(" in module_source
    assert "registry_seed_service(owner_user_id=user.id)" in module_source
    assert "registry_seed_service=ensure_ai_registry_seed" in source


def test_admin_ai_healthcheck_local_path_writes_health_without_network_or_provider_usage(
    app_module,
    client,
    admin_token,
    teacher_token,
    student_token,
    monkeypatch,
):
    no_network(monkeypatch)
    assert client.post("/api/admin/ai/healthcheck", json={}).status_code == 401
    assert client.post("/api/admin/ai/healthcheck", json={}, headers=bearer(student_token)).status_code == 403
    assert client.post("/api/admin/ai/healthcheck", json={}, headers=bearer(teacher_token)).status_code == 403

    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
        app_module.db.session.commit()
        before = side_effect_counts(app_module)

    response = client.post(
        "/api/admin/ai/healthcheck",
        json={"live_probe": False},
        headers={**bearer(admin_token), "X-Request-ID": "provider-healthcheck"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert "items" in payload["data"]
    assert_no_sentinel(payload)

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_policy"] == before["provider_policy"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["alignment_runs"] == before["alignment_runs"]
        assert after["ai_provider_config"] == before["ai_provider_config"]


def test_legacy_alignment_run_routes_contract_and_frontend_cutover(app_module, client, teacher_token, student_token):
    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    formal_frontend = (ROOT / "frontend" / "js" / "formal-workflow.js").read_text(encoding="utf-8")
    assert 'api("/api/alignment/runs")' in frontend
    assert 'api("/api/alignment/run"' not in frontend
    assert '"/api/alignment/run"' not in formal_frontend
    assert '"/api/document-alignment-runs"' in formal_frontend
    assert 'api("/api/admin/ai/providers")' in frontend
    assert 'api("/api/admin/ai/health")' in frontend

    with app_module.app.app_context():
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").one()
        run = app_module.AlignmentRun(
            triggered_by=teacher.id,
            provider="mock",
            model_name="mock",
            ai_provider="mock",
            ai_provider_mode="mock",
            ai_model="mock",
            prompt_key="term_alignment",
            prompt_version="v1",
            retrieval_version="test",
            term_count=1,
            status="completed",
        )
        app_module.db.session.add(run)
        app_module.db.session.commit()
        run_id = run.id
        before = side_effect_counts(app_module)

    list_response = client.get("/api/alignment/runs?page=1&page_size=5", headers=bearer(teacher_token))
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["status"] == "success"
    assert {"items", "pagination"} <= set(list_payload["data"])
    assert "request_id" not in list_payload

    detail_response = client.get(f"/api/alignment/runs/{run_id}", headers=bearer(teacher_token))
    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["status"] == "success"
    assert set(detail_payload) == {"status", "run"}
    assert detail_payload["run"]["id"] == run_id

    student_list = client.get("/api/alignment/runs", headers=bearer(student_token))
    assert student_list.status_code == 200
    assert student_list.get_json()["status"] == "success"

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after == before


def test_provider_admin_openapi_and_external_health_risk_are_characterized():
    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    paths = contract["paths"]
    for path in [
        "/api/admin/ai/providers",
        "/api/admin/ai/models",
        "/api/admin/ai/prompts",
        "/api/admin/ai/calls",
        "/api/admin/ai/usage",
        "/api/admin/ai/health",
        "/api/admin/ai/healthcheck",
        "/api/alignment/run",
        "/api/alignment/runs",
        "/api/alignment/runs/{run_id}",
    ]:
        assert path in paths
    assert "/api/admin/alignment-runs" not in paths

    health_source = (ROOT / "backend" / "services" / "ai_health.py").read_text(encoding="utf-8")
    assert "if not live_probe" in health_source
    assert "provider.call(" in health_source
