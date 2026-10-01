import pytest

from document_alignment_workflow_route_support import bearer, cleanup, create_governed_source, workflow_counts


@pytest.fixture(autouse=True)
def clean_formal_route_state(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
    yield
    with app_module.app.app_context():
        cleanup(app_module)


def test_http_start_worker_poll_and_items_use_one_formal_identity(
    client, app_module, teacher_token, student_token
):
    with app_module.app.app_context():
        source = create_governed_source(app_module)
        legacy_before = {
            "runs": app_module.AlignmentRun.query.count(),
            "cards": app_module.TerminologyCard.query.count(),
            "calls": app_module.AICallLog.query.count(),
        }
    headers = {
        **bearer(teacher_token),
        "Idempotency-Key": "integration-formal-9c5f",
        "X-Request-ID": "integration-formal-request-9c5f",
    }
    started = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source.source_uid},
        headers=headers,
    )
    assert started.status_code == 202
    run_uid = started.get_json()["data"]["run_uid"]
    assert client.get(started.headers["Location"], headers=bearer(teacher_token)).status_code == 200
    initial_items = client.get(
        f"/api/document-alignment-runs/{run_uid}/items", headers=bearer(teacher_token)
    )
    assert initial_items.status_code == 200

    with app_module.app.app_context():
        worker_result = app_module.run_formal_worker_once(worker_id="formal-route-worker-9c5f")
        assert worker_result.outcome in {
            "completed",
            "completed_with_warnings",
            "blocked",
            "failed",
        }

    terminal = client.get(f"/api/document-alignment-runs/{run_uid}", headers=bearer(teacher_token))
    items = client.get(
        f"/api/document-alignment-runs/{run_uid}/items?page=1&page_size=20",
        headers=bearer(teacher_token),
    )
    replay = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source.source_uid},
        headers=headers,
    )

    assert terminal.status_code == items.status_code == 200
    assert terminal.get_json()["data"]["is_terminal"] is True
    assert terminal.get_json()["data"]["progress_percent"] == 100
    assert replay.status_code == 202
    assert replay.get_json()["data"]["run_uid"] == run_uid
    assert replay.get_json()["data"]["reused"] is True
    assert client.get(f"/api/document-alignment-runs/{run_uid}", headers=bearer(student_token)).status_code == 403
    with app_module.app.app_context():
        assert workflow_counts(app_module) == {"runs": 1, "jobs": 1, "audits": 1}
        assert {
            "runs": app_module.AlignmentRun.query.count(),
            "cards": app_module.TerminologyCard.query.count(),
            "calls": app_module.AICallLog.query.count(),
        } == legacy_before
        assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
