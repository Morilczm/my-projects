import inspect
import json
import socket
import urllib.request
import uuid
from pathlib import Path

import pytest
import yaml

from provider_admin_state_isolation import (
    assert_provider_admin_state_clean,
    capture_provider_admin_state,
    restore_provider_admin_state,
)


ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "docs" / "openapi.yaml"
FRONTEND = ROOT / "frontend" / "index.html"
DEPRECATION_ADR = ROOT / "docs" / "adr" / "ADR-legacy-alignment-run-deprecation.md"
BOUNDARY_DOC = ROOT / "docs" / "legacy_alignment_run_boundary.md"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4S"


@pytest.fixture(autouse=True)
def isolate_provider_admin_state(app_module):
    snapshot = capture_provider_admin_state(app_module)
    yield
    restore_provider_admin_state(app_module, snapshot)
    assert_provider_admin_state_clean(app_module)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["token"]


def create_reviewer_token(client, app_module):
    email = f"legacy-run-reviewer-{uuid.uuid4().hex[:8]}@lexibridge.local"
    with app_module.app.app_context():
        app_module.db.session.add(
            app_module.User(
                username=f"legacy_run_reviewer_{uuid.uuid4().hex[:8]}",
                email=email,
                password_hash=app_module.generate_password_hash("Reviewer1234", method="pbkdf2:sha256"),
                role="reviewer",
                is_verified=True,
                created_at=app_module.current_time_text(),
            )
        )
        app_module.db.session.commit()
    return login(client, email, "Reviewer1234")


def route_map(app_module):
    routes = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            routes.setdefault((rule.rule, method), []).append(rule.endpoint)
    return routes


def counts(app_module):
    return {
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "background_jobs": app_module.BackgroundJob.query.count(),
        "terminology_cards": app_module.TerminologyCard.query.count(),
        "usage_records": app_module.UsageRecord.query.count(),
        "ai_call_logs": app_module.AICallLog.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
    }


def unique_term(prefix="LegacyRun"):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def post_legacy_run(client, token, payload=None, *, sync=False, request_id=None, raw_data=None, content_type=None):
    headers = bearer(token)
    if request_id:
        headers["X-Request-ID"] = request_id
    path = "/api/alignment/run"
    if sync:
        path = f"{path}?sync=true"
    if raw_data is not None:
        return client.post(path, data=raw_data, content_type=content_type, headers=headers)
    return client.post(path, json=payload if payload is not None else {}, headers=headers)


def assert_no_secret_payload(value):
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    forbidden = [
        SENTINEL,
        "Bearer sentinel",
        "Authorization",
        "Cookie",
        "private key",
        "password",
        "api_key",
    ]
    for item in forbidden:
        assert item not in serialized


def install_network_guards(monkeypatch):
    calls = {"socket": 0, "urlopen": 0}

    def blocked_socket(*args, **kwargs):
        calls["socket"] += 1
        raise AssertionError("legacy alignment run attempted socket access")

    def blocked_urlopen(*args, **kwargs):
        calls["urlopen"] += 1
        raise AssertionError("legacy alignment run attempted urllib transport")

    monkeypatch.setattr(socket, "socket", blocked_socket)
    monkeypatch.setattr(urllib.request, "urlopen", blocked_urlopen)
    return calls


def fail_if_formal_gate_called(monkeypatch, app_module):
    gate_calls = {"policy": 0, "preflight": 0}

    def policy_gate(*args, **kwargs):
        gate_calls["policy"] += 1
        raise AssertionError("legacy alignment run unexpectedly invoked formal provider policy")

    def preflight_gate(*args, **kwargs):
        gate_calls["preflight"] += 1
        raise AssertionError("legacy alignment run unexpectedly invoked provider preflight")

    monkeypatch.setattr(app_module.provider_governance_service, "evaluate_provider_request", policy_gate)
    monkeypatch.setattr(app_module.provider_preflight_service, "run_provider_preflight", preflight_gate)
    return gate_calls


