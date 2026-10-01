import importlib
import json
import socket
import urllib.request
from uuid import uuid4
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4I"
OBSERVABILITY_ROUTES = {
    ("/api/admin/ai/calls", "GET"): "admin_ai_calls",
    ("/api/admin/ai/usage", "GET"): "admin_ai_usage",
    ("/api/admin/ai/health", "GET"): "admin_ai_health",
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
        "ai_call_logs": app_module.AICallLog.query.count(),
        "ai_provider_config": app_module.AIProviderConfig.query.count(),
        "ai_models": app_module.AIModelRegistry.query.count(),
        "prompts": app_module.PromptTemplate.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_policy": app_module.AlignmentProviderPolicy.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
    }


def assert_no_secret_like_data(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    forbidden = [
        SENTINEL,
        "api_key",
        "authorization",
        "cookie",
        "private_key",
        "bearer ",
    ]
    lowered = serialized.lower()
    for item in forbidden:
        assert item not in lowered


def create_call_log(app_module, *, provider_name, status, created_at, estimated_cost=0.0):
    log = app_module.AICallLog(
        task_type="term_alignment",
        provider_name=provider_name,
        provider_mode="mock",
        model_name=f"{provider_name}-model",
        prompt_key="term_alignment",
        prompt_version="v1",
        request_hash="request-hash",
        response_hash="response-hash",
        input_token_count=10,
        output_token_count=20,
        estimated_cost=estimated_cost,
        latency_ms=12,
        status=status,
        error_code="" if status == "success" else "PROVIDER_ERROR",
        error_message="" if status == "success" else "redacted provider failure",
        redacted_prompt_preview="redacted prompt preview",
        redacted_response_preview="redacted response preview",
        created_at=created_at,
    )
    app_module.db.session.add(log)
    app_module.db.session.flush()
    return log


def create_role_token(app_module, client, *, role):
    password = "Reviewer1234"
    unique = uuid4().hex
    email = f"{role}-{unique}@lexibridge.local"
    with app_module.app.app_context():
        user = app_module.User(
            username=f"{role}_{unique}",
            email=email,
            password_hash=app_module.generate_password_hash(password, method="pbkdf2:sha256"),
            role=role,
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.get_json()["token"]


def seed_local_health(app_module):
    app_module.ensure_ai_registry_seed()
    app_module.db.session.commit()


def test_observability_route_map_openapi_and_frontend_dependencies(app_module):
    actual = route_map(app_module)
    for key, endpoint in OBSERVABILITY_ROUTES.items():
        assert actual.get(key) == endpoint
        assert sum(
            1
            for rule in app_module.app.url_map.iter_rules()
            if rule.rule == key[0] and key[1] in rule.methods
        ) == 1

    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    for path in {route[0] for route in OBSERVABILITY_ROUTES}:
        assert path in contract["paths"]
        assert "get" in contract["paths"][path]

    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for path in {route[0] for route in OBSERVABILITY_ROUTES}:
        assert f'api("{path}")' in frontend


def test_observability_gets_keep_permissions_envelope_no_request_id_and_no_network(
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
    reviewer_token = create_role_token(app_module, client, role="reviewer")

    for path, method in OBSERVABILITY_ROUTES:
        assert method == "GET"
        assert client.get(path).status_code == 401
        assert client.get(path, headers=bearer(student_token)).status_code == 403
        assert client.get(path, headers=bearer(teacher_token)).status_code == 403
        assert client.get(path, headers=bearer(reviewer_token)).status_code == 403

    with app_module.app.app_context():
        seed_local_health(app_module)
        older = create_call_log(app_module, provider_name="old-provider", status="error", created_at="2026-07-15T12:00:00", estimated_cost=0.01)
        newest = create_call_log(app_module, provider_name="new-provider", status="success", created_at="2026-07-16T12:00:00", estimated_cost=0.03)
        app_module.db.session.commit()
        expected_first_id = newest.id
        expected_second_id = older.id
        before = side_effect_counts(app_module)

    responses = {}
    for path, method in OBSERVABILITY_ROUTES:
        response = client.get(path, headers={**bearer(admin_token), "X-Request-ID": f"legacy-observability-{path.rsplit('/', 1)[-1]}"})
        assert response.status_code == 200, response.get_data(as_text=True)
        payload = response.get_json()
        responses[path] = payload
        assert set(payload) == {"status", "message", "data"}
        assert payload["status"] == "success"
        assert "request_id" not in payload
        assert_no_secret_like_data(payload)

    calls = responses["/api/admin/ai/calls"]["data"]["items"]
    assert [item["id"] for item in calls[:2]] == [expected_first_id, expected_second_id]
    assert len(calls) <= 300
    first_call = calls[0]
    assert {
        "id",
        "task_type",
        "provider_name",
        "provider_mode",
        "model_name",
        "prompt_key",
        "prompt_version",
        "user_id",
        "course_id",
        "document_id",
        "job_id",
        "alignment_run_id",
        "evaluation_run_id",
        "request_hash",
        "response_hash",
        "input_token_count",
        "output_token_count",
        "estimated_cost",
        "latency_ms",
        "status",
        "error_code",
        "error_message",
        "redacted_prompt_preview",
        "redacted_response_preview",
        "created_at",
    } == set(first_call)

    usage = responses["/api/admin/ai/usage"]["data"]
    assert {"summary", "recent"} == set(usage)
    assert usage["summary"]["total_calls"] >= 2
    assert [item["id"] for item in usage["recent"][:2]] == [expected_first_id, expected_second_id]
    assert len(usage["recent"]) <= 50

    health = responses["/api/admin/ai/health"]["data"]
    assert "items" in health
    assert health["items"]
    assert {
        "provider_name",
        "provider_mode",
        "base_url",
        "default_model",
        "is_enabled",
        "is_default",
        "health_status",
    } <= set(health["items"][0])

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after == before
