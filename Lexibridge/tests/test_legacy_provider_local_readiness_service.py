import ast
import importlib
import json
import socket
import urllib.request
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "backend" / "services" / "legacy_provider_local_readiness.py"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4M"


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


def imports_for(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return imports


def provider(**overrides):
    from services.legacy_provider_local_readiness import LegacyProviderLocalReadinessProvider

    data = {
        "provider_name": "mock",
        "provider_mode": "mock",
        "model_name": "mock-rule-v1",
        "enabled": True,
        "credential_present": False,
        "adapter_available": True,
        "external_execution_enabled": False,
    }
    data.update(overrides)
    return LegacyProviderLocalReadinessProvider(**data)


def request(**overrides):
    from services.legacy_provider_local_readiness import LegacyProviderLocalReadinessRequest

    data = {"live_probe_requested": False}
    data.update(overrides)
    return LegacyProviderLocalReadinessRequest(**data)


def evaluate(provider_snapshot, readiness_request=None):
    from services.legacy_provider_local_readiness import evaluate_legacy_provider_local_readiness

    return evaluate_legacy_provider_local_readiness(
        request=readiness_request or request(),
        provider=provider_snapshot,
    )


def assert_no_sentinel(value):
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    assert SENTINEL not in serialized
    lowered = serialized.lower()
    for term in ("authorization", "cookie", "private_key", "bearer "):
        assert term not in lowered


def test_local_readiness_service_static_boundary():
    imports = set(imports_for(SERVICE_PATH))
    assert "flask" not in imports
    assert "backend.app" not in imports
    assert "backend.routes" not in imports
    assert "os" not in imports
    assert not any("transport" in item for item in imports)

    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert "provider_from_selection" not in source
    assert "healthcheck_provider" not in source
    assert "db.session.commit" not in source
    assert "db.session.rollback" not in source
    assert "os.environ" not in source
    assert "api_key" not in source
    assert "Authorization" not in source


def test_local_readiness_dtos_are_immutable():
    p = provider()
    r = request()
    result = evaluate(p, r)
    for instance, attr in [(p, "provider_name"), (r, "live_probe_requested"), (result, "health_status")]:
        try:
            setattr(instance, attr, "changed")
        except FrozenInstanceError:
            pass
        else:
            raise AssertionError(f"{type(instance).__name__} is mutable")


def test_local_readiness_matches_legacy_provider_modes(monkeypatch):
    no_network(monkeypatch)
    cases = [
        (provider(provider_name="none", provider_mode="none"), "unhealthy", "AI provider is not configured."),
        (provider(provider_name="mock", provider_mode="mock"), "healthy", "Development-only provider is available."),
        (
            provider(provider_name="local_heuristic", provider_mode="local_heuristic"),
            "healthy",
            "Development-only provider is available.",
        ),
        (
            provider(provider_name="external-llm-replay-v1", provider_mode="replay"),
            "unhealthy",
            "Live provider API key is missing or placeholder.",
        ),
    ]
    for snapshot, status, message in cases:
        result = evaluate(snapshot)
        assert result.health_status == status
        assert result.message == message
        assert result.live_probe_executed is False
        assert result.to_payload()["health_status"] == status


def test_live_provider_without_credential_is_unhealthy_without_secret(monkeypatch):
    no_network(monkeypatch)
    result = evaluate(provider(provider_name="deepseek", provider_mode="live", credential_present=False))
    assert result.health_status == "unhealthy"
    assert result.message == "Live provider API key is missing or placeholder."
    assert result.error_code is None
    assert result.health_updates == {"health_status": "unhealthy"}
    assert_no_sentinel(result.to_payload())


def test_live_provider_with_credential_skips_probe_by_default(monkeypatch):
    no_network(monkeypatch)
    result = evaluate(provider(provider_name="deepseek", provider_mode="live", credential_present=True))
    assert result.health_status == "unknown"
    assert result.message == "Config is complete; live probe skipped."
    assert result.live_probe_executed is False
    assert result.health_updates == {"health_status": "unknown"}


def test_live_probe_true_is_disabled_for_all_provider_classes(monkeypatch):
    no_network(monkeypatch)
    snapshots = [
        provider(provider_name="deepseek", provider_mode="live", credential_present=True),
        provider(provider_name="deepseek", provider_mode="live", credential_present=False),
        provider(provider_name="mock", provider_mode="mock"),
        provider(provider_name="local_heuristic", provider_mode="local_heuristic"),
        provider(provider_name="external-llm-replay-v1", provider_mode="replay", credential_present=True),
        provider(provider_name="disabled-deepseek", provider_mode="live", enabled=False, credential_present=True),
    ]
    for snapshot in snapshots:
        result = evaluate(snapshot, request(live_probe_requested=True))
        assert result.health_status == "unknown"
        assert result.error_code == "LEGACY_LIVE_PROBE_DISABLED"
        assert result.live_probe_requested is True
        assert result.live_probe_executed is False
        payload = result.to_payload()
        assert payload["provider_name"] == snapshot.provider_name
        assert payload["provider_mode"] == snapshot.provider_mode
        assert payload["error_code"] == "LEGACY_LIVE_PROBE_DISABLED"
        assert "disabled" in payload["message"].lower()
        assert_no_sentinel(payload)


def test_adapter_unavailable_and_external_disabled_are_local_summaries(monkeypatch):
    no_network(monkeypatch)
    unavailable = evaluate(
        provider(provider_name="custom_openai_compatible", provider_mode="live", adapter_available=False)
    )
    assert unavailable.health_status == "unhealthy"
    assert unavailable.error_code == "AI_PROVIDER_ADAPTER_UNAVAILABLE"

    disabled = evaluate(
        provider(provider_name="deepseek", provider_mode="live", external_execution_enabled=False, credential_present=True)
    )
    assert disabled.health_status == "unknown"
    assert disabled.live_probe_executed is False


def test_repeated_evaluation_is_deterministic_and_has_no_transaction_hooks(monkeypatch):
    no_network(monkeypatch)
    snapshot = provider(provider_name="deepseek", provider_mode="live", credential_present=True)
    first = evaluate(snapshot, request(live_probe_requested=True))
    second = evaluate(snapshot, request(live_probe_requested=True))
    assert first == second
    assert first.health_updates == {"health_status": "unknown"}
    assert "commit" not in SERVICE_PATH.read_text(encoding="utf-8")
    assert "rollback" not in SERVICE_PATH.read_text(encoding="utf-8")
