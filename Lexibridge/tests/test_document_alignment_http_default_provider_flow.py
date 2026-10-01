import pytest

from document_alignment_workflow_route_support import bearer
from services.document_alignment_workflow_contract import (
    ITEM_STATUS_NEEDS_REVIEW,
    ROOT_STATUS_READY_FOR_REVIEW,
)
from services.formal_document_alignment_provider_selection import (
    FORMAL_DEFAULT_MODEL_IDENTITY,
    FORMAL_DEFAULT_PROVIDER_NAME,
)
from test_document_alignment_worker_integration import _cleanup, _setup_source


@pytest.fixture(autouse=True)
def clean_default_provider_flow(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
    yield
    with app_module.app.app_context():
        _cleanup(app_module)


def test_http_admission_default_selection_reaches_ready_for_review_without_run_mutation(
    client,
    app_module,
    teacher_token,
):
    with app_module.app.app_context():
        source = _setup_source(app_module)
        source_uid = source.source_uid
        legacy_before = {
            "runs": app_module.AlignmentRun.query.count(),
            "cards": app_module.TerminologyCard.query.count(),
            "usage": app_module.UsageRecord.query.count(),
            "calls": app_module.AICallLog.query.count(),
        }

    response = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source_uid},
        headers={
            **bearer(teacher_token),
            "Idempotency-Key": "formal-default-provider-9c5f1",
            "X-Request-ID": "formal-default-provider-request-9c5f1",
        },
    )

    assert response.status_code == 202, response.get_data(as_text=True)
    run_uid = response.get_json()["data"]["run_uid"]
    with app_module.app.app_context():
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        assert run.provider_preference == FORMAL_DEFAULT_PROVIDER_NAME
        assert run.model_preference == FORMAL_DEFAULT_MODEL_IDENTITY
        assert run.prompt_version == "alignment-v1"

        worker_result = app_module.run_formal_worker_once(
            worker_id="formal-default-provider-worker-9c5f1"
        )
        app_module.db.session.expire_all()
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        job = app_module.BackgroundJob.query.filter(
            app_module.BackgroundJob.input_json.like(f"%{run_uid}%")
        ).one()
        items = app_module.DocumentAlignmentWorkflowItem.query.filter_by(
            workflow_run_id=run.id
        ).all()
        mappings = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            workflow_run_uid=run_uid
        ).all()
        execution_keys = [mapping.execution_key for mapping in mappings]

        assert worker_result.outcome == "completed", {
            "worker": worker_result,
            "run": (run.status, run.error_code, run.error_message),
            "job": (job.status, job.error_code, job.error_message),
            "items": [
                (item.candidate_term, item.status, item.stage, item.error_code)
                for item in items
            ],
            "mappings": [
                (
                    mapping.execution_status,
                    mapping.safe_error_code,
                    mapping.draft_card_uid,
                    mapping.verification_run_uid,
                )
                for mapping in mappings
            ],
        }
        assert run.status == ROOT_STATUS_READY_FOR_REVIEW, [
            (item.candidate_term, item.status, item.error_code) for item in items
        ]
        assert job.status == "completed"
        assert len(items) == 2
        assert all(item.status == ITEM_STATUS_NEEDS_REVIEW for item in items)
        assert app_module.AlignmentProviderPreflightRun.query.filter(
            app_module.AlignmentProviderPreflightRun.execution_key.in_(execution_keys)
        ).count() == 0
        assert {
            "runs": app_module.AlignmentRun.query.count(),
            "cards": app_module.TerminologyCard.query.count(),
            "usage": app_module.UsageRecord.query.count(),
            "calls": app_module.AICallLog.query.count(),
        } == legacy_before
