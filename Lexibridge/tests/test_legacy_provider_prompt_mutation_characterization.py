import importlib
import json
import socket
import urllib.request
from contextlib import contextmanager
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
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4O"
PROMPT_PATH = "/api/admin/ai/prompts"


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


@contextmanager
def no_exception_propagation(app_module):
    old = app_module.app.config.get("PROPAGATE_EXCEPTIONS")
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        yield
    finally:
        if old is None:
            app_module.app.config.pop("PROPAGATE_EXCEPTIONS", None)
        else:
            app_module.app.config["PROPAGATE_EXCEPTIONS"] = old


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


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


def side_effect_counts(app_module):
    return {
        "providers": app_module.AIProviderConfig.query.count(),
        "models": app_module.AIModelRegistry.query.count(),
        "prompts": app_module.PromptTemplate.query.count(),
        "provider_policy": app_module.AlignmentProviderPolicy.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_calls": app_module.AICallLog.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
    }


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


def assert_no_secret_like_data(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    lowered = serialized.lower()
    for forbidden in (
        SENTINEL.lower(),
        "authorization",
        "cookie",
        "private_key",
        "bearer ",
    ):
        assert forbidden not in lowered


def fetch_prompt(app_module, prompt_key, prompt_version):
    return app_module.PromptTemplate.query.filter_by(
        prompt_key=prompt_key,
        prompt_version=prompt_version,
    ).one()


def test_prompt_mutation_registration_openapi_frontend_and_route_adapter_contract(app_module):
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

    app_source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    route_source = (ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py").read_text(
        encoding="utf-8"
    )
    assert "def admin_ai_prompts_post_handler(user):" not in app_source
    assert "prompt_post_handler" not in app_source
    assert '@app.route("/api/admin/ai/prompts"' not in app_source
    assert "methods=[\"GET\", \"POST\"]" in route_source
    assert "prompt_post_handler" not in route_source
    assert "LegacyPromptMutationRequest.from_payload" in route_source
    assert "prompt_mutation_service(" in route_source
    assert "prompt_mutation_dependencies" in route_source

    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    prompt_contract = contract["paths"][PROMPT_PATH]
    assert set(prompt_contract) == {"get", "post"}
    request_schema = prompt_contract["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["required"] == ["prompt_key", "prompt_version", "task_type", "template_text"]

    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert f'api("{PROMPT_PATH}")' in frontend
    assert f'api("{PROMPT_PATH}", {{ method: "POST"' not in frontend


def test_prompt_mutation_permissions_do_not_seed_or_write_for_non_admins(
    app_module,
    client,
    admin_token,
    teacher_token,
    student_token,
):
    reviewer_token = create_role_token(app_module, client, role="reviewer")
    payload = prompt_payload(f"legacy_admin_9c4o_permission_{uuid4().hex}")
    with app_module.app.app_context():
        before = side_effect_counts(app_module)

    assert client.post(PROMPT_PATH, json=payload).status_code == 401
    assert client.post(PROMPT_PATH, json=payload, headers=bearer(student_token)).status_code == 403
    assert client.post(PROMPT_PATH, json=payload, headers=bearer(teacher_token)).status_code == 403
    assert client.post(PROMPT_PATH, json=payload, headers=bearer(reviewer_token)).status_code == 403

    with app_module.app.app_context():
        after_denied = side_effect_counts(app_module)
        assert after_denied == before

    assert client.post(PROMPT_PATH, json=payload, headers=bearer(admin_token)).status_code == 200


def test_prompt_mutation_json_error_contract_and_unknown_fields(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    with app_module.app.app_context():
        before = side_effect_counts(app_module)

    empty_response = client.post(PROMPT_PATH, json={}, headers=bearer(admin_token))
    assert empty_response.status_code == 400
    empty_payload = empty_response.get_json()
    assert empty_payload["status"] == "error"
    assert empty_payload["error_code"] == "VALIDATION_ERROR"
    assert "request_id" not in empty_payload

    malformed_response = client.post(
        PROMPT_PATH,
        data="{",
        content_type="application/json",
        headers=bearer(admin_token),
    )
    assert malformed_response.status_code == 400

    empty_body_response = client.post(PROMPT_PATH, headers=bearer(admin_token))
    assert empty_body_response.status_code == 415

    with no_exception_propagation(app_module):
        non_object_response = client.post(PROMPT_PATH, json=["not", "an", "object"], headers=bearer(admin_token))
    assert non_object_response.status_code == 500

    with app_module.app.app_context():
        app_module.db.session.rollback()
        after_errors = side_effect_counts(app_module)
        assert after_errors == before

    prompt_key = f"legacy_admin_9c4o_unknown_{uuid4().hex}"
    response = client.post(
        PROMPT_PATH,
        json=prompt_payload(
            prompt_key,
            api_key=SENTINEL,
            authorization=f"Bearer {SENTINEL}",
            private_metadata={"private_key": SENTINEL},
        ),
        headers=bearer(admin_token),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert "request_id" not in body
    assert_no_secret_like_data(body)
    assert "api_key" not in body["data"]
    assert "authorization" not in body["data"]
    assert "private_metadata" not in body["data"]
    with app_module.app.app_context():
        prompt = fetch_prompt(app_module, prompt_key, "v1")
        serialized_prompt = json.dumps(
            {
                "template_text": prompt.template_text,
                "json_schema": prompt.json_schema,
                "notes": prompt.notes,
            },
            ensure_ascii=False,
        )
        assert SENTINEL not in serialized_prompt


def test_prompt_mutation_upsert_write_set_template_and_secret_boundary(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = f"legacy_admin_9c4o_create_{uuid4().hex}"
    legal_template = "Use bilingual course evidence. Return JSON only."
    payload = prompt_payload(
        prompt_key,
        template_text=f"  {legal_template}  ",
        notes="  created by characterization  ",
        json_schema={"type": "object", "required": ["term"]},
        credential_metadata={"token": SENTINEL},
    )

    with app_module.app.app_context():
        app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).delete()
        app_module.db.session.commit()
        before = side_effect_counts(app_module)

    response = client.post(PROMPT_PATH, json=payload, headers=bearer(admin_token))
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"status", "message", "data"}
    assert body["message"] == "Prompt saved."
    assert "request_id" not in body
    assert "template_text" not in body["data"]
    assert_no_secret_like_data(body)

    with app_module.app.app_context():
        prompt = fetch_prompt(app_module, prompt_key, "v1")
        assert prompt.template_text == legal_template
        assert prompt.notes == "created by characterization"
        assert prompt.task_type == "term_alignment"
        assert prompt.language == "bilingual"
        assert prompt.is_active is True
        assert prompt.is_default is False
        assert prompt.created_by > 0
        assert prompt.created_at
        assert prompt.updated_at
        assert json.loads(prompt.json_schema) == {"type": "object", "required": ["term"]}
        after = side_effect_counts(app_module)
        assert after["prompts"] >= before["prompts"] + 1
        for key in (
            "provider_policy",
            "provider_usage",
            "provider_preflight",
            "verification_runs",
            "provider_calls",
            "concept_cards",
            "audit_records",
        ):
            assert after[key] == before[key]


def test_prompt_mutation_policy_runtime_required_identity_and_mutable_revision(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = f"legacy_admin_9c4p_identity_{uuid4().hex}"
    prompt_version = f"release/{uuid4().hex[:8]}"

    with app_module.app.app_context():
        app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).delete()
        app_module.db.session.commit()
        before_audit_count = app_module.AuditRecord.query.count()

    minimal_create = client.post(
        PROMPT_PATH,
        json={
            "prompt_key": f"  {prompt_key}  ",
            "prompt_version": f"  {prompt_version}  ",
        },
        headers=bearer(admin_token),
    )
    assert minimal_create.status_code == 200
    create_body = minimal_create.get_json()
    assert set(create_body) == {"status", "message", "data"}
    assert "request_id" not in create_body
    assert create_body["data"]["prompt_key"] == prompt_key
    assert create_body["data"]["prompt_version"] == prompt_version

    with app_module.app.app_context():
        created_prompt = fetch_prompt(app_module, prompt_key, prompt_version)
        created_id = created_prompt.id
        assert created_prompt.task_type == prompt_key
        assert created_prompt.template_text == ""
        assert created_prompt.prompt_version == prompt_version
        assert app_module.PromptTemplate.query.filter_by(
            prompt_key=prompt_key,
            prompt_version=prompt_version,
        ).count() == 1
        assert app_module.AuditRecord.query.count() == before_audit_count

    identical_repeat = client.post(
        PROMPT_PATH,
        json={
            "prompt_key": prompt_key,
            "prompt_version": prompt_version,
        },
        headers=bearer(admin_token),
    )
    assert identical_repeat.status_code == 200

    overwrite = client.post(
        PROMPT_PATH,
        json=prompt_payload(
            prompt_key,
            version=prompt_version,
            task_type="policy_overwrite",
            template_text="Last write replaces the mutable legacy revision.",
            notes="overwritten",
        ),
        headers=bearer(admin_token),
    )
    assert overwrite.status_code == 200

    with app_module.app.app_context():
        updated_prompt = fetch_prompt(app_module, prompt_key, prompt_version)
        assert updated_prompt.id == created_id
        assert updated_prompt.task_type == "policy_overwrite"
        assert updated_prompt.template_text == "Last write replaces the mutable legacy revision."
        assert updated_prompt.notes == "overwritten"
        assert app_module.PromptTemplate.query.filter_by(
            prompt_key=prompt_key,
            prompt_version=prompt_version,
        ).count() == 1
        assert app_module.AuditRecord.query.count() == before_audit_count

    case_variant = client.post(
        PROMPT_PATH,
        json=prompt_payload(prompt_key.upper(), version=prompt_version, template_text="case variant"),
        headers=bearer(admin_token),
    )
    assert case_variant.status_code == 200
    with app_module.app.app_context():
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key.upper()).count() == 1
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).count() == 1

    null_key_version = f"null-key-{uuid4().hex}"
    null_key_response = client.post(
        PROMPT_PATH,
        json={"prompt_key": None, "prompt_version": null_key_version},
        headers=bearer(admin_token),
    )
    assert null_key_response.status_code == 200
    with app_module.app.app_context():
        null_key_prompt = fetch_prompt(app_module, "None", null_key_version)
        assert null_key_prompt.prompt_key == "None"

    null_version_key = f"null-version-{uuid4().hex}"
    null_version_response = client.post(
        PROMPT_PATH,
        json={"prompt_key": null_version_key, "prompt_version": None},
        headers=bearer(admin_token),
    )
    assert null_version_response.status_code == 200
    with app_module.app.app_context():
        null_version_prompt = fetch_prompt(app_module, null_version_key, "None")
        assert null_version_prompt.prompt_version == "None"


def test_prompt_mutation_last_commit_wins_characterized(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = f"legacy_admin_9c4p_last_commit_{uuid4().hex}"
    prompt_version = "opaque-client-version"

    create = client.post(
        PROMPT_PATH,
        json=prompt_payload(prompt_key, version=prompt_version, template_text="base"),
        headers=bearer(admin_token),
    )
    assert create.status_code == 200

    first_client = app_module.app.test_client()
    second_client = app_module.app.test_client()

    first_write = first_client.post(
        PROMPT_PATH,
        json=prompt_payload(prompt_key, version=prompt_version, template_text="first admin write"),
        headers=bearer(admin_token),
    )
    second_write = second_client.post(
        PROMPT_PATH,
        json=prompt_payload(prompt_key, version=prompt_version, template_text="second admin write"),
        headers=bearer(admin_token),
    )

    assert first_write.status_code == 200
    assert second_write.status_code == 200
    assert first_write.status_code != 409
    assert second_write.status_code != 409
    assert "ETag" not in first_write.headers
    assert "ETag" not in second_write.headers

    with app_module.app.app_context():
        prompts = app_module.PromptTemplate.query.filter_by(
            prompt_key=prompt_key,
            prompt_version=prompt_version,
        ).all()
        assert len(prompts) == 1
        assert prompts[0].template_text == "second admin write"


def test_prompt_mutation_updates_same_version_in_place_and_does_not_manage_defaults(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = f"legacy_admin_9c4o_version_{uuid4().hex}"

    create_v1 = client.post(
        PROMPT_PATH,
        json=prompt_payload(prompt_key, version="v1", template_text="Original v1", is_default=True),
        headers=bearer(admin_token),
    )
    assert create_v1.status_code == 200

    update_v1 = client.post(
        PROMPT_PATH,
        json=prompt_payload(
            prompt_key,
            version="v1",
            template_text="Updated v1",
            task_type="translation",
            language="en",
            is_active=False,
            is_default=False,
            json_schema="not-json-schema",
            notes="updated in place",
        ),
        headers=bearer(admin_token),
    )
    assert update_v1.status_code == 200

    create_v2 = client.post(
        PROMPT_PATH,
        json=prompt_payload(prompt_key, version="v2", template_text="Version 2", is_default=True),
        headers=bearer(admin_token),
    )
    assert create_v2.status_code == 200

    with app_module.app.app_context():
        prompts = app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).order_by(
            app_module.PromptTemplate.prompt_version.asc()
        ).all()
        assert [prompt.prompt_version for prompt in prompts] == ["v1", "v2"]
        v1, v2 = prompts
        assert v1.template_text == "Updated v1"
        assert v1.task_type == "translation"
        assert v1.language == "en"
        assert v1.is_active is False
        assert v1.is_default is False
        assert v1.json_schema == "not-json-schema"
        assert v1.notes == "updated in place"
        assert v2.template_text == "Version 2"
        assert v2.is_default is True

    second_default = client.post(
        PROMPT_PATH,
        json=prompt_payload(f"{prompt_key}_other", version="v1", template_text="Other default", is_default=True),
        headers=bearer(admin_token),
    )
    assert second_default.status_code == 200

    with app_module.app.app_context():
        defaults = app_module.PromptTemplate.query.filter_by(is_default=True).all()
        assert len([prompt for prompt in defaults if prompt.prompt_key in {prompt_key, f"{prompt_key}_other"}]) == 2


def test_prompt_mutation_commit_failure_explicitly_rolls_back_and_session_can_recover(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = f"legacy_admin_9c4o_commit_failure_{uuid4().hex}"
    rollback_calls = []

    def fail_commit():
        raise RuntimeError("controlled 9c4o commit failure")

    def track_rollback():
        rollback_calls.append("rollback")

    with monkeypatch.context() as patched:
        patched.setattr(app_module.db.session, "commit", fail_commit)
        patched.setattr(app_module.db.session, "rollback", track_rollback)
        with no_exception_propagation(app_module):
                response = client.post(PROMPT_PATH, json=prompt_payload(prompt_key), headers=bearer(admin_token))

    assert response.status_code == 500
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error_code"] == "INTERNAL_ERROR"
    assert body["message"] == "Internal server error."
    assert rollback_calls == ["rollback"]

    # Recover the scoped session after the intentionally blocked commit.
    with app_module.app.app_context():
        app_module.db.session.remove()
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).first() is None

    recovery_response = client.post(
        PROMPT_PATH,
        json=prompt_payload(f"{prompt_key}_recovery"),
        headers=bearer(admin_token),
    )
    assert recovery_response.status_code == 200


def test_prompt_mutation_static_complexity_and_no_transport_boundary():
    app_source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    route_source = (ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py").read_text(
        encoding="utf-8"
    )
    service_source = (ROOT / "backend" / "services" / "legacy_provider_prompt_mutation.py").read_text(
        encoding="utf-8"
    )
    assert "def admin_ai_prompts_post_handler" not in app_source
    assert "prompt_post_handler" not in app_source
    start = route_source.index("    def admin_ai_prompts():")
    end = route_source.index("\n\n    app.add_url_rule(", start)
    block = route_source[start:end]
    assert len(block.splitlines()) <= 28
    assert "request.get_json() or {}" in block
    assert "LegacyPromptMutationRequest.from_payload" in block
    assert "prompt_mutation_service(" in block
    assert "models.PromptTemplate.query.filter_by" not in block
    assert "PromptTemplate(" not in block
    assert "db.session.commit()" not in block
    assert "db.session.rollback" not in block
    assert "AuditRecord" not in block
    assert "healthcheck_provider" not in block
    assert ".call(" not in block
    assert "provider_from_selection" not in block

    assert "PromptTemplate.query.filter_by(" in service_source
    assert "dependencies.db.session.commit()" in service_source
    assert "dependencies.db.session.rollback()" in service_source
    assert "AuditRecord" not in service_source
    assert "healthcheck_provider" not in service_source
    assert "provider_from_selection" not in service_source
