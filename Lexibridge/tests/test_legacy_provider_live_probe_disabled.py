import importlib
import json
import socket
import urllib.request

import pytest

from provider_admin_state_isolation import (
    capture_provider_admin_state,
    restore_provider_admin_state,
)


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
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    for module_name in ("requests", "httpx"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        if hasattr(module, "request"):
            monkeypatch.setattr(module, "request", blocked)


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


def create_enabled_live_provider(app_module):
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
    return config.id


def test_live_probe_true_is_disabled_before_health_provider_logic(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    with app_module.app.app_context():
        reset_legacy_registry_tables(app_module)
        create_enabled_live_provider(app_module)
        before = side_effect_counts(app_module)

    calls = []
    original_evaluate = app_module.evaluate_legacy_provider_local_readiness

    def readiness_spy(*, request, provider):
        calls.append((provider.provider_name, provider.provider_mode, request.live_probe_requested, provider.credential_present))
        return original_evaluate(request=request, provider=provider)

    monkeypatch.setattr(app_module, "DEEPSEEK_API_KEY", SENTINEL)
    monkeypatch.setattr(app_module, "DEEPSEEK_BASE_URL", f"https://example.invalid/{SENTINEL}")
    monkeypatch.setattr(app_module, "evaluate_legacy_provider_local_readiness", readiness_spy)

    response = client.post(
        "/api/admin/ai/healthcheck",
        json={"live_probe": True},
        headers={**bearer(admin_token), "X-Request-ID": "legacy-live-probe-disabled"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"status", "message", "data"}
    assert payload["status"] == "success"
    assert "request_id" not in payload
    assert_no_sentinel(payload)
    items = payload["data"]["items"]
    live_item = next(item for item in items if item["provider_name"] == "deepseek")
    assert live_item["provider_mode"] == "live"
    assert live_item["health_status"] == "unknown"
    assert live_item["error_code"] == "LEGACY_LIVE_PROBE_DISABLED"
    assert "disabled" in live_item["message"].lower()
    live_calls = [call for call in calls if call[0] == "deepseek"]
    assert live_calls == [("deepseek", "live", True, True)]

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after["provider_config"] >= before["provider_config"]
        assert after["models"] >= before["models"]
        assert after["prompts"] >= before["prompts"]
        assert after["ai_calls"] == before["ai_calls"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["audit_records"] == before["audit_records"]
        assert after["concept_cards"] == before["concept_cards"]


def test_live_probe_omitted_and_false_keep_local_readiness_path(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    with app_module.app.app_context():
        reset_legacy_registry_tables(app_module)
        create_enabled_live_provider(app_module)

    monkeypatch.setattr(app_module, "DEEPSEEK_API_KEY", SENTINEL)
    monkeypatch.setattr(app_module, "DEEPSEEK_BASE_URL", f"https://example.invalid/{SENTINEL}")

    omitted = client.post("/api/admin/ai/healthcheck", json={}, headers=bearer(admin_token))
    explicit_false = client.post(
        "/api/admin/ai/healthcheck",
        json={"live_probe": False},
        headers=bearer(admin_token),
    )

    assert omitted.status_code == 200
    assert explicit_false.status_code == 200
    for response in (omitted, explicit_false):
        live_item = next(item for item in response.get_json()["data"]["items"] if item["provider_name"] == "deepseek")
        assert live_item["health_status"] == "unknown"
        assert live_item["message"] == "Config is complete; live probe skipped."
        assert "error_code" not in live_item
    assert_no_sentinel(omitted.get_json())
    assert_no_sentinel(explicit_false.get_json())


def test_live_probe_disabled_contract_keeps_role_boundaries(
    client,
    admin_token,
    teacher_token,
    student_token,
    monkeypatch,
):
    no_network(monkeypatch)
    assert client.post("/api/admin/ai/healthcheck", json={"live_probe": True}).status_code == 401
    assert (
        client.post(
            "/api/admin/ai/healthcheck",
            json={"live_probe": True},
            headers=bearer(student_token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/ai/healthcheck",
            json={"live_probe": True},
            headers=bearer(teacher_token),
        ).status_code
        == 403
    )
    assert client.post("/api/admin/ai/healthcheck", json={"live_probe": True}, headers=bearer(admin_token)).status_code == 200


def test_pilot_readiness_checks_legacy_live_probe_disabled():
    from scripts import pilot_readiness_check

    code = pilot_readiness_check.provider_network_disabled_code()
    assert "/api/admin/ai/healthcheck" in code
    assert "LEGACY_LIVE_PROBE_DISABLED" in code
