import json
from pathlib import Path

import pytest

from document_alignment_workflow_route_support import bearer
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1,
    FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION,
)
from services.formal_document_alignment_provider_selection import (
    FORMAL_DEFAULT_MODEL_IDENTITY,
    FORMAL_DEFAULT_PROVIDER_NAME,
)
from test_document_alignment_worker_integration import _cleanup, _setup_source


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_WORKFLOW_VERSION = "formal-document-alignment-v1"
CANONICAL_JOB_TYPE = "formal_document_alignment_workflow_v1"
STALE_WORKFLOW_VERSION = "formal-document-alignment-workflow-v1"


@pytest.fixture(autouse=True)
def clean_contract_state(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
    yield
    with app_module.app.app_context():
        _cleanup(app_module)


def test_formal_workflow_version_and_job_type_have_distinct_canonical_identities():
    assert FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION == CANONICAL_WORKFLOW_VERSION
    assert FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE == CANONICAL_JOB_TYPE
    assert FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION != FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE

    for relative_path in (
        "docs/adr/ADR-formal-document-alignment-workflow.md",
        "docs/formal_document_alignment_workflow_boundary.md",
        "docs/formal_document_alignment_worker_handler.md",
        "docs/openapi.yaml",
    ):
        assert STALE_WORKFLOW_VERSION not in (ROOT / relative_path).read_text(encoding="utf-8")


def test_authenticated_http_admission_freezes_all_production_defaults(
    client,
    app_module,
    teacher_token,
):
    with app_module.app.app_context():
        source = _setup_source(app_module)
        source_uid = source.source_uid
        teacher = app_module.User.query.filter_by(
            email="teacher.test@lexibridge.local"
        ).one()
        requested_by = str(teacher.id)

    response = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source_uid},
        headers={
            **bearer(teacher_token),
            "Idempotency-Key": "production-contract-convergence-9c5g-v3",
            "X-Request-ID": "production-contract-convergence-request-9c5g-v3",
        },
    )

    assert response.status_code == 202, response.get_data(as_text=True)
    run_uid = response.get_json()["data"]["run_uid"]
    with app_module.app.app_context():
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        job = app_module.BackgroundJob.query.filter(
            app_module.BackgroundJob.input_json.like(f"%{run_uid}%")
        ).one()
        payload = json.loads(job.input_json)

        assert run.workflow_version == CANONICAL_WORKFLOW_VERSION
        assert run.provider_preference == FORMAL_DEFAULT_PROVIDER_NAME == "mock-rule-v1"
        assert run.model_preference == FORMAL_DEFAULT_MODEL_IDENTITY == "mock-rule-v1:v1"
        assert run.prompt_version == "alignment-v1"
        assert run.requested_by == requested_by
        assert run.source_uid == source_uid
        assert (run.status, run.stage) == ("queued", "queued")

        assert job.job_type == CANONICAL_JOB_TYPE
        assert job.max_attempts == FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1 == 3
        assert job.attempt_count == 0
        assert job.execution_attempt == 0
        assert job.status == "queued"
        assert payload == {
            "workflow_run_uid": run_uid,
            "workflow_version": CANONICAL_WORKFLOW_VERSION,
        }
