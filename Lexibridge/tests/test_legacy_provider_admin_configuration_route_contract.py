import importlib
import json
import socket
import urllib.request
from pathlib import Path
from uuid import uuid4

import yaml


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4K"
CONFIGURATION_ROUTES = {
    ("/api/admin/ai/providers", "GET"): "admin_ai_providers",
    ("/api/admin/ai/models", "GET"): "admin_ai_models",
    ("/api/admin/ai/prompts", "GET"): "admin_ai_prompts",
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
        "ai_provider_config": app_module.AIProviderConfig.query.count(),
        "ai_models": app_module.AIModelRegistry.query.count(),
        "prompts": app_module.PromptTemplate.query.count(),
        "provider_policy": app_module.AlignmentProviderPolicy.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
    }


def reset_legacy_registry_tables(app_module):
    app_module.PromptTemplate.query.delete()
    app_module.AIModelRegistry.query.delete()
    app_module.AIProviderConfig.query.delete()
    app_module.db.session.commit()


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


def assert_no_secret_like_data(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    lowered = serialized.lower()
    forbidden = [
        SENTINEL.lower(),
        "api_key",
        "authorization",
        "cookie",
        "private_key",
        "bearer ",
    ]
    for item in forbidden:
        assert item not in lowered


def test_configuration_route_map_openapi_and_frontend_contract(app_module):
    actual = route_map(app_module)
    for key, endpoint in CONFIGURATION_ROUTES.items():
        assert actual.get(key) == endpoint
        assert sum(
            1
            for rule in app_module.app.url_map.iter_rules()
            if rule.rule == key[0] and key[1] in rule.methods
        ) == 1

    assert actual.get(("/api/admin/ai/prompts", "POST")) == "admin_ai_prompts"

    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    for path in {route[0] for route in CONFIGURATION_ROUTES}:
        assert path in contract["paths"]
        assert "get" in contract["paths"][path]
    assert "post" in contract["paths"]["/api/admin/ai/prompts"]

    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for path in {route[0] for route in CONFIGURATION_ROUTES}:
        assert f'api("{path}")' in frontend


def test_configuration_gets_keep_permissions_envelope_fields_seed_flush_and_no_network(
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

    for path, method in CONFIGURATION_ROUTES:
        assert method == "GET"
        assert client.get(path).status_code == 401
        assert client.get(path, headers=bearer(student_token)).status_code == 403
        assert client.get(path, headers=bearer(teacher_token)).status_code == 403
        assert client.get(path, headers=bearer(reviewer_token)).status_code == 403

    with app_module.app.app_context():
        reset_legacy_registry_tables(app_module)
        empty_before = side_effect_counts(app_module)
        assert empty_before["ai_provider_config"] == 0
        assert empty_before["ai_models"] == 0
        assert empty_before["prompts"] == 0

    for path, method in CONFIGURATION_ROUTES:
        response = client.get(path, headers={**bearer(admin_token), "X-Request-ID": f"config-seed-{path.rsplit('/', 1)[-1]}"})
        assert response.status_code == 200, response.get_data(as_text=True)
        payload = response.get_json()
        assert set(payload) == {"status", "message", "data"}
        assert payload["status"] == "success"
        assert "request_id" not in payload
        assert "items" in payload["data"]
        assert payload["data"]["items"]
        assert_no_secret_like_data(payload)
        with app_module.app.app_context():
            after_get = side_effect_counts(app_module)
            assert after_get == empty_before

    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
        app_module.db.session.commit()
        persisted_before = side_effect_counts(app_module)

    responses = {}
    for path, method in CONFIGURATION_ROUTES:
        response = client.get(path, headers={**bearer(admin_token), "X-Request-ID": f"config-{path.rsplit('/', 1)[-1]}"})
        assert response.status_code == 200, response.get_data(as_text=True)
        payload = response.get_json()
        responses[path] = payload
        assert set(payload) == {"status", "message", "data"}
        assert payload["status"] == "success"
        assert "request_id" not in payload
        assert_no_secret_like_data(payload)

    provider_data = responses["/api/admin/ai/providers"]["data"]
    assert set(provider_data) == {"items", "current"}
    provider_item = provider_data["items"][0]
    assert {
        "id",
        "provider_name",
        "provider_mode",
        "base_url",
        "default_model",
        "is_enabled",
        "is_default",
        "supports_json_schema",
        "supports_streaming",
        "supports_vision",
        "supports_formula_reasoning",
        "max_input_tokens",
        "max_output_tokens",
        "timeout_seconds",
        "max_retries",
        "cost_per_1k_input_tokens",
        "cost_per_1k_output_tokens",
        "health_status",
        "last_healthcheck_at",
        "created_at",
        "updated_at",
    } == set(provider_item)
    assert "api_key" not in provider_item
    provider_defaults = [item["is_default"] for item in provider_data["items"]]
    assert provider_defaults == sorted(provider_defaults, reverse=True)

    model_items = responses["/api/admin/ai/models"]["data"]["items"]
    assert model_items
    assert {
        "id",
        "provider_name",
        "model_name",
        "model_version",
        "model_display_name",
        "provider_mode",
        "supports_json_output",
        "supports_tool_calling",
        "supports_vision",
        "max_input_tokens",
        "max_output_tokens",
        "cost_per_1k_input_tokens",
        "cost_per_1k_output_tokens",
        "is_enabled",
        "is_default_for_provider",
        "last_evaluation_run_id",
        "last_evaluation_score",
        "known_risks",
        "created_at",
        "updated_at",
    } == set(model_items[0])

    prompt_items = responses["/api/admin/ai/prompts"]["data"]["items"]
    assert prompt_items
    assert {
        "id",
        "prompt_key",
        "prompt_version",
        "task_type",
        "language",
        "json_schema",
        "is_active",
        "is_default",
        "created_by",
        "created_at",
        "updated_at",
        "notes",
    } == set(prompt_items[0])
    assert "template_text" not in prompt_items[0]

    with app_module.app.app_context():
        after = side_effect_counts(app_module)
        assert after == persisted_before


def test_configuration_gets_preserve_legitimate_prompt_template_contract(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = "legacy_admin_9c4k_prompt"
    legal_template = "Translate the term using course evidence and preserve JSON output."
    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
        prompt = app_module.PromptTemplate(
            prompt_key=prompt_key,
            prompt_version="v1",
            task_type="term_alignment",
            language="bilingual",
            template_text=legal_template,
            json_schema=json.dumps({"type": "object", "properties": {"term": {"type": "string"}}}),
            is_active=True,
            is_default=False,
            created_by=1,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
            notes="visible safe prompt notes",
        )
        app_module.db.session.add(prompt)
        app_module.db.session.commit()

    response = client.get("/api/admin/ai/prompts", headers=bearer(admin_token))
    assert response.status_code == 200
    payload = response.get_json()
    prompts = payload["data"]["items"]
    match = next(item for item in prompts if item["prompt_key"] == prompt_key)
    assert match["notes"] == "visible safe prompt notes"
    assert match["json_schema"]["properties"]["term"]["type"] == "string"
    assert "template_text" not in match
    assert legal_template not in json.dumps(match, ensure_ascii=False)


def test_prompt_post_mutation_contract_stays_in_place(app_module, client, admin_token, monkeypatch):
    no_network(monkeypatch)
    prompt_key = "legacy_admin_9c4k_post"
    payload = {
        "prompt_key": prompt_key,
        "prompt_version": "v1",
        "task_type": "term_alignment",
        "language": "bilingual",
        "template_text": "Return bilingual evidence.",
        "json_schema": {"type": "object"},
        "is_active": True,
        "is_default": False,
        "notes": "created by POST regression",
    }
    response = client.post("/api/admin/ai/prompts", json=payload, headers=bearer(admin_token))
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["message"] == "Prompt saved."
    assert "request_id" not in body
    assert body["data"]["prompt_key"] == prompt_key

    with app_module.app.app_context():
        prompt = app_module.PromptTemplate.query.filter_by(
            prompt_key=prompt_key,
            prompt_version="v1",
        ).one()
        assert prompt.template_text == "Return bilingual evidence."
        assert prompt.notes == "created by POST regression"
