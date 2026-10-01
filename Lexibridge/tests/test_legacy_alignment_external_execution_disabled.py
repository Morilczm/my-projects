import json
import socket
import urllib.request
import uuid
from pathlib import Path

import pytest

from provider_admin_state_isolation import (
    assert_provider_admin_state_clean,
    capture_provider_admin_state,
    restore_provider_admin_state,
)


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4U"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_provider_admin_state(app_module):
    snapshot = capture_provider_admin_state(app_module)
    yield
    restore_provider_admin_state(app_module, snapshot)
    assert_provider_admin_state_clean(app_module)


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def counts(app_module):
    return {
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "background_jobs": app_module.BackgroundJob.query.count(),
        "terminology_cards": app_module.TerminologyCard.query.count(),
        "usage_records": app_module.UsageRecord.query.count(),
        "ai_call_logs": app_module.AICallLog.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
    }


def install_zero_transport_spies(monkeypatch, app_module):
    calls = {
        "request": 0,
        "urlopen": 0,
        "socket": 0,
        "provider_selection": 0,
        "provider": 0,
        "metadata": 0,
    }

    def request_spy(*args, **kwargs):
        calls["request"] += 1
        raise AssertionError("urllib Request must not be constructed")

    def urlopen_spy(*args, **kwargs):
        calls["urlopen"] += 1
        raise AssertionError("urlopen must not be called")

    def socket_spy(*args, **kwargs):
        calls["socket"] += 1
        raise AssertionError("socket must not be opened")

    def provider_selection_spy(*args, **kwargs):
        calls["provider_selection"] += 1
        raise AssertionError("credential-bearing provider selection must not be built")

    def provider_spy(*args, **kwargs):
        calls["provider"] += 1
        raise AssertionError("provider adapter must not be initialized")

    def metadata_spy(*args, **kwargs):
        calls["metadata"] += 1
        raise AssertionError("current_provider_metadata must not run on blocked path")

    monkeypatch.setattr(urllib.request, "Request", request_spy)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen_spy)
    monkeypatch.setattr(socket, "socket", socket_spy)
    monkeypatch.setattr(app_module, "ai_selection_from_config", provider_selection_spy)
    monkeypatch.setattr(app_module, "provider_from_selection", provider_spy)
    monkeypatch.setattr(app_module, "current_provider_metadata", metadata_spy)
    return calls


def create_live_default_provider(app_module, *, credential_present=True):
    app_module.AI_PROVIDER = "deepseek"
    app_module.AI_PROVIDER_MODE = "live"
    app_module.DEEPSEEK_API_KEY = SENTINEL if credential_present else ""
    app_module.DEEPSEEK_BASE_URL = f"https://example.invalid/v1?token={SENTINEL}"
    for config in app_module.AIProviderConfig.query.filter_by(is_default=True).all():
        config.is_default = False
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


def post_alignment(client, teacher_token, payload):
    return client.post("/api/alignment/run", json=payload, headers=auth_header(teacher_token))


def assert_safe_blocked_response(response):
    assert response.status_code == 422
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error_code"] == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"
    assert "LEGACY_ALIGNMENT_RUN_DEPRECATED" not in json.dumps(body)
    assert SENTINEL not in json.dumps(body, ensure_ascii=False)
    assert "urllib" not in json.dumps(body, ensure_ascii=False).lower()
    assert "api key" not in json.dumps(body, ensure_ascii=False).lower()
    return body


def test_no_hidden_switch_reenables_legacy_alignment_external_execution():
    source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")

    assert "LEGACY_ALIGNMENT_RUN_DEPRECATED" not in source
    for forbidden in [
        "ENABLE_LEGACY_ALIGNMENT_EXTERNAL",
        "ALLOW_LEGACY_ALIGNMENT_EXTERNAL",
        "legacy_alignment_external_enabled",
        "debug_legacy_alignment_external",
        "test_legacy_alignment_external",
    ]:
        assert forbidden not in source


