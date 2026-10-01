import pytest

from document_alignment_workflow_route_support import bearer, cleanup, create_governed_source
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1,
)


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
    yield
    with app_module.app.app_context():
        cleanup(app_module)


def _post(client, token, source_uid, key, **body):
    return client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source_uid, **body},
        headers={**bearer(token), "Idempotency-Key": key},
    )


def test_http_admission_freezes_v1_retry_budget_and_replay_does_not_reset_it(
    client,
    app_module,
    teacher_token,
):
    with app_module.app.app_context():
        source = create_governed_source(app_module)
    first = _post(client, teacher_token, source.source_uid, "retry-budget-replay-9c5f2")
    assert first.status_code == 202
    assert not {
        "max_attempts",
        "attempt_count",
        "execution_attempt",
    } & set(first.get_json()["data"])
    run_uid = first.get_json()["data"]["run_uid"]
    with app_module.app.app_context():
        job = app_module.BackgroundJob.query.filter(
            app_module.BackgroundJob.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            app_module.BackgroundJob.input_json.like(f"%{run_uid}%"),
        ).one()
        assert job.max_attempts == FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1
        assert job.attempt_count == 0
        assert job.execution_attempt == 0
        # Simulate a historical task whose creation-time policy allowed no requeue.
        job.max_attempts = 1
        job.attempt_count = 1
        job.execution_attempt = 2
        app_module.db.session.commit()

    replay = _post(client, teacher_token, source.source_uid, "retry-budget-replay-9c5f2")
    assert replay.status_code == 202
    assert replay.get_json()["data"]["reused"] is True
    with app_module.app.app_context():
        jobs = app_module.BackgroundJob.query.filter_by(
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
        ).all()
        assert len(jobs) == 1
        assert jobs[0].max_attempts == 1
        assert jobs[0].attempt_count == 1
        assert jobs[0].execution_attempt == 2


def test_same_key_different_source_freezes_independent_retry_budgets(
    client,
    app_module,
    teacher_token,
):
    with app_module.app.app_context():
        first_source = create_governed_source(app_module)
        second_source = create_governed_source(app_module)
    first = _post(client, teacher_token, first_source.source_uid, "shared-retry-key-9c5f2")
    second = _post(client, teacher_token, second_source.source_uid, "shared-retry-key-9c5f2")

    assert first.status_code == second.status_code == 202
    assert first.get_json()["data"]["run_uid"] != second.get_json()["data"]["run_uid"]
    with app_module.app.app_context():
        jobs = app_module.BackgroundJob.query.filter_by(
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
        ).all()
        assert len(jobs) == 2
        assert {job.max_attempts for job in jobs} == {3}


def test_client_cannot_supply_retry_policy(client, app_module, teacher_token):
    with app_module.app.app_context():
        source = create_governed_source(app_module)

    response = _post(
        client,
        teacher_token,
        source.source_uid,
        "client-retry-policy-9c5f2",
        max_attempts=99,
    )

    assert response.status_code == 400
    with app_module.app.app_context():
        assert app_module.BackgroundJob.query.filter_by(
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
        ).count() == 0
