import json

import pytest

from services import document_alignment_item_preparation as preparation
from services import document_alignment_processing_orchestrator as orchestrator
from services.document_alignment_workflow_contract import ITEM_STAGE_EVIDENCE_RETRIEVAL
from test_document_alignment_processing_orchestrator_integration import (
    _cleanup,
    _formal_counts_for_run,
    _orchestrator_dependencies,
    _preparation_dependencies,
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


def test_terminal_reinvocation_is_read_only_and_does_not_repeat_provider_records(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "terminal-repeat", bootstrap=False)
    command = _command(run_uid, lease)
    dependencies = _orchestrator_dependencies(
        app_module,
        app_module.db.session,
        lease,
        "terminal-repeat",
    )
    first = orchestrator.process_document_alignment_workflow(command, dependencies)
    counts = {
        "cards": app_module.ConceptAlignmentCard.query.count(),
        "preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "verification": app_module.AlignmentVerificationRun.query.count(),
        "usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "audit": app_module.AuditRecord.query.count(),
    }

    second = orchestrator.process_document_alignment_workflow(command, dependencies)

    assert first.outcome == "ready_for_review"
    assert second.outcome == "already_terminal"
    assert {
        "cards": app_module.ConceptAlignmentCard.query.count(),
        "preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "verification": app_module.AlignmentVerificationRun.query.count(),
        "usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "audit": app_module.AuditRecord.query.count(),
    } == counts
    assert app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one().status == "running"
    _cleanup(app_module)


def test_evidence_ready_resume_rehydrates_memory_input_and_completes_once(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "evidence-resume", bootstrap=True)
    item = app_module.DocumentAlignmentWorkflowItem.query.one()
    prepared = preparation.prepare_document_alignment_item(
        preparation.PrepareDocumentAlignmentItemCommand(
            workflow_run_uid=run_uid,
            workflow_item_uid=item.item_uid,
        ),
        _preparation_dependencies(app_module, app_module.db.session),
    )
    assert prepared.outcome == preparation.PREPARATION_OUTCOME_PREPARED
    item = app_module.DocumentAlignmentWorkflowItem.query.filter_by(item_uid=item.item_uid).one()
    item.english_evidence_refs = json.dumps(list(prepared.english_evidence_refs))
    item.chinese_evidence_refs = json.dumps(list(prepared.chinese_evidence_refs))
    item.chinese_candidate_summary = json.dumps(
        {
            "values": list(prepared.chinese_candidate_values),
            "provenance_refs": list(prepared.chinese_candidate_provenance_refs),
            "candidate_count": prepared.candidate_count,
        },
        ensure_ascii=False,
    )
    item.risk_labels = json.dumps(list(prepared.risk_labels))
    item.status = "evidence_ready"
    item.stage = ITEM_STAGE_EVIDENCE_RETRIEVAL
    app_module.db.session.commit()

    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "evidence-resume"),
    )

    assert result.outcome == "ready_for_review"
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "needs_review"
    counts = _formal_counts_for_run(app_module, run_uid)
    assert counts["verifications"] == 1
    assert counts["usage"] == 1
    _cleanup(app_module)