def test_default_live_provider_route_blocks_before_credentials_transport_or_writes(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    with app_module.app.app_context():
        create_live_default_provider(app_module, credential_present=True)
        before = counts(app_module)
    calls = install_zero_transport_spies(monkeypatch, app_module)

    response = post_alignment(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": f"External Disabled {uuid.uuid4().hex[:8]}",
            "courseware_sentence": "External legacy provider must not execute.",
        },
    )

    body = assert_safe_blocked_response(response)
    assert body["reason_code"] == "LEGACY_ALIGNMENT_EXTERNAL_PROVIDER_DISABLED"
    assert calls == {
        "request": 0,
        "urlopen": 0,
        "socket": 0,
        "provider_selection": 0,
        "provider": 0,
        "metadata": 0,
    }
    with app_module.app.app_context():
        assert counts(app_module) == before
        assert not app_module.db.session.new
        assert not app_module.db.session.dirty
        assert not app_module.db.session.deleted


def test_direct_alignment_helper_blocks_live_default_before_legacy_transport(
    app_module,
    test_course,
    monkeypatch,
):
    with app_module.app.app_context():
        create_live_default_provider(app_module, credential_present=True)
        before = counts(app_module)
    calls = install_zero_transport_spies(monkeypatch, app_module)

    with app_module.app.app_context(), pytest.raises(RuntimeError) as exc_info:
        app_module.generate_alignment_result(
            english_term=f"Direct Helper Blocked {uuid.uuid4().hex[:8]}",
            courseware_sentence="Direct helper must not execute legacy transport.",
            course=test_course.name,
        )

    assert "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED" in str(exc_info.value)
    assert calls == {
        "request": 0,
        "urlopen": 0,
        "socket": 0,
        "provider_selection": 0,
        "provider": 0,
        "metadata": 0,
    }
    with app_module.app.app_context():
        assert counts(app_module) == before


def test_credential_present_and_absent_external_blocks_have_same_contract(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    payload = {
        "scope_type": "course",
        "course_id": test_course.id,
        "english_term": f"External Parity {uuid.uuid4().hex[:8]}",
        "provider": "deepseek",
    }
    with app_module.app.app_context():
        create_live_default_provider(app_module, credential_present=True)
    install_zero_transport_spies(monkeypatch, app_module)
    present = post_alignment(client, teacher_token, payload)
    present_body = assert_safe_blocked_response(present)

    monkeypatch.undo()
    with app_module.app.app_context():
        restore_provider_admin_state(app_module, capture_provider_admin_state(app_module))
        create_live_default_provider(app_module, credential_present=False)
    install_zero_transport_spies(monkeypatch, app_module)
    absent = post_alignment(client, teacher_token, payload)
    absent_body = assert_safe_blocked_response(absent)

    assert present.status_code == absent.status_code
    assert present_body["error_code"] == absent_body["error_code"]
    assert present_body["message"] == absent_body["message"]


@pytest.mark.parametrize(
    "payload_provider",
    ["deepseek", "openai", "custom_openai_compatible", "external", "custom-provider", "mock-deepseek"],
)
def test_explicit_external_unknown_and_custom_provider_fail_closed(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
    payload_provider,
):
    calls = install_zero_transport_spies(monkeypatch, app_module)
    with app_module.app.app_context():
        before = counts(app_module)

    response = post_alignment(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": f"Blocked Provider {uuid.uuid4().hex[:8]}",
            "provider": payload_provider,
            "base_url": f"https://example.invalid/v1?token={SENTINEL}" if payload_provider == "custom-provider" else "",
        },
    )

    assert_safe_blocked_response(response)
    assert calls["request"] == 0
    assert calls["urlopen"] == 0
    assert calls["socket"] == 0
    with app_module.app.app_context():
        assert counts(app_module) == before


def test_local_deterministic_route_flow_remains_available(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    calls = {"request": 0, "urlopen": 0, "socket": 0}

    monkeypatch.setattr(urllib.request, "Request", lambda *args, **kwargs: calls.__setitem__("request", calls["request"] + 1))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: calls.__setitem__("urlopen", calls["urlopen"] + 1))
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: calls.__setitem__("socket", calls["socket"] + 1))

    response = post_alignment(
        client,
        teacher_token,
        {
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": f"Local Allowed {uuid.uuid4().hex[:8]}",
            "courseware_sentence": "Local deterministic alignment remains queued.",
            "provider": "mock",
        },
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "success"
    assert body["data"]["job_status"] == "queued"
    assert calls == {"request": 0, "urlopen": 0, "socket": 0}
