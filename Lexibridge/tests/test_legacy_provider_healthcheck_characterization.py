import importlib
import json
import socket
import urllib.request
from pathlib import Path

import pytest
import yaml

from provider_admin_state_isolation import (
    capture_provider_admin_state,
    restore_provider_admin_state,
)


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4L1"


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


def handler_block():
    source = (ROOT / "backend" / "routes" / "legacy_provider_admin_healthcheck.py").read_text(encoding="utf-8")
    start = source.index("    def admin_ai_healthcheck(")
    end = source.index("\n    app.add_url_rule", start + 1)
    return source[start:end]


def side_effect_counts(app_module):
    return {
        "provider_config": app_module.AIProviderConfig.query.count(),
        "models": app_module.AIModelRegistry.query.count(),
        "prompts": app_module.PromptTemplate.query.count(),
        "ai_calls": app_module.AICallLog.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
    }


def reset_legacy_registry_tables(app_module):
    app_module.AIProviderConfig.query.delete()
    app_module.AIModelRegistry.query.delete()
    app_module.PromptTemplate.query.delete()
    app_module.db.session.commit()


def assert_no_sentinel(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert SENTINEL not in serialized
    lowered = serialized.lower()
    for term in ("authorization", "cookie", "private_key", "bearer "):
        assert term not in lowered


def test_healthcheck_route_contract_openapi_and_static_handler_boundary(app_module):
    actual = route_map(app_module)
    assert actual[("/api/admin/ai/healthcheck", "POST")] == "admin_ai_healthcheck"
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/admin/ai/healthcheck" and "POST" in rule.methods
    ) == 1

    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    healthcheck = contract["paths"]["/api/admin/ai/healthcheck"]["post"]
    assert healthcheck["requestBody"]["required"] is False
    assert "live_probe" in healthcheck["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert sorted(healthcheck["responses"]) == ["200", "403"]

    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "/api/admin/ai/healthcheck" not in frontend

    app_source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    assert '@app.route("/api/admin/ai/healthcheck", methods=["POST"])' not in app_source
    assert "def admin_ai_healthcheck(" not in app_source
    assert "register_legacy_provider_admin_healthcheck_routes(" in app_source

    block = handler_block()
    assert len(block.splitlines()) == 27
    assert "seed_registry(user.id)" in block
    assert "local_readiness_service(" in block
    assert "LegacyProviderLocalReadinessProvider(" in block
    assert "credential_present=bool(credential_presence_resolver(config))" in block
    assert "healthcheck_provider" not in block
    assert "core.db.session.commit()" in block
    assert "rollback" not in block
    assert "AuditRecord" not in block
    assert "AICallLog" not in block
    assert "AlignmentProviderUsageRecord" not in block


def test_healthcheck_permissions_payload_parsing_and_legacy_envelope(
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

    response = client.post(
        "/api/admin/ai/healthcheck",
        json={"live_probe": False, "unknown_field": SENTINEL},
        headers={**bearer(admin_token), "X-Request-ID": "legacy-health-unknown-field"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"status", "message", "data"}
    assert payload["status"] == "success"
    assert "items" in payload["data"]
    assert "request_id" not in payload
    assert_no_sentinel(payload)

    malformed = client.post(
        "/api/admin/ai/healthcheck",
        data="{",
        content_type="application/json",
        headers=bearer(admin_token),
    )
    assert malformed.status_code == 400
    with app_module.app.app_context():
        app_module.db.session.rollback()

    empty_body = client.post("/api/admin/ai/healthcheck", headers=bearer(admin_token))
    assert empty_body.status_code == 415
    with app_module.app.app_context():
        app_module.db.session.rollback()


def test_healthcheck_local_readiness_seed_commit_and_write_set(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    with app_module.app.app_context():
        reset_legacy_registry_tables(app_module)
        before = side_effect_counts(app_module)

    response = client.post(
        "/api/admin/ai/healthcheck",
        json={"live_probe": False},
        headers={**bearer(admin_token), "X-Request-ID": "legacy-health-local"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert "items" in payload["data"]
    assert payload["data"]["items"]
    assert {item["health_status"] for item in payload["data"]["items"]} <= {
        "healthy",
        "unhealthy",
        "unknown",
    }
    assert_no_sentinel(payload)

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["provider_config"] >= before["provider_config"] + 1
        assert after["models"] >= before["models"] + 1
        assert after["prompts"] >= before["prompts"] + 1
        assert after["ai_calls"] == before["ai_calls"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["audit_records"] == before["audit_records"]
        assert after["concept_cards"] == before["concept_cards"]
        persisted = app_module.AIProviderConfig.query.filter_by(is_enabled=True).all()
        assert persisted
        assert all(config.last_healthcheck_at for config in persisted)


def test_healthcheck_live_probe_route_returns_disabled_result_without_calling_health_logic(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    captured = []
    original_evaluate = app_module.evaluate_legacy_provider_local_readiness

    def readiness_spy(*, request, provider):
        captured.append({
            "provider_name": provider.provider_name,
            "provider_mode": provider.provider_mode,
            "model_name": provider.model_name,
            "credential_present": provider.credential_present,
            "live_probe_requested": request.live_probe_requested,
        })
        return original_evaluate(request=request, provider=provider)

    with app_module.app.app_context():
        reset_legacy_registry_tables(app_module)
        config = app_module.AIProviderConfig(
            provider_name="deepseek",
            provider_mode="live",
            base_url=f"https://example.invalid/{SENTINEL}",
            default_model="deepseek-chat",
            is_enabled=True,
            is_default=True,
            health_status="unknown",
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add(config)
        app_module.db.session.commit()
        before = side_effect_counts(app_module)

    monkeypatch.setattr(app_module, "DEEPSEEK_API_KEY", SENTINEL)
    monkeypatch.setattr(app_module, "DEEPSEEK_BASE_URL", f"https://example.invalid/{SENTINEL}")
    monkeypatch.setattr(app_module, "evaluate_legacy_provider_local_readiness", readiness_spy)

    response = client.post(
        "/api/admin/ai/healthcheck",
        json={"live_probe": True},
        headers={**bearer(admin_token), "X-Request-ID": "legacy-health-live"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert_no_sentinel(payload)
    live_item = next(item for item in payload["data"]["items"] if item["provider_name"] == "deepseek")
    assert live_item["error_code"] == "LEGACY_LIVE_PROBE_DISABLED"
    assert "disabled" in live_item["message"].lower()
    live_calls = [item for item in captured if item["provider_name"] == "deepseek"]
    assert live_calls == [{
        "provider_name": "deepseek",
        "provider_mode": "live",
        "model_name": "deepseek-chat",
        "credential_present": True,
        "live_probe_requested": True,
    }]

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["ai_calls"] == before["ai_calls"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["audit_records"] == before["audit_records"]


def test_ai_health_service_still_requires_live_probe_redaction_boundary(monkeypatch):
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
            return {
                "status": "error",
                "error_code": "AI_PROVIDER_FAILED",
                "message": f"Transport exception contained {SENTINEL}",
            }

    monkeypatch.setattr(ai_health, "provider_from_selection", lambda selection: ProviderSpy())
    selection = ai_registry.ProviderSelection(
        provider_name="deepseek",
        provider_mode="live",
        model_name="deepseek-chat",
        api_key="sk-live-probe-risk-fixture",
        base_url="https://example.invalid",
        timeout_seconds=1,
        max_retries=0,
    )

    skipped = ai_health.healthcheck_provider(selection, live_probe=False)
    assert skipped["health_status"] == "unknown"
    assert captured == []

    result = ai_health.healthcheck_provider(selection, live_probe=True)
    assert result["health_status"] == "unhealthy"
    assert result["error_code"] == "AI_PROVIDER_FAILED"
    assert SENTINEL in result["message"]
    assert captured[0]["task_type"] == "term_alignment"
    assert captured[0]["input_payload"]["english_term"] == "Health Check"


def test_healthcheck_boundary_document_records_decision():
    document = (ROOT / "docs" / "legacy_provider_healthcheck_boundary.md").read_text(encoding="utf-8")
    required_markers = [
        "POST /api/admin/ai/healthcheck",
        "Local readiness",
        "Live transport probe",
        "Seed and transaction matrix",
        "LEGACY_LIVE_PROBE_DISABLED",
    ]
    for marker in required_markers:
        assert marker in document
