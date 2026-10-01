import importlib
import json
import socket
import urllib.request
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4H"

LEGACY_ADMIN_ROUTES = {
    ("/api/admin/ai/providers", "GET"): "admin_ai_providers",
    ("/api/admin/ai/models", "GET"): "admin_ai_models",
    ("/api/admin/ai/prompts", "GET"): "admin_ai_prompts",
    ("/api/admin/ai/prompts", "POST"): "admin_ai_prompts",
    ("/api/admin/ai/calls", "GET"): "admin_ai_calls",
    ("/api/admin/ai/usage", "GET"): "admin_ai_usage",
    ("/api/admin/ai/health", "GET"): "admin_ai_health",
    ("/api/admin/ai/healthcheck", "POST"): "admin_ai_healthcheck",
}

LEGACY_ADMIN_GETS = [
    "/api/admin/ai/providers",
    "/api/admin/ai/models",
    "/api/admin/ai/prompts",
    "/api/admin/ai/calls",
    "/api/admin/ai/usage",
    "/api/admin/ai/health",
]

SEEDING_GETS = {
    "/api/admin/ai/providers",
    "/api/admin/ai/models",
    "/api/admin/ai/prompts",
    "/api/admin/ai/health",
}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError(f"network access attempted: args={args!r}")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    for module_name in ("requests", "httpx"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        if hasattr(module, "request"):
            monkeypatch.setattr(module, "request", blocked)


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
    assert SENTINEL not in serialized
    forbidden = [
        "api_key",
        "authorization",
        "cookie",
        "private_key",
        "bearer ",
    ]
    lowered = serialized.lower()
    for item in forbidden:
        assert item not in lowered


def reset_legacy_registry_tables(app_module):
    app_module.AIProviderConfig.query.delete()
    app_module.AIModelRegistry.query.delete()
    app_module.PromptTemplate.query.delete()
    app_module.db.session.commit()


def test_legacy_admin_ai_route_map_openapi_and_frontend_dependencies(app_module):
    actual = route_map(app_module)
    for key, endpoint in LEGACY_ADMIN_ROUTES.items():
        assert actual.get(key) == endpoint
        assert sum(
            1
            for rule in app_module.app.url_map.iter_rules()
            if rule.rule == key[0] and key[1] in rule.methods
        ) == 1

    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    for path in {
        "/api/admin/ai/providers",
        "/api/admin/ai/models",
        "/api/admin/ai/prompts",
        "/api/admin/ai/calls",
        "/api/admin/ai/usage",
        "/api/admin/ai/health",
        "/api/admin/ai/healthcheck",
    }:
        assert path in contract["paths"]

    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for path in LEGACY_ADMIN_GETS:
        assert f'api("{path}")' in frontend
    assert "/api/admin/ai/healthcheck" not in frontend


def test_legacy_admin_ai_get_permissions_seed_side_effects_and_idempotency(
    app_module,
    client,
    admin_token,
    teacher_token,
    student_token,
    monkeypatch,
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SENTINEL)
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    monkeypatch.setattr(app_module, "DEEPSEEK_API_KEY", SENTINEL)
    monkeypatch.setattr(app_module, "OPENAI_API_KEY", SENTINEL)
    no_network(monkeypatch)

    for path in LEGACY_ADMIN_GETS:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=bearer(student_token)).status_code == 403
        assert client.get(path, headers=bearer(teacher_token)).status_code == 403

    with app_module.app.app_context():
        reset_legacy_registry_tables(app_module)
        before = side_effect_counts(app_module)
        assert before["ai_provider_config"] == 0
        assert before["ai_models"] == 0
        assert before["prompts"] == 0

    first = client.get(
        "/api/admin/ai/providers",
        headers={**bearer(admin_token), "X-Request-ID": "legacy-provider-seed"},
    )
    assert first.status_code == 200
    payload = first.get_json()
    assert payload["status"] == "success"
    assert "request_id" not in payload
    assert set(payload["data"]) == {"items", "current"}
    assert payload["data"]["items"]
    assert_no_sentinel(payload)

    with app_module.app.app_context():
        after_first_seed = side_effect_counts(app_module)
        # The legacy GET handler calls ensure_ai_registry_seed(), which flushes
        # default rows for the response but does not commit them.
        assert after_first_seed["ai_provider_config"] == before["ai_provider_config"]
        assert after_first_seed["ai_models"] == before["ai_models"]
        assert after_first_seed["prompts"] == before["prompts"]
        assert after_first_seed["verification_runs"] == before["verification_runs"]
        assert after_first_seed["provider_usage"] == before["provider_usage"]
        assert after_first_seed["provider_policy"] == before["provider_policy"]
        assert after_first_seed["provider_preflight"] == before["provider_preflight"]
        assert after_first_seed["alignment_runs"] == before["alignment_runs"]
        assert after_first_seed["audit_records"] == before["audit_records"]

    responses = {}
    for path in LEGACY_ADMIN_GETS:
        response = client.get(path, headers={**bearer(admin_token), "X-Request-ID": f"legacy-{path.rsplit('/', 1)[-1]}"})
        assert response.status_code == 200, response.get_data(as_text=True)
        responses[path] = response.get_json()
        assert responses[path]["status"] == "success"
        assert "data" in responses[path]
        assert "request_id" not in responses[path]
        assert_no_sentinel(responses[path])

    assert "items" in responses["/api/admin/ai/models"]["data"]
    assert "items" in responses["/api/admin/ai/prompts"]["data"]
    assert "items" in responses["/api/admin/ai/calls"]["data"]
    assert {"summary", "recent"} <= set(responses["/api/admin/ai/usage"]["data"])
    assert "items" in responses["/api/admin/ai/health"]["data"]

    with app_module.app.app_context():
        after_repeated_gets = side_effect_counts(app_module)
        assert after_repeated_gets == after_first_seed


