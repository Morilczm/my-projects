import pytest

from document_alignment_workflow_route_support import bearer, cleanup, create_governed_source


@pytest.fixture(autouse=True)
def clean_formal_only_state(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
    yield
    with app_module.app.app_context():
        cleanup(app_module)


def test_formal_http_and_worker_complete_while_legacy_runtime_is_disabled(
    app_module,
    client,
    teacher_token,
    monkeypatch,
):
    legacy = app_module.legacy_alignment_freeze_service
    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_RUNTIME_STATE", legacy.RUNTIME_STATE_DISABLED)
    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED", False)
    with app_module.app.app_context():
        source = create_governed_source(app_module)
        legacy_before = {
            "runs": app_module.AlignmentRun.query.count(),
            "jobs": app_module.BackgroundJob.query.filter_by(
                job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE
            ).count(),
        }

    started = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source.source_uid},
        headers={
            **bearer(teacher_token),
            "Idempotency-Key": "formal-only-runtime-9c5o",
            "X-Request-ID": "formal-only-runtime-request-9c5o",
        },
    )
    assert started.status_code == 202
    run_uid = started.get_json()["data"]["run_uid"]
    with app_module.app.app_context():
        worker = app_module.run_formal_worker_once(worker_id="formal-only-runtime-9c5o")
        assert worker.outcome in {"completed", "completed_with_warnings", "blocked", "failed"}
        formal_job = app_module.BackgroundJob.query.filter(
            app_module.BackgroundJob.job_type == app_module.FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            app_module.BackgroundJob.input_json.like(f"%{run_uid}%"),
        ).one()
        assert formal_job.execution_attempt >= 1
        assert formal_job.status in {"completed", "failed"}
        assert app_module.claim_next_legacy_alignment_job("must-remain-stopped") is None
        assert legacy_before == {
            "runs": app_module.AlignmentRun.query.count(),
            "jobs": app_module.BackgroundJob.query.filter_by(
                job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE
            ).count(),
        }

    terminal = client.get(
        f"/api/document-alignment-runs/{run_uid}",
        headers=bearer(teacher_token),
    )
    assert terminal.status_code == 200
    assert terminal.get_json()["data"]["is_terminal"] is True


def test_formal_contract_and_idempotency_scope_remain_frozen(app_module):
    assert app_module.WORKFLOW_VERSION_V1 == "formal-document-alignment-v1"
    assert app_module.FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE == (
        "formal_document_alignment_workflow_v1"
    )
    idempotency_constraint = next(
        constraint
        for constraint in app_module.DocumentAlignmentWorkflowRun.__table__.constraints
        if constraint.name == "uq_document_alignment_workflow_idempotency"
    )
    assert [column.name for column in idempotency_constraint.columns] == [
        "requested_by",
        "source_uid",
        "workflow_version",
        "idempotency_key",
    ]
