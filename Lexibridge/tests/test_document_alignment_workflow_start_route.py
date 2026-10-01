import pytest

from document_alignment_workflow_route_support import bearer, cleanup, create_governed_source, workflow_counts


@pytest.fixture(autouse=True)
def clean_formal_route_state(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
    yield
    with app_module.app.app_context():
        cleanup(app_module)


def _headers(token, key="formal-start-9c5f", request_id="request-9c5f-start"):
    return {
        **bearer(token),
        "Idempotency-Key": key,
        "X-Request-ID": request_id,
    }


def test_teacher_and_admin_start_return_202_location_and_safe_resource(
    client, app_module, teacher_token, admin_token
):
    with app_module.app.app_context():
        teacher_source = create_governed_source(app_module)
        admin_source = create_governed_source(app_module)

    teacher = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": teacher_source.source_uid},
        headers=_headers(teacher_token, "formal-start-teacher"),
    )
    admin = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": admin_source.source_uid},
        headers=_headers(admin_token, "formal-start-admin"),
    )

    assert teacher.status_code == admin.status_code == 202
    for response in (teacher, admin):
        payload = response.get_json()
        data = payload["data"]
        assert payload["status"] == "success"
        assert payload["request_id"]
        assert response.headers["Location"] == data["status_url"]
        assert response.headers["Retry-After"] == "2"
        assert response.headers["X-Request-ID"] == payload["request_id"]
        assert data["reused"] is False
        assert data["run_uid"]
        assert data["status"] == "queued"
        assert data["stage"] == "queued"
        assert "job_uid" not in data
        assert "token" not in str(payload).lower()


def test_start_requires_teacher_or_admin(client, student_token):
    anonymous = client.post("/api/document-alignment-runs", json={"source_uid": "source"})
    student = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": "source"},
        headers=_headers(student_token),
    )
    assert anonymous.status_code == 401
    assert student.status_code == 403


@pytest.mark.parametrize(
    "headers,body,content_type",
    [
        ({}, {"source_uid": "source"}, "application/json"),
        ({"Idempotency-Key": ""}, {"source_uid": "source"}, "application/json"),
        ({"Idempotency-Key": "x" * 129}, {"source_uid": "source"}, "application/json"),
        ({"Idempotency-Key": "valid"}, {"source_uid": "source", "unknown": True}, "application/json"),
        ({"Idempotency-Key": "valid"}, [], "application/json"),
        ({"Idempotency-Key": "valid"}, {"source_uid": "source"}, "text/plain"),
    ],
)
def test_start_rejects_invalid_headers_and_body(client, teacher_token, headers, body, content_type):
    response = client.post(
        "/api/document-alignment-runs",
        json=body if content_type == "application/json" else None,
        data=None if content_type == "application/json" else '{"source_uid":"source"}',
        content_type=content_type,
        headers={**bearer(teacher_token), **headers},
    )
    assert response.status_code in {400, 415}
    assert response.get_json()["status"] == "error"


def test_start_replay_reuses_run_without_duplicate_job_or_audit(client, app_module, teacher_token):
    with app_module.app.app_context():
        source = create_governed_source(app_module)
    headers = _headers(teacher_token, "formal-replay-9c5f")

    first = client.post("/api/document-alignment-runs", json={"source_uid": source.source_uid}, headers=headers)
    second = client.post("/api/document-alignment-runs", json={"source_uid": source.source_uid}, headers=headers)

    assert first.status_code == second.status_code == 202
    assert first.get_json()["data"]["run_uid"] == second.get_json()["data"]["run_uid"]
    assert first.get_json()["data"]["reused"] is False
    assert second.get_json()["data"]["reused"] is True
    with app_module.app.app_context():
        assert workflow_counts(app_module) == {"runs": 1, "jobs": 1, "audits": 1}


def test_same_key_changed_canonical_source_returns_409(client, app_module, teacher_token):
    with app_module.app.app_context():
        source = create_governed_source(app_module)
    source_uid = source.source_uid
    headers = _headers(teacher_token, "formal-conflict-9c5f")
    first = client.post("/api/document-alignment-runs", json={"source_uid": source_uid}, headers=headers)
    assert first.status_code == 202
    with app_module.app.app_context():
        source = app_module.KnowledgeSource.query.filter_by(source_uid=source_uid).one()
        source.version = "2"
        app_module.db.session.commit()
    conflict = client.post("/api/document-alignment-runs", json={"source_uid": source_uid}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.get_json()["error_code"] == "DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT"


def test_blocked_and_missing_sources_use_safe_statuses(client, app_module, teacher_token):
    headers = _headers(teacher_token, "formal-missing-9c5f")
    missing = client.post("/api/document-alignment-runs", json={"source_uid": "missing-source"}, headers=headers)
    with app_module.app.app_context():
        blocked_source = create_governed_source(app_module, chunk_count=0)
    blocked = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": blocked_source.source_uid},
        headers=_headers(teacher_token, "formal-blocked-9c5f"),
    )
    assert missing.status_code == 404
    assert blocked.status_code == 422
    assert blocked.get_json()["error_code"] == "DOCUMENT_ALIGNMENT_NO_USABLE_CHUNKS"
