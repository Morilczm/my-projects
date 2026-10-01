import importlib
import json
import socket
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from provider_admin_state_isolation import (
    assert_provider_admin_state_clean,
    capture_provider_admin_state,
    restore_provider_admin_state,
)


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = "/api/admin/ai/prompts"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4R"


@pytest.fixture(autouse=True)
def isolate_provider_admin_state(app_module):
    snapshot = capture_provider_admin_state(app_module)
    restore_provider_admin_state(app_module, snapshot)
    yield
    restore_provider_admin_state(app_module, snapshot)
    assert_provider_admin_state_clean(app_module)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def no_network(monkeypatch, app_module=None):
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
    if app_module is not None:
        if hasattr(app_module, "provider_from_selection"):
            monkeypatch.setattr(app_module, "provider_from_selection", blocked)
        if hasattr(app_module, "healthcheck_provider"):
            monkeypatch.setattr(app_module, "healthcheck_provider", blocked)


def prompt_payload(prompt_key, *, version="v1", **overrides):
    payload = {
        "prompt_key": prompt_key,
        "prompt_version": version,
        "task_type": "term_alignment",
        "language": "bilingual",
        "template_text": "Legal template with {term} and JSON output.",
        "json_schema": {"type": "object", "properties": {"term": {"type": "string"}}},
        "is_active": True,
        "is_default": False,
        "notes": "safe route note",
    }
    payload.update(overrides)
    return payload


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


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


def side_effect_counts(app_module):
    return {
        "audit_records": app_module.AuditRecord.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_calls": app_module.AICallLog.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
    }


def fetch_prompt(app_module, prompt_key, prompt_version="v1"):
    return app_module.PromptTemplate.query.filter_by(
        prompt_key=prompt_key,
        prompt_version=prompt_version,
    ).one()


