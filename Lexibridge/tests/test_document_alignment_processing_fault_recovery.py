import dataclasses
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from services import document_alignment_item_preparation as preparation
from services import document_alignment_processing_orchestrator as orchestrator
from services.formal_background_job_execution import LEASE_OUTCOME_LEASE_EXPIRED
from test_document_alignment_processing_orchestrator_integration import (
    PREFIX,
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


def _failing_preparation(app_module, dependencies, failure_kind):
    prepared_dependencies = _preparation_dependencies(app_module, app_module.db.session)

    def controlled_failure(*args, **kwargs):
        raise RuntimeError(f"controlled {failure_kind} failure")

    if failure_kind == "candidate":
        prepared_dependencies = dataclasses.replace(
            prepared_dependencies,
            candidate_generator=controlled_failure,
        )
    else:
        prepared_dependencies = dataclasses.replace(
            prepared_dependencies,
            evidence_retriever=controlled_failure,
        )

    def prepare_item(command, item_uid):
        return preparation.prepare_document_alignment_item(
            preparation.PrepareDocumentAlignmentItemCommand(
                workflow_run_uid=command.workflow_run_uid,
                workflow_item_uid=item_uid,
            ),
            prepared_dependencies,
        )

    return dataclasses.replace(
        dependencies,
        preparation=dataclasses.replace(dependencies.preparation, prepare=prepare_item),
    )


def test_bootstrap_failure_stops_without_items_and_same_session_can_resume(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "fault-bootstrap", bootstrap=False)
    command = _command(run_uid, lease)
    normal = _orchestrator_dependencies(app_module, app_module.db.session, lease, "fault-bootstrap")

    def fail_bootstrap(_):
        raise RuntimeError("controlled bootstrap failure")

    first = orchestrator.process_document_alignment_workflow(
        command,
        dataclasses.replace(
            normal,
            bootstrap=dataclasses.replace(normal.bootstrap, execute=fail_bootstrap),
        ),
    )
    assert first.outcome == "retryable_interruption"
    assert first.retryable is True
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).count() == 0

    second = orchestrator.process_document_alignment_workflow(command, normal)
    assert second.outcome == "ready_for_review"
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "needs_review"
    _cleanup(app_module)


@pytest.mark.parametrize("failure_kind", ["candidate", "evidence"])
def test_preparation_collaborator_failure_stops_and_resume_reuses_bootstrap(
    app_module,
    failure_kind,
):
    suffix = f"fault-{failure_kind}"
    run_uid, lease = _setup_governed_workflow(app_module, suffix, bootstrap=False)
    command = _command(run_uid, lease)
    normal = _orchestrator_dependencies(app_module, app_module.db.session, lease, suffix)

    first = orchestrator.process_document_alignment_workflow(
        command,
        _failing_preparation(app_module, normal, failure_kind),
    )
    assert first.outcome == "retryable_interruption"
    assert first.retryable is True
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "candidate"
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 0

    second = orchestrator.process_document_alignment_workflow(command, normal)
    assert second.outcome == "ready_for_review"
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).count() == 1
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 1
    _cleanup(app_module)


def test_evidence_checkpoint_commit_failure_rolls_back_and_resumes(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "fault-checkpoint", bootstrap=False)
    command = _command(run_uid, lease)
    dependencies = _orchestrator_dependencies(
        app_module,
        app_module.db.session,
        lease,
        "fault-checkpoint",
    )
    calls = {"failed": False}

    def fail_checkpoint(mapper, connection, target):
        if target.status == "evidence_ready" and not calls["failed"]:
            calls["failed"] = True
            raise RuntimeError("controlled evidence checkpoint failure")

    event.listen(app_module.DocumentAlignmentWorkflowItem, "before_update", fail_checkpoint)
    try:
        first = orchestrator.process_document_alignment_workflow(command, dependencies)
    finally:
        event.remove(app_module.DocumentAlignmentWorkflowItem, "before_update", fail_checkpoint)

    app_module.db.session.expire_all()
    assert first.outcome == "retryable_interruption"
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "candidate"
    assert _formal_counts_for_run(app_module, run_uid)["mappings"] == 0

    second = orchestrator.process_document_alignment_workflow(command, dependencies)
    assert second.outcome == "ready_for_review"
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "needs_review"
    _cleanup(app_module)


def test_adapter_retryable_result_stops_before_later_items_and_resumes(app_module):
    run_uid, lease = _setup_governed_workflow(
        app_module,
        "fault-adapter",
        bootstrap=False,
        terms=("Fourier Transform", "Laplace Transform"),
        bilingual_terms={
            "Fourier Transform": "傅里叶变换",
            "Laplace Transform": "拉普拉斯变换",
        },
    )
    command = _command(run_uid, lease)
    normal = _orchestrator_dependencies(app_module, app_module.db.session, lease, "fault-adapter")
    calls = {"adapter": 0}

    def retryable_adapter(command, item_uid, prepared):
        calls["adapter"] += 1
        return SimpleNamespace(
            outcome="persistence_error",
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
            error_message="Formal item persistence must be retried.",
        )

    first = orchestrator.process_document_alignment_workflow(
        command,
        dataclasses.replace(
            normal,
            verification=dataclasses.replace(normal.verification, execute=retryable_adapter),
        ),
    )
    items = app_module.DocumentAlignmentWorkflowItem.query.order_by(
        app_module.DocumentAlignmentWorkflowItem.id
    ).all()
    assert first.outcome == "retryable_interruption"
    assert calls["adapter"] == 1
    assert [item.status for item in items] == ["evidence_ready", "candidate"]

    second = orchestrator.process_document_alignment_workflow(command, normal)
    assert second.outcome == "ready_for_review"
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 2
    _cleanup(app_module)