def create_document_with_chunk(app_module, course, owner_user_id=0, scope_type="course", content=None):
    document = app_module.Document(
        owner_user_id=owner_user_id,
        course_id=course.id if course else None,
        scope_type=scope_type,
        filename=f"legacy-run-{uuid.uuid4().hex[:8]}.txt",
        original_filename="legacy-run.txt",
        content_type="text/plain",
        size_bytes=128,
        file_type="txt",
        language="en",
        parsing_status="parsed",
        parse_uid=f"parse-{uuid.uuid4().hex}",
        upload_time=app_module.current_time_text(),
    )
    app_module.db.session.add(document)
    app_module.db.session.flush()
    chunk = app_module.DocumentChunk(
        document_id=document.id,
        course_id=course.id if course else None,
        owner_user_id=owner_user_id,
        chunk_index=0,
        parse_uid=document.parse_uid,
        parse_block_uid=f"block-{uuid.uuid4().hex}",
        language="en",
        section_title="Frequency Domain",
        content=content or f"Legacy Boundary Transform {uuid.uuid4().hex[:8]} converts a signal across domains.",
        source_type="teacher_upload",
        source_location="page 1",
        ocr_confidence=100,
    )
    app_module.db.session.add(chunk)
    app_module.db.session.commit()
    return document, chunk


def test_legacy_alignment_run_route_registration_frontend_and_openapi(app_module):
    routes = route_map(app_module)
    assert routes[("/api/alignment/run", "POST")] == ["run_alignment"]
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/alignment/run" and "POST" in rule.methods
    ) == 1

    handler = app_module.app.view_functions["run_alignment"]
    source = inspect.getsource(handler)
    assert handler.__module__ == "lexibridge_test_app"
    assert "@app.route(\"/api/alignment/run\", methods=[\"POST\"])" in Path("backend/app.py").read_text(encoding="utf-8")
    assert "require_current_user({\"student\", \"teacher\", \"admin\"})" in source
    assert "run_alignment_for_chunks(" in source
    assert "generate_alignment_result(" in source
    assert "create_or_update_card_from_alignment(" in source
    assert "db.session.commit()" in source
    assert "rollback" not in source
    assert "AlignmentVerificationRun" not in source
    assert "record_alignment_provider_usage" not in source
    assert "evaluate_provider_request" not in source

    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    assert "/api/alignment/run" in contract["paths"]
    assert "post" in contract["paths"]["/api/alignment/run"]
    operation = contract["paths"]["/api/alignment/run"]["post"]
    assert operation["deprecated"] is True
    description = operation["description"]
    assert "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED" in description
    assert "LEGACY_ALIGNMENT_RUN_DEPRECATED" in description
    assert "not HTTP 410" in description
    frontend = FRONTEND.read_text(encoding="utf-8")
    formal_module = (ROOT / "frontend" / "js" / "formal-workflow.js").read_text(encoding="utf-8")
    assert 'api("/api/alignment/run"' not in frontend
    assert "startFormalAlignmentForDocument" in frontend
    assert "/api/document-alignment-runs" in formal_module
    assert "/api/alignment/run" not in formal_module


