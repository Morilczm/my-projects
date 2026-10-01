import ast
import importlib
import json
import socket
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest

from provider_admin_state_isolation import (
    assert_provider_admin_state_clean,
    capture_provider_admin_state,
    restore_provider_admin_state,
)


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = "/api/admin/ai/prompts"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4Q"


@pytest.fixture(autouse=True)
def isolate_provider_admin_state(app_module):
    snapshot = capture_provider_admin_state(app_module)
    restore_provider_admin_state(app_module, snapshot)
    yield
    restore_provider_admin_state(app_module, snapshot)
    assert_provider_admin_state_clean(app_module)


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


def prompt_payload(prompt_key, *, version="v1", **overrides):
    payload = {
        "prompt_key": prompt_key,
        "prompt_version": version,
        "task_type": "term_alignment",
        "language": "bilingual",
        "template_text": "Return JSON with bilingual evidence and risk labels.",
        "json_schema": {"type": "object", "properties": {"term": {"type": "string"}}},
        "is_active": True,
        "is_default": False,
        "notes": "safe prompt note",
    }
    payload.update(overrides)
    return payload


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


def block_for_function(source, name):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"function not found: {name}")


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


def test_prompt_mutation_service_integration_keeps_shared_route_and_extracted_adapter():
    app_source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    route_source = (ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py").read_text(
        encoding="utf-8"
    )
    with pytest.raises(AssertionError):
        block_for_function(app_source, "admin_ai_prompts_post_handler")

    assert "if request.method == \"POST\":" in route_source
    post_index = route_source.index("if request.method == \"POST\":")
    post_block = block_for_function(route_source, "admin_ai_prompts")
    assert "LegacyPromptMutationRequest.from_payload" in post_block
    assert "prompt_mutation_service(" in post_block
    assert "db.session.commit" not in post_block
    assert "db.session.rollback" not in post_block
    seed_index = route_source.index("seed_registry(user.id)", post_index)
    get_query_index = route_source.index("models.PromptTemplate.query.order_by", post_index)
    assert post_index < seed_index < get_query_index


def test_prompt_mutation_service_integration_contract_and_write_set(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
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

    prompt_key = f"legacy_admin_9c4q_integration_{uuid4().hex}"
    with app_module.app.app_context():
        before = side_effect_counts(app_module)
        before_audit = app_module.AuditRecord.query.count()

    response = client.post(
        PROMPT_PATH,
        json=prompt_payload(
            prompt_key,
            template_text="Legal template with placeholders: {term}\nReturn JSON.",
            api_key=SENTINEL,
            authorization=f"Bearer {SENTINEL}",
        ),
        headers=bearer(admin_token),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"status", "message", "data"}
    assert body["status"] == "success"
    assert body["message"] == "Prompt saved."
    assert "request_id" not in body
    serialized_body = json.dumps(body, ensure_ascii=False)
    assert SENTINEL not in serialized_body
    assert "template_text" not in body["data"]

    with app_module.app.app_context():
        prompt = fetch_prompt(app_module, prompt_key)
        assert prompt.template_text == "Legal template with placeholders: {term}\nReturn JSON."
        assert SENTINEL not in json.dumps(
            {
                "template_text": prompt.template_text,
                "json_schema": prompt.json_schema,
                "notes": prompt.notes,
            },
            ensure_ascii=False,
        )
        after = side_effect_counts(app_module)
        assert after == before
        assert app_module.AuditRecord.query.count() == before_audit

    get_response = client.get(PROMPT_PATH, headers=bearer(admin_token))
    assert get_response.status_code == 200
    get_body = get_response.get_json()
    assert get_body["status"] == "success"
    assert "items" in get_body["data"]


def test_prompt_mutation_service_integration_failure_contract_and_rollback(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = f"legacy_admin_9c4q_failure_{uuid4().hex}"

    validation = client.post(PROMPT_PATH, json={"prompt_version": "v1"}, headers=bearer(admin_token))
    assert validation.status_code == 400
    validation_body = validation.get_json()
    assert validation_body["status"] == "error"
    assert validation_body["error_code"] == "VALIDATION_ERROR"
    assert validation_body["message"] == "prompt_key and prompt_version are required."
    assert "request_id" not in validation_body

    original_commit = app_module.db.session.commit

    def fail_commit():
        raise RuntimeError("controlled 9c4q integration commit failure")

    with monkeypatch.context() as patched:
        patched.setattr(app_module.db.session, "commit", fail_commit)
        response = client.post(PROMPT_PATH, json=prompt_payload(prompt_key), headers=bearer(admin_token))

    assert response.status_code == 500
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error_code"] == "INTERNAL_ERROR"
    assert body["message"] == "Internal server error."
    assert "request_id" not in body

    with app_module.app.app_context():
        app_module.db.session.commit = original_commit
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).first() is None
        assert not app_module.db.session.new
        assert not app_module.db.session.dirty

    recovery = client.post(
        PROMPT_PATH,
        json=prompt_payload(f"{prompt_key}_recovery"),
        headers=bearer(admin_token),
    )
    assert recovery.status_code == 200