def test_legacy_admin_ai_prompt_post_is_mutation_not_readonly(
    app_module,
    client,
    admin_token,
    teacher_token,
    student_token,
    monkeypatch,
):
    no_network(monkeypatch)
    assert client.post("/api/admin/ai/prompts", json={}).status_code == 401
    assert client.post("/api/admin/ai/prompts", json={}, headers=bearer(student_token)).status_code == 403
    assert client.post("/api/admin/ai/prompts", json={}, headers=bearer(teacher_token)).status_code == 403

    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
        app_module.db.session.commit()
        before = side_effect_counts(app_module)

    invalid = client.post("/api/admin/ai/prompts", json={}, headers=bearer(admin_token))
    assert invalid.status_code == 400
    assert invalid.get_json()["error_code"] == "VALIDATION_ERROR"

    prompt_key = "legacy_admin_9c4h"
    payload = {
        "prompt_key": prompt_key,
        "prompt_version": "v1",
        "task_type": "term_alignment",
        "language": "bilingual",
        "json_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
        "is_active": True,
        "is_default": False,
        "notes": "9C.4H compatibility fixture",
    }
    response = client.post(
        "/api/admin/ai/prompts",
        json=payload,
        headers={**bearer(admin_token), "X-Request-ID": "legacy-prompt-post"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["data"]["prompt_key"] == prompt_key
    assert "request_id" not in body
    assert_no_sentinel(body)

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["prompts"] == before["prompts"] + 1
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_policy"] == before["provider_policy"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["alignment_runs"] == before["alignment_runs"]
        assert after["ai_call_logs"] == before["ai_call_logs"]
        assert after["audit_records"] == before["audit_records"]


def test_legacy_admin_ai_healthcheck_local_paths_write_health_only_without_network(
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
        reset_legacy_registry_tables(app_module)
        app_module.ensure_ai_registry_seed()
        for config in app_module.AIProviderConfig.query.all():
            config.provider_mode = "mock"
            config.provider_name = "mock"
            config.default_model = "mock"
            config.is_enabled = True
            config.is_default = True
            config.health_status = "unknown"
        app_module.db.session.commit()
        before = side_effect_counts(app_module)

    for live_probe in (False, True):
        response = client.post(
            "/api/admin/ai/healthcheck",
            json={"live_probe": live_probe},
            headers={**bearer(admin_token), "X-Request-ID": f"legacy-health-{live_probe}"},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "success"
        assert "items" in payload["data"]
        assert payload["data"]["items"][0]["provider_mode"] == "mock"
        if live_probe:
            assert payload["data"]["items"][0]["health_status"] == "unknown"
            assert payload["data"]["items"][0]["error_code"] == "LEGACY_LIVE_PROBE_DISABLED"
        else:
            assert payload["data"]["items"][0]["health_status"] == "healthy"
        assert "request_id" not in payload
        assert_no_sentinel(payload)

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        # Healthcheck first ensures the env-selected provider and then commits
        # provider health fields, so the env default seed is persisted here.
        assert after["ai_provider_config"] >= before["ai_provider_config"]
        assert after["ai_models"] >= before["ai_models"]
        assert after["prompts"] == before["prompts"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_policy"] == before["provider_policy"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["alignment_runs"] == before["alignment_runs"]
        assert after["audit_records"] == before["audit_records"]
        statuses = {
            config.provider_mode: config.health_status
            for config in app_module.AIProviderConfig.query.all()
        }
        assert statuses["mock"] == "unknown"


def test_legacy_admin_ai_healthcheck_live_probe_disabled_without_network(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    captured_route_calls = []
    original_evaluate = app_module.evaluate_legacy_provider_local_readiness

    def readiness_spy(*, request, provider):
        captured_route_calls.append({
            "provider_name": provider.provider_name,
            "provider_mode": provider.provider_mode,
            "model_name": provider.model_name,
            "live_probe": request.live_probe_requested,
            "credential_present": provider.credential_present,
        })
        return original_evaluate(request=request, provider=provider)

    with app_module.app.app_context():
        reset_legacy_registry_tables(app_module)
        live_config = app_module.AIProviderConfig(
            provider_name="deepseek",
            provider_mode="live",
            base_url="https://example.invalid",
            default_model="deepseek-chat",
            is_enabled=True,
            is_default=True,
            health_status="unknown",
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add(live_config)
        app_module.db.session.commit()
        before = side_effect_counts(app_module)

    monkeypatch.setattr(app_module, "evaluate_legacy_provider_local_readiness", readiness_spy)
    response = client.post(
        "/api/admin/ai/healthcheck",
        json={"live_probe": True},
        headers={**bearer(admin_token), "X-Request-ID": "legacy-live-probe"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    live_item = next(item for item in payload["data"]["items"] if item["provider_name"] == "deepseek")
    assert live_item["health_status"] == "unknown"
    assert live_item["error_code"] == "LEGACY_LIVE_PROBE_DISABLED"
    live_calls = [item for item in captured_route_calls if item["provider_name"] == "deepseek"]
    assert live_calls == [{
        "provider_name": "deepseek",
        "provider_mode": "live",
        "model_name": "deepseek-chat",
        "live_probe": True,
        "credential_present": live_calls[0]["credential_present"],
    }]
    assert isinstance(live_calls[0]["credential_present"], bool)
    assert_no_sentinel(payload)

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        # The route may persist the env-selected default provider before
        # running health checks over all enabled configs.
        assert after["ai_provider_config"] >= before["ai_provider_config"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_policy"] == before["provider_policy"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["alignment_runs"] == before["alignment_runs"]
        assert after["audit_records"] == before["audit_records"]


def test_ai_health_service_live_probe_calls_provider_adapter_without_real_network(monkeypatch):
    ai_health = importlib.import_module("services.ai_health")
    ai_registry = importlib.import_module("services.ai_registry")
    captured = []

    class ProviderSpy:
        def call(self, task_type, prompt_text, input_payload, json_schema=None):
            captured.append({
                "task_type": task_type,
                "prompt_text": prompt_text,
                "input_payload": input_payload,
                "json_schema": json_schema,
            })
            return {"status": "success", "result": {"ok": True}}

    def provider_from_selection_spy(selection):
        assert selection.provider_name == "deepseek"
        assert selection.provider_mode == "live"
        return ProviderSpy()

    monkeypatch.setattr(ai_health, "provider_from_selection", provider_from_selection_spy)
    selection = ai_registry.ProviderSelection(
        provider_name="deepseek",
        provider_mode="live",
        model_name="deepseek-chat",
        api_key="sk-live-probe-risk-fixture",
        base_url="https://example.invalid",
    )
    skipped = ai_health.healthcheck_provider(selection, live_probe=False)
    assert skipped["health_status"] == "unknown"
    assert captured == []

    result = ai_health.healthcheck_provider(selection, live_probe=True)
    assert result["health_status"] == "healthy"
    assert captured
    assert captured[0]["task_type"] == "term_alignment"
    assert captured[0]["input_payload"]["english_term"] == "Health Check"


def test_legacy_admin_ai_source_boundaries_are_static():
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
    assert "healthcheck_provider" not in module_source
    assert "registry_seed_service=ensure_ai_registry_seed" in source
    health_source = (
        ROOT / "backend" / "routes" / "legacy_provider_admin_healthcheck.py"
    ).read_text(encoding="utf-8")
    assert "register_legacy_provider_admin_healthcheck_routes(" in source
    assert "def admin_ai_healthcheck(" not in source
    assert '@app.route("/api/admin/ai/healthcheck", methods=["POST"])' not in source
    assert "local_readiness_service(" in health_source
    assert "LegacyProviderLocalReadinessProvider(" in health_source
    assert "credential_present=bool(credential_presence_resolver(config))" in health_source
    assert "core.db.session.commit()" in health_source
    assert "healthcheck_provider" not in health_source