def assert_no_secret_like_data(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    lowered = serialized.lower()
    for forbidden in (SENTINEL.lower(), "api_key", "authorization", "cookie", "private_key", "bearer "):
        assert forbidden not in lowered


def test_prompt_mutation_route_keeps_shared_get_post_endpoint_openapi_and_frontend(app_module):
    actual = route_map(app_module)
    assert actual[(PROMPT_PATH, "GET")] == "admin_ai_prompts"
    assert actual[(PROMPT_PATH, "POST")] == "admin_ai_prompts"
    prompt_rules = [
        rule
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == PROMPT_PATH and {"GET", "POST"}.intersection(rule.methods)
    ]
    assert len(prompt_rules) == 1
    assert {"GET", "POST"}.issubset(prompt_rules[0].methods)

    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    assert "get" in contract["paths"][PROMPT_PATH]
    assert "post" in contract["paths"][PROMPT_PATH]

    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert f'api("{PROMPT_PATH}")' in frontend


def test_prompt_mutation_route_permissions_and_json_error_contract(
    app_module,
    client,
    admin_token,
    teacher_token,
    student_token,
    monkeypatch,
):
    no_network(monkeypatch, app_module)
    reviewer_token = create_role_token(app_module, client, role="reviewer")
    payload = prompt_payload(f"legacy_admin_9c4r_permission_{uuid4().hex}")
    with app_module.app.app_context():
        before = side_effect_counts(app_module)

    assert client.post(PROMPT_PATH, json=payload).status_code == 401
    assert client.post(PROMPT_PATH, json=payload, headers=bearer(student_token)).status_code == 403
    assert client.post(PROMPT_PATH, json=payload, headers=bearer(teacher_token)).status_code == 403
    assert client.post(PROMPT_PATH, json=payload, headers=bearer(reviewer_token)).status_code == 403
    with app_module.app.app_context():
        assert side_effect_counts(app_module) == before

    empty_response = client.post(PROMPT_PATH, json={}, headers=bearer(admin_token))
    assert empty_response.status_code == 400
    empty_body = empty_response.get_json()
    assert empty_body["status"] == "error"
    assert empty_body["error_code"] == "VALIDATION_ERROR"
    assert "request_id" not in empty_body

    missing_key = client.post(PROMPT_PATH, json={"prompt_version": "v1"}, headers=bearer(admin_token))
    assert missing_key.status_code == 400
    missing_version = client.post(PROMPT_PATH, json={"prompt_key": "legacy_admin_9c4r_missing"}, headers=bearer(admin_token))
    assert missing_version.status_code == 400

    malformed_response = client.post(
        PROMPT_PATH,
        data="{",
        content_type="application/json",
        headers=bearer(admin_token),
    )
    assert malformed_response.status_code == 400
    assert client.post(PROMPT_PATH, headers=bearer(admin_token)).status_code == 415

    with app_module.app.app_context():
        app_module.db.session.rollback()
        assert side_effect_counts(app_module) == before


def test_prompt_mutation_route_create_update_repeat_secret_redaction_and_get_unchanged(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch, app_module)
    prompt_key = f"legacy_admin_9c4r_route_{uuid4().hex}"
    with app_module.app.app_context():
        before = side_effect_counts(app_module)
        before_audit = app_module.AuditRecord.query.count()

    create = client.post(
        PROMPT_PATH,
        json=prompt_payload(
            prompt_key,
            template_text="Legal prompt template with {term}\nReturn JSON.",
            api_key=SENTINEL,
            authorization=f"Bearer {SENTINEL}",
            private_metadata={"private_key": SENTINEL},
        ),
        headers=bearer(admin_token),
    )
    assert create.status_code == 200
    create_body = create.get_json()
    assert set(create_body) == {"status", "message", "data"}
    assert create_body["status"] == "success"
    assert create_body["message"] == "Prompt saved."
    assert "request_id" not in create_body
    assert "template_text" not in create_body["data"]
    assert_no_secret_like_data(create_body)

    with app_module.app.app_context():
        prompt = fetch_prompt(app_module, prompt_key)
        prompt_id = prompt.id
        assert prompt.template_text == "Legal prompt template with {term}\nReturn JSON."
        assert SENTINEL not in json.dumps(
            {
                "template_text": prompt.template_text,
                "json_schema": prompt.json_schema,
                "notes": prompt.notes,
            },
            ensure_ascii=False,
        )

    identical = client.post(PROMPT_PATH, json=prompt_payload(prompt_key), headers=bearer(admin_token))
    assert identical.status_code == 200
    different = client.post(
        PROMPT_PATH,
        json=prompt_payload(prompt_key, template_text="Second payload wins."),
        headers=bearer(admin_token),
    )
    assert different.status_code == 200

    with app_module.app.app_context():
        prompts = app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key, prompt_version="v1").all()
        assert len(prompts) == 1
        assert prompts[0].id == prompt_id
        assert prompts[0].template_text == "Second payload wins."
        assert side_effect_counts(app_module) == before
        assert app_module.AuditRecord.query.count() == before_audit

    get_response = client.get(PROMPT_PATH, headers=bearer(admin_token))
    assert get_response.status_code == 200
    get_body = get_response.get_json()
    assert get_body["status"] == "success"
    assert set(get_body) == {"status", "message", "data"}
    assert "items" in get_body["data"]


def test_prompt_mutation_route_uses_service_transaction_and_rolls_back_on_failure(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch, app_module)
    prompt_key = f"legacy_admin_9c4r_failure_{uuid4().hex}"
    original_commit = app_module.db.session.commit
    original_rollback = app_module.db.session.rollback
    rollback_calls = []

    def fail_commit():
        raise RuntimeError("controlled 9c4r commit failure")

    def tracked_rollback():
        rollback_calls.append("rollback")
        return original_rollback()

    with monkeypatch.context() as patched:
        patched.setattr(app_module.db.session, "commit", fail_commit)
        patched.setattr(app_module.db.session, "rollback", tracked_rollback)
        response = client.post(PROMPT_PATH, json=prompt_payload(prompt_key), headers=bearer(admin_token))

    assert response.status_code == 500
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error_code"] == "INTERNAL_ERROR"
    assert body["message"] == "Internal server error."
    assert "request_id" not in body
    assert rollback_calls == ["rollback"]

    with app_module.app.app_context():
        app_module.db.session.commit = original_commit
        app_module.db.session.rollback = original_rollback
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).first() is None
        assert not app_module.db.session.new
        assert not app_module.db.session.dirty

    recovery = client.post(PROMPT_PATH, json=prompt_payload(f"{prompt_key}_recovery"), headers=bearer(admin_token))
    assert recovery.status_code == 200
