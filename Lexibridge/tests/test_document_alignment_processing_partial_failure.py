import json

import pytest

from services import document_alignment_processing_orchestrator as orchestrator
from services.document_alignment_workflow_contract import ITEM_STAGE_TERMINAL
from test_document_alignment_processing_orchestrator_integration import (
    _cleanup,
    _formal_counts_for_run,
    _orchestrator_dependencies,
    _setup_governed_workflow,
)


@pytest.fixture(autouse=True)
def _app_context(app_module):
    with app_module.app.app_context():
        yield


def _command(run_uid, lease):
    return orchestrator.ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )


def test_business_blocked_item_does_not_stop_later_root_aggregation(app_module):
    run_uid, lease = _setup_governed_workflow(
        app_module,
        "partial",
        bootstrap=False,
        terms=("Fourier Transform", "Unmapped Course Term"),
        bilingual_terms={"Fourier Transform": "傅里叶变换"},
    )

    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "partial"),
    )

    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    items = app_module.DocumentAlignmentWorkflowItem.query.order_by(
        app_module.DocumentAlignmentWorkflowItem.id
    ).all()
    assert result.outcome == "completed_with_warnings", result
    assert [item.status for item in items] == ["needs_review", "blocked"]
    assert items[1].error_code == "DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE"
    assert run.ready_for_review_items == 1
    assert run.blocked_items == 1
    assert run.failed_items == 0
    assert run.warning_count >= 1
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 1
    _cleanup(app_module)


def test_all_business_blocked_items_finalize_root_blocked_without_provider_usage(app_module):
    run_uid, lease = _setup_governed_workflow(
        app_module,
        "all-blocked",
        bootstrap=False,
        terms=("Unmapped Term A", "Unmapped Term B"),
        bilingual_terms={},
    )

    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "all-blocked"),
    )

    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert result.outcome == "blocked"
    assert run.blocked_items == 2
    assert run.ready_for_review_items == 0
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 0
    _cleanup(app_module)


def test_existing_failed_items_are_not_retried_and_finalize_root_failed(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "failed", bootstrap=True)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    item = app_module.DocumentAlignmentWorkflowItem.query.one()
    item.status = "failed"
    item.stage = ITEM_STAGE_TERMINAL
    item.error_code = "DOCUMENT_ALIGNMENT_VERIFICATION_FAILED"
    item.error_message = "Formal deterministic verification failed."
    item.finished_at = "2026-07-18 16:02:00"
    app_module.db.session.commit()

    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "failed"),
    )

    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert result.outcome == "failed"
    assert result.reused_items == 1
    assert run.failed_items == 1
    assert _formal_counts_for_run(app_module, run_uid)["verifications"] == 0
    _cleanup(app_module)


def test_source_drift_preserves_completed_item_and_blocks_unstarted_candidate(app_module):
    run_uid, lease = _setup_governed_workflow(
        app_module,
        "drift",
        bootstrap=True,
        terms=("Fourier Transform", "Unmapped Drift Term A", "Unmapped Drift Term B"),
        bilingual_terms={"Fourier Transform": "傅里叶变换"},
    )
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    items = app_module.DocumentAlignmentWorkflowItem.query.order_by(
        app_module.DocumentAlignmentWorkflowItem.id
    ).all()
    items[0].status = "needs_review"
    items[0].stage = ITEM_STAGE_TERMINAL
    items[0].risk_labels = json.dumps(["teacher_review_required"])
    source = app_module.KnowledgeSource.query.filter_by(source_uid=run.source_uid).one()
    source.version = 2
    app_module.db.session.commit()

    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "drift"),
    )

    app_module.db.session.expire_all()
    items = app_module.DocumentAlignmentWorkflowItem.query.order_by(
        app_module.DocumentAlignmentWorkflowItem.id
    ).all()
    assert result.outcome == "completed_with_warnings", result
    assert items[0].status == "needs_review"
    assert [item.status for item in items[1:]] == ["blocked", "blocked"]
    assert {item.error_code for item in items[1:]} == {"DOCUMENT_ALIGNMENT_SOURCE_CHANGED"}
    _cleanup(app_module)
