import json
import socket
import urllib.request
import uuid

import pytest

from provider_admin_state_isolation import (
    assert_provider_admin_state_clean,
    capture_provider_admin_state,
    restore_provider_admin_state,
)


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4U"


@pytest.fixture(autouse=True)
def isolate_provider_admin_state(app_module):
    snapshot = capture_provider_admin_state(app_module)
    yield
    restore_provider_admin_state(app_module, snapshot)
    assert_provider_admin_state_clean(app_module)


def counts(app_module):
    return {
        "terminology_cards": app_module.TerminologyCard.query.count(),
        "usage_records": app_module.UsageRecord.query.count(),
        "ai_call_logs": app_module.AICallLog.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
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
        raise AssertionError("current_provider_metadata must not run on blocked worker path")

    monkeypatch.setattr(urllib.request, "Request", request_spy)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen_spy)
    monkeypatch.setattr(socket, "socket", socket_spy)
    monkeypatch.setattr(app_module, "ai_selection_from_config", provider_selection_spy)
    monkeypatch.setattr(app_module, "provider_from_selection", provider_spy)
    monkeypatch.setattr(app_module, "current_provider_metadata", metadata_spy)
    return calls


def create_alignment_job(app_module, user_id, course, *, provider="deepseek", status="queued"):
    run = app_module.AlignmentRun(
        course_id=course.id,
        triggered_by=user_id,
        provider=provider,
        model_name="deepseek-chat",
        ai_provider=provider,
        ai_provider_mode="live" if provider != "mock" else "mock",
        ai_model="deepseek-chat" if provider != "mock" else "mock",
        prompt_key="term_alignment",
        prompt_version="v1",
        retrieval_version=app_module.RETRIEVAL_VERSION,
        term_count=1,
        status="queued",
        started_at="",
    )
    app_module.db.session.add(run)
    app_module.db.session.flush()
    job = app_module.create_background_job(
        "alignment_run",
        user_id,
        course_id=course.id,
        alignment_run_id=run.id,
        scope_type="course",
        input_data={
            "provider": provider,
            "english_term": f"Worker External {uuid.uuid4().hex[:8]}",
            "courseware_sentence": "Worker must quarantine external legacy jobs.",
            "scope_type": "course",
            "course_id": course.id,
            "Authorization": f"Bearer {SENTINEL}",
            "base_url": f"https://example.invalid/v1?token={SENTINEL}",
        },
    )
    job.status = status
    app_module.db.session.commit()
    return run, job


def teacher_id(app_module):
    return app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first().id


@pytest.mark.parametrize("initial_status", ["queued", "retrying", "running"])
def test_worker_quarantines_external_alignment_job_before_credentials_transport_or_business_writes(
    app_module,
    test_course,
    monkeypatch,
    initial_status,
):
    with app_module.app.app_context():
        _run, job = create_alignment_job(app_module, teacher_id(app_module), test_course, status=initial_status)
        job_id = job.id
        before = counts(app_module)
    calls = install_zero_transport_spies(monkeypatch, app_module)

    with app_module.app.app_context():
        processed = app_module.run_background_job(job_id, worker_id="pytest-worker")

        assert processed.status == "failed"
        assert processed.error_code == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"
        assert SENTINEL not in (processed.error_message or "")
        assert processed.attempt_count == 1
        assert counts(app_module) == before
        assert calls == {
            "request": 0,
            "urlopen": 0,
            "socket": 0,
            "provider_selection": 0,
            "provider": 0,
            "metadata": 0,
        }

        repeated = app_module.run_background_job(job_id, worker_id="pytest-worker-repeat")
        assert repeated.status == "failed"
        assert calls["request"] == 0
        assert calls["urlopen"] == 0
        assert calls["socket"] == 0


@pytest.mark.parametrize("provider", ["unknown-provider", "custom_openai_compatible", "mock-deepseek"])
def test_worker_unknown_and_custom_alignment_jobs_fail_closed(
    app_module,
    test_course,
    monkeypatch,
    provider,
):
    with app_module.app.app_context():
        _run, job = create_alignment_job(app_module, teacher_id(app_module), test_course, provider=provider)
        job_id = job.id
    calls = install_zero_transport_spies(monkeypatch, app_module)

    with app_module.app.app_context():
        processed = app_module.run_background_job(job_id, worker_id="pytest-worker")

        assert processed.status == "failed"
        assert processed.error_code == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"
        assert json.loads(processed.result_json or "{}") == {}
        assert calls["request"] == 0
        assert calls["urlopen"] == 0
        assert calls["socket"] == 0


def test_external_alignment_job_retry_remains_blocked_after_quarantine(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    with app_module.app.app_context():
        _run, job = create_alignment_job(app_module, teacher_id(app_module), test_course)
        job_id = job.id
    calls = install_zero_transport_spies(monkeypatch, app_module)

    with app_module.app.app_context():
        processed = app_module.run_background_job(job_id, worker_id="pytest-worker")
        assert processed.status == "failed"
        assert processed.error_code == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"

    retry_response = client.post(
        f"/api/jobs/{job_id}/retry",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )

    assert retry_response.status_code == 422
    body = retry_response.get_json()
    assert body["error_code"] == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"
    assert body["retry_blocked"] is True
    with app_module.app.app_context():
        reloaded = app_module.db.session.get(app_module.BackgroundJob, job_id)
        assert reloaded.status == "failed"
        assert reloaded.error_code == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"
    assert calls["request"] == 0
    assert calls["urlopen"] == 0
    assert calls["socket"] == 0


def test_worker_local_deterministic_alignment_job_still_completes(
    client,
    app_module,
    teacher_token,
    test_course,
    monkeypatch,
):
    response = client.post(
        "/api/alignment/run",
        json={
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": f"Worker Local {uuid.uuid4().hex[:8]}",
            "courseware_sentence": "Local deterministic worker flow remains available.",
            "provider": "mock",
        },
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    job_id = response.get_json()["data"]["job_id"]

    with app_module.app.app_context():
        job = app_module.run_background_job(job_id, worker_id="pytest-worker")
        assert job.status == "completed"
        assert job.error_code == ""