def test_legacy_alignment_run_deprecation_policy_matches_current_compatibility_state(app_module):
    adr = DEPRECATION_ADR.read_text(encoding="utf-8")
    boundary = BOUNDARY_DOC.read_text(encoding="utf-8")
    app_source = Path("backend/app.py").read_text(encoding="utf-8")
    frontend = FRONTEND.read_text(encoding="utf-8")
    routes = route_map(app_module)

    assert "Status: ACCEPTED_FOR_SMALL_PILOT" in adr
    assert "Policy name: LEGACY_ALIGNMENT_RUN_DEPRECATION_V1" in adr
    assert "Endpoint role: TEMPORARY_FRONTEND_COMPATIBILITY_ONLY" in adr
    assert "LEGACY_EXTERNAL_EXECUTION_PROHIBITED" in adr
    assert "LOCAL_OR_DETERMINISTIC_ONLY" in adr
    assert "FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION" in adr
    assert "NO_LEGACY_AND_FORMAL_DUAL_WRITE" in adr
    assert "RETAIN_READ_ONLY_AFTER_CUTOVER" in adr
    assert "REPLACEMENT_FIRST_THEN_CUTOVER" in adr
    assert "LEGACY_ALIGNMENT_RUN_DEPRECATED" in adr
    assert "Directly Extract The Existing Handler As A Service" in adr
    assert "Transparent Forward To `/api/alignment/verify`" in adr

    assert routes[("/api/alignment/run", "POST")] == ["run_alignment"]
    assert "LEGACY_ALIGNMENT_RUN_DEPRECATED" not in app_source
    assert 'api("/api/alignment/run"' not in frontend
    assert "startFormalAlignmentForDocument" in frontend
    assert "/api/alignment/run" in boundary
    assert "Frontend Migration Checklist" in boundary
    assert "Task 9C.4U" in adr
    assert "Task 9C.5A" in adr
    assert routes[("/api/document-alignment-runs", "POST")] == [
        "create_document_alignment_run"
    ]
    assert routes[("/api/document-alignment-runs/<run_uid>", "GET")] == [
        "get_document_alignment_run"
    ]
    assert routes[("/api/document-alignment-runs/<run_uid>/items", "GET")] == [
        "list_document_alignment_run_items"
    ]


def test_legacy_alignment_run_auth_roles_and_body_error_contract(
    client,
    app_module,
    teacher_token,
    student_token,
    admin_token,
):
    reviewer_token = create_reviewer_token(client, app_module)
    unauth = client.post("/api/alignment/run", json={"english_term": unique_term()})
    assert unauth.status_code == 401
    assert unauth.get_json()["error_code"] == "AUTH_REQUIRED"
    assert "request_id" not in unauth.get_json()

    reviewer = post_legacy_run(client, reviewer_token, {"english_term": unique_term()})
    assert reviewer.status_code == 403
    assert reviewer.get_json()["error_code"] == "PERMISSION_DENIED"

    student_course = post_legacy_run(client, student_token, {"english_term": unique_term(), "scope_type": "course"})
    assert student_course.status_code == 403
    assert student_course.get_json()["error_code"] == "PERMISSION_DENIED"

    teacher_empty = post_legacy_run(client, teacher_token, {})
    assert teacher_empty.status_code == 403
    assert teacher_empty.get_json()["error_code"] == "PERMISSION_DENIED"

    invalid_scope = post_legacy_run(client, admin_token, {"scope_type": "global", "english_term": unique_term()})
    assert invalid_scope.status_code == 400
    assert invalid_scope.get_json()["error_code"] == "VALIDATION_ERROR"

    malformed = post_legacy_run(
        client,
        teacher_token,
        raw_data="{",
        content_type="application/json",
    )
    assert malformed.status_code == 400

    old_testing = app_module.app.config.get("TESTING")
    old_propagate = app_module.app.config.get("PROPAGATE_EXCEPTIONS")
    app_module.app.config["TESTING"] = False
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        non_object = post_legacy_run(client, teacher_token, payload=["not", "an", "object"])
        assert non_object.status_code == 500
        assert non_object.get_json()["error_code"] == "INTERNAL_ERROR"
    finally:
        app_module.app.config["TESTING"] = old_testing
        app_module.app.config["PROPAGATE_EXCEPTIONS"] = old_propagate
        with app_module.app.app_context():
            app_module.db.session.rollback()


