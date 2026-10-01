import pytest

from document_alignment_workflow_query_support import cleanup as cleanup_query, create_scenario
from document_alignment_workflow_route_support import bearer, token_for_user


@pytest.fixture(autouse=True)
def clean_query_state(app_module):
    with app_module.app.app_context():
        cleanup_query(app_module)
    yield
    with app_module.app.app_context():
        cleanup_query(app_module)


def _scenario_tokens(app_module):
    scenario = create_scenario(app_module, item_count=5, ready=2, blocked=1, failed=1)
    return scenario, {
        "requester": token_for_user(app_module, scenario["requester_id"]),
        "course_teacher": token_for_user(app_module, scenario["course_teacher_id"]),
        "unrelated": token_for_user(app_module, scenario["unrelated_teacher_id"]),
    }


def test_authorized_teachers_and_admin_can_get_run(client, app_module, admin_token):
    with app_module.app.app_context():
        scenario, tokens = _scenario_tokens(app_module)
    path = f"/api/document-alignment-runs/{scenario['run_uid']}"
    requester = client.get(path, headers=bearer(tokens["requester"]))
    course_teacher = client.get(path, headers=bearer(tokens["course_teacher"]))
    admin = client.get(path, headers=bearer(admin_token))

    assert requester.status_code == course_teacher.status_code == admin.status_code == 200
    payload = requester.get_json()
    assert payload["data"]["run_uid"] == scenario["run_uid"]
    assert payload["data"]["progress_percent"] == 80
    assert payload["request_id"]
    assert requester.headers["X-Request-ID"] == payload["request_id"]


def test_unrelated_teacher_is_anti_enumerated_and_student_anonymous_are_denied(
    client, app_module, student_token
):
    with app_module.app.app_context():
        scenario, tokens = _scenario_tokens(app_module)
    path = f"/api/document-alignment-runs/{scenario['run_uid']}"

    assert client.get(path, headers=bearer(tokens["unrelated"])).status_code == 404
    assert client.get(path, headers=bearer(student_token)).status_code == 403
    assert client.get(path).status_code == 401
    assert client.get("/api/document-alignment-runs/missing", headers=bearer(tokens["requester"])).status_code == 404


def test_run_response_hides_transport_and_raw_content(client, app_module):
    with app_module.app.app_context():
        scenario, tokens = _scenario_tokens(app_module)
    response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}",
        headers=bearer(tokens["requester"]),
    )
    text = str(response.get_json()).casefold()
    for forbidden in (
        "job_uid",
        "worker_id",
        "execution_attempt",
        "lease_token",
        "heartbeat",
        "input_json",
        "raw evidence",
        "provider output",
        "database id",
    ):
        assert forbidden not in text


def test_terminal_run_progress_is_100(client, app_module):
    with app_module.app.app_context():
        scenario = create_scenario(
            app_module,
            item_count=3,
            run_status="completed_with_warnings",
            run_stage="terminal",
            ready=1,
            blocked=1,
            failed=0,
        )
        token = token_for_user(app_module, scenario["requester_id"])
    response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}",
        headers=bearer(token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["progress_percent"] == 100
    assert response.get_json()["data"]["is_terminal"] is True


def test_get_run_rejects_request_body(client, app_module):
    with app_module.app.app_context():
        scenario, tokens = _scenario_tokens(app_module)
    response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}",
        data='{"unexpected":true}',
        content_type="application/json",
        headers=bearer(tokens["requester"]),
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST"