def test_lease_expiry_between_items_stops_and_does_not_terminalize_root(app_module):
    run_uid, lease = _setup_governed_workflow(
        app_module,
        "fault-lease",
        bootstrap=False,
        terms=("Fourier Transform", "Laplace Transform"),
        bilingual_terms={
            "Fourier Transform": "傅里叶变换",
            "Laplace Transform": "拉普拉斯变换",
        },
    )
    command = _command(run_uid, lease)
    normal = _orchestrator_dependencies(app_module, app_module.db.session, lease, "fault-lease")
    calls = {"heartbeat": 0}
    real_heartbeat = normal.lease.heartbeat

    def expire_before_second_item(command):
        calls["heartbeat"] += 1
        if calls["heartbeat"] == 7:
            return SimpleNamespace(
                outcome=LEASE_OUTCOME_LEASE_EXPIRED,
                error_code="DOCUMENT_ALIGNMENT_LEASE_EXPIRED",
                error_message="Formal job lease expired.",
            )
        return real_heartbeat(command)

    first = orchestrator.process_document_alignment_workflow(
        command,
        dataclasses.replace(
            normal,
            lease=dataclasses.replace(normal.lease, heartbeat=expire_before_second_item),
        ),
    )
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    items = app_module.DocumentAlignmentWorkflowItem.query.order_by(
        app_module.DocumentAlignmentWorkflowItem.id
    ).all()
    assert first.outcome == "lease_expired"
    assert run.status == "processing"
    assert [item.status for item in items] == ["needs_review", "candidate"]
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 1

    second = orchestrator.process_document_alignment_workflow(command, normal)
    assert second.outcome == "ready_for_review"
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 2
    _cleanup(app_module)


def test_progress_commit_failure_preserves_item_and_next_invocation_rebuilds_counts(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "fault-progress", bootstrap=False)
    command = _command(run_uid, lease)
    dependencies = _orchestrator_dependencies(
        app_module,
        app_module.db.session,
        lease,
        "fault-progress",
    )
    calls = {"failed": False}

    def fail_progress(mapper, connection, target):
        if (
            target.status == "processing"
            and int(target.ready_for_review_items or 0) == 1
            and not calls["failed"]
        ):
            calls["failed"] = True
            raise RuntimeError("controlled progress persistence failure")

    event.listen(app_module.DocumentAlignmentWorkflowRun, "before_update", fail_progress)
    try:
        first = orchestrator.process_document_alignment_workflow(command, dependencies)
    finally:
        event.remove(app_module.DocumentAlignmentWorkflowRun, "before_update", fail_progress)

    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert first.outcome == "retryable_interruption"
    assert run.status == "processing"
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "needs_review"

    second = orchestrator.process_document_alignment_workflow(command, dependencies)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert second.outcome == "ready_for_review"
    assert run.ready_for_review_items == 1
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 1
    _cleanup(app_module)


def test_existing_root_terminal_audit_identity_is_reused(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "fault-audit-conflict", bootstrap=False)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    identity = orchestrator.build_document_alignment_root_audit_event_identity(
        run_uid,
        run.workflow_version,
        "document_alignment_ready_for_review",
    )
    app_module.db.session.add(
        app_module.AuditRecord(
            audit_uid=f"{PREFIX}-audit-existing-terminal",
            event_identity=identity,
            event_type="document_alignment_ready_for_review",
            target_type="document_alignment_workflow_run",
            target_uid=run_uid,
            source="formal_processing_orchestrator",
            created_at="2026-07-18 16:00:00",
        )
    )
    app_module.db.session.commit()

    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(
            app_module,
            app_module.db.session,
            lease,
            "fault-audit-conflict",
        ),
    )
    assert result.outcome == "ready_for_review"
    assert app_module.AuditRecord.query.filter_by(event_identity=identity).count() == 1
    _cleanup(app_module)


def test_root_finalization_commit_failure_is_retryable_and_session_recovers(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "fault-finalization", bootstrap=False)
    command = _command(run_uid, lease)
    dependencies = _orchestrator_dependencies(
        app_module,
        app_module.db.session,
        lease,
        "fault-finalization",
    )
    calls = {"failed": False}

    def fail_terminal_update(mapper, connection, target):
        if target.status == "ready_for_review" and not calls["failed"]:
            calls["failed"] = True
            raise RuntimeError("controlled root finalization failure")

    event.listen(app_module.DocumentAlignmentWorkflowRun, "before_update", fail_terminal_update)
    try:
        first = orchestrator.process_document_alignment_workflow(command, dependencies)
    finally:
        event.remove(app_module.DocumentAlignmentWorkflowRun, "before_update", fail_terminal_update)

    app_module.db.session.expire_all()
    assert first.outcome == "persistence_error"
    assert first.retryable is True
    assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one().status == "processing"
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "needs_review"

    second = orchestrator.process_document_alignment_workflow(command, dependencies)
    assert second.outcome == "ready_for_review"
    assert _formal_counts_for_run(app_module, run_uid)["usage"] == 1
    _cleanup(app_module)