def test_legacy_alignment_run_default_async_enqueues_without_execution_or_formal_writes(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    network_calls = install_network_guards(monkeypatch)
    formal_calls = fail_if_formal_gate_called(monkeypatch, app_module)
    term = unique_term()
    with app_module.app.app_context():
        before = counts(app_module)

    response = post_legacy_run(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": term,
            "courseware_sentence": "Fourier Transform converts a signal.",
            "api_key": SENTINEL,
            "Authorization": f"Bearer {SENTINEL}",
            "unknown_metadata": {"credential": SENTINEL},
        },
        request_id="legacy-run-async",
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "success"
    assert "request_id" not in body
    data = body["data"]
    assert data["alignment_run_id"]
    assert data["job_id"]
    assert data["job_type"] == "alignment_run"
    assert data["job_status"] == "queued"
    assert data["run"]["status"] == "queued"
    assert_no_secret_payload(body)
    assert network_calls == {"socket": 0, "urlopen": 0}
    assert formal_calls == {"policy": 0, "preflight": 0}

    with app_module.app.app_context():
        after = counts(app_module)
        assert after["alignment_runs"] == before["alignment_runs"] + 1
        assert after["background_jobs"] == before["background_jobs"] + 1
        assert after["terminology_cards"] == before["terminology_cards"]
        assert after["usage_records"] == before["usage_records"]
        assert after["ai_call_logs"] == before["ai_call_logs"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["audit_records"] == before["audit_records"]
        assert after["concept_cards"] == before["concept_cards"]
        job = app_module.db.session.get(app_module.BackgroundJob, data["job_id"])
        assert SENTINEL not in job.input_json


def test_legacy_alignment_run_sync_direct_uses_legacy_execution_bypasses_formal_gates_and_writes_card(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    network_calls = install_network_guards(monkeypatch)
    formal_calls = fail_if_formal_gate_called(monkeypatch, app_module)
    provider_calls = {"count": 0}
    original_provider_from_selection = app_module.provider_from_selection

    def provider_spy(selection):
        provider_calls["count"] += 1
        return original_provider_from_selection(selection)

    monkeypatch.setattr(app_module, "provider_from_selection", provider_spy)
    term = unique_term("SyncDirect")
    with app_module.app.app_context():
        before = counts(app_module)

    response = post_legacy_run(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": term,
            "courseware_sentence": "A direct sync legacy alignment request.",
            "chapter": "Frequency Domain",
            "api_key": SENTINEL,
        },
        sync=True,
        request_id="legacy-run-sync-direct",
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "success"
    assert "data" not in body
    assert "request_id" not in body
    assert body["alignment"]["english_term"] == term
    assert body["alignment"]["prompt_key"] == "term_alignment"
    assert body["alignment"]["prompt_version"] == "v1"
    assert body["card"]["english_term"] == term
    assert body["card"]["status"] in {"needs_more_evidence", "pending_quality_control"}
    assert_no_secret_payload(body)
    assert network_calls == {"socket": 0, "urlopen": 0}
    assert provider_calls["count"] == 0
    assert formal_calls == {"policy": 0, "preflight": 0}

    with app_module.app.app_context():
        after = counts(app_module)
        assert after["alignment_runs"] == before["alignment_runs"] + 1
        assert after["background_jobs"] == before["background_jobs"]
        assert after["terminology_cards"] == before["terminology_cards"] + 1
        assert after["ai_call_logs"] == before["ai_call_logs"]
        assert after["usage_records"] == before["usage_records"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["audit_records"] == before["audit_records"]
        assert after["concept_cards"] == before["concept_cards"]


def test_legacy_alignment_run_sync_document_creates_legacy_run_and_cards_not_formal_verification(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    network_calls = install_network_guards(monkeypatch)
    formal_calls = fail_if_formal_gate_called(monkeypatch, app_module)
    with app_module.app.app_context():
        document, _chunk = create_document_with_chunk(app_module, test_course)
        document_id = document.id
        before = counts(app_module)

    response = post_legacy_run(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "document_id": document_id,
            "api_key": SENTINEL,
        },
        sync=True,
        request_id="legacy-run-sync-document",
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "success"
    assert "cards" in body
    assert "data" not in body
    assert "request_id" not in body
    assert len(body["cards"]) >= 1
    assert_no_secret_payload(body)
    assert network_calls == {"socket": 0, "urlopen": 0}
    assert formal_calls == {"policy": 0, "preflight": 0}

    with app_module.app.app_context():
        after = counts(app_module)
        assert after["alignment_runs"] == before["alignment_runs"] + 1
        assert after["background_jobs"] == before["background_jobs"]
        assert after["terminology_cards"] >= before["terminology_cards"] + 1
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert after["audit_records"] == before["audit_records"]
        assert after["concept_cards"] == before["concept_cards"]


def test_legacy_alignment_run_live_transport_intent_is_blocked_before_request_construction(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    transport_calls = {"request": 0, "urlopen": 0}

    def request_spy(*args, **kwargs):
        transport_calls["request"] += 1
        raise AssertionError("legacy live urllib Request should not be constructed")

    def transport_spy(*args, **kwargs):
        transport_calls["urlopen"] += 1
        raise AssertionError("legacy live urlopen should not be called")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("legacy live transport reached raw socket")

    monkeypatch.setattr(socket, "socket", blocked_socket)
    monkeypatch.setattr(urllib.request, "Request", request_spy)
    monkeypatch.setattr(urllib.request, "urlopen", transport_spy)
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("AI_PROVIDER_MODE", "live")
    monkeypatch.setenv("DEEPSEEK_API_KEY", SENTINEL)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", f"https://example.invalid/v1?token={SENTINEL}")
    with app_module.app.app_context():
        app_module.AI_PROVIDER = "deepseek"
        app_module.AI_PROVIDER_MODE = "live"
        app_module.DEEPSEEK_API_KEY = SENTINEL
        app_module.DEEPSEEK_BASE_URL = f"https://example.invalid/v1?token={SENTINEL}"
        app_module.db.session.add(
            app_module.AIProviderConfig(
                provider_name="deepseek",
                provider_mode="live",
                default_model="deepseek-chat",
                base_url=f"https://example.invalid/v1?token={SENTINEL}",
                is_enabled=True,
                is_default=True,
                created_at=app_module.current_time_text(),
            )
        )
        app_module.db.session.commit()
        before = counts(app_module)

    response = post_legacy_run(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": unique_term("LiveIntent"),
            "courseware_sentence": "Legacy live provider intent should be stopped before network.",
        },
        sync=True,
        request_id="legacy-run-live-intent",
    )

    assert response.status_code == 422, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error_code"] == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"
    assert body["reason_code"] == "LEGACY_ALIGNMENT_EXTERNAL_PROVIDER_DISABLED"
    assert transport_calls == {"request": 0, "urlopen": 0}
    assert_no_secret_payload(body)
    with app_module.app.app_context():
        after = counts(app_module)
        assert after["alignment_runs"] == before["alignment_runs"]
        assert after["background_jobs"] == before["background_jobs"]
        assert after["terminology_cards"] == before["terminology_cards"]
        assert after["usage_records"] == before["usage_records"]
        assert after["ai_call_logs"] == before["ai_call_logs"]
        assert after["verification_runs"] == before["verification_runs"]
        assert after["provider_usage"] == before["provider_usage"]
        assert after["provider_preflight"] == before["provider_preflight"]
        assert app_module.AuditRecord.query.filter(app_module.AuditRecord.error_message.contains(SENTINEL)).count() == 0
        assert app_module.AICallLog.query.filter(app_module.AICallLog.error_message.contains(SENTINEL)).count() == 0
        assert app_module.AlignmentRun.query.filter(app_module.AlignmentRun.error_message.contains(SENTINEL)).count() == 0
        assert app_module.TerminologyCard.query.filter(app_module.TerminologyCard.risk_note.contains(SENTINEL)).count() == 0


def test_legacy_alignment_run_repeated_async_request_is_not_idempotent(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    install_network_guards(monkeypatch)
    term = unique_term("RepeatAsync")
    payload = {
        "scope_type": "course",
        "course_id": test_course.id,
        "english_term": term,
        "courseware_sentence": "Repeated request characterization.",
    }
    with app_module.app.app_context():
        before = counts(app_module)
    first = post_legacy_run(client, teacher_token, payload, request_id="legacy-run-repeat-1")
    second = post_legacy_run(client, teacher_token, payload, request_id="legacy-run-repeat-2")
    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.get_json()["data"]
    second_body = second.get_json()["data"]
    assert first_body["alignment_run_id"] != second_body["alignment_run_id"]
    assert first_body["job_id"] != second_body["job_id"]
    with app_module.app.app_context():
        after = counts(app_module)
        assert after["alignment_runs"] == before["alignment_runs"] + 2
        assert after["background_jobs"] == before["background_jobs"] + 2


def test_legacy_alignment_run_commit_failure_has_no_handler_rollback_but_session_can_be_recovered(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    source = inspect.getsource(app_module.app.view_functions["run_alignment"])
    assert "db.session.commit()" in source
    assert "rollback" not in source

    original_commit = app_module.db.session.commit
    commit_calls = {"count": 0}

    def fail_once():
        commit_calls["count"] += 1
        if commit_calls["count"] == 1:
            raise RuntimeError("controlled legacy alignment commit failure")
        return original_commit()

    monkeypatch.setattr(app_module.db.session, "commit", fail_once)
    old_testing = app_module.app.config.get("TESTING")
    old_propagate = app_module.app.config.get("PROPAGATE_EXCEPTIONS")
    app_module.app.config["TESTING"] = False
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
    response = post_legacy_run(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": unique_term("CommitFailure"),
        },
    )
    assert response.status_code == 500
    assert response.get_json()["error_code"] == "INTERNAL_ERROR"
    with app_module.app.app_context():
        app_module.db.session.rollback()
    app_module.app.config["TESTING"] = old_testing
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = old_propagate
    monkeypatch.setattr(app_module.db.session, "commit", original_commit)

    recovery = post_legacy_run(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": unique_term("CommitRecovery"),
        },
    )
    assert recovery.status_code == 200, recovery.get_data(as_text=True)


def test_legacy_alignment_run_differs_from_formal_verification_write_set(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    install_network_guards(monkeypatch)
    with app_module.app.app_context():
        before = counts(app_module)

    legacy = post_legacy_run(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": unique_term("FormalCompareLegacy"),
        },
        request_id="legacy-run-compare",
    )
    assert legacy.status_code == 200, legacy.get_data(as_text=True)
    with app_module.app.app_context():
        after_legacy = counts(app_module)

    formal = client.post(
        "/api/alignment/verify",
        json={
            "provider": "mock-rule-v1",
            "english_term": unique_term("FormalCompare"),
            "chinese_term": "形式化验证",
            "course": "Formal Comparison",
            "english_evidence": [{"snippet": "formal evidence", "score": 0.8}],
            "chinese_evidence": [{"snippet": "正式证据", "score": 0.8}],
        },
        headers={**bearer(teacher_token), "X-Request-ID": "legacy-run-formal-compare"},
    )
    assert formal.status_code == 200, formal.get_data(as_text=True)
    formal_body = formal.get_json()
    assert formal_body["request_id"] == "legacy-run-formal-compare"
    with app_module.app.app_context():
        after_formal = counts(app_module)
        assert after_legacy["alignment_runs"] == before["alignment_runs"] + 1
        assert after_legacy["background_jobs"] == before["background_jobs"] + 1
        assert after_legacy["verification_runs"] == before["verification_runs"]
        assert after_legacy["provider_usage"] == before["provider_usage"]
        assert after_legacy["audit_records"] == before["audit_records"]

        assert after_formal["alignment_runs"] == after_legacy["alignment_runs"]
        assert after_formal["background_jobs"] == after_legacy["background_jobs"]
        assert after_formal["verification_runs"] == after_legacy["verification_runs"] + 1
        assert after_formal["provider_usage"] == after_legacy["provider_usage"] + 1
        assert after_formal["audit_records"] > after_legacy["audit_records"]
        assert after_formal["concept_cards"] == after_legacy["concept_cards"]
