from services.ai_health import healthcheck_provider
from services.ai_registry import ProviderSelection


def test_none_mock_and_live_missing_key_health_states():
    none = healthcheck_provider(ProviderSelection("none", "none", "none"))
    assert none["health_status"] == "unhealthy"

    mock = healthcheck_provider(ProviderSelection("mock", "mock", "mock"))
    assert mock["health_status"] == "healthy"

    live_missing = healthcheck_provider(ProviderSelection("deepseek", "live", "deepseek-chat", api_key=""))
    assert live_missing["health_status"] == "unhealthy"
    assert "key" in live_missing["message"].lower()


def test_healthcheck_api_updates_registry_without_key_leak(app_module, client, admin_token):
    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
    response = client.post("/api/admin/ai/healthcheck", json={}, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["items"]
    assert "api_key" not in str(payload).lower()
    with app_module.app.app_context():
        assert app_module.AIProviderConfig.query.first().health_status in {"healthy", "unhealthy", "unknown"}
