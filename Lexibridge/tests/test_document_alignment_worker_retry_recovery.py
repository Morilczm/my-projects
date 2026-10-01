import json
from datetime import datetime, timedelta

import pytest

from services.document_alignment_processing_orchestrator import (
    DocumentAlignmentProcessingDependencies,
    DocumentAlignmentProcessingModels,
    ItemPreparationCollaborator,
    ItemVerificationCollaborator,
    LeaseCollaborator,
    ProcessDocumentAlignmentWorkflowCommand,
    ProcessDocumentAlignmentWorkflowResult,
    WorkflowBootstrapCollaborator,
    finalize_document_alignment_workflow_failure,
    OUTCOME_ALREADY_TERMINAL,
    OUTCOME_RETRYABLE_INTERRUPTION,
)
from services.document_alignment_worker_handler import (
    DocumentAlignmentWorkerHandlerDependencies,
    FormalDocumentAlignmentJobSnapshot,
    FormalDocumentAlignmentRunSnapshot,
    FormalJobOwnershipCollaborator,
    FormalProcessingCollaborator,
    run_claimed_formal_document_alignment_job,
)
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ITEM_STAGE_TERMINAL,
    ITEM_STATUS_FAILED,
    ITEM_STATUS_NEEDS_REVIEW,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_FAILED,
    ROOT_STATUS_PROCESSING,
    WORKFLOW_VERSION_V1,
)
from services.formal_background_job_execution import (
    complete_formal_background_job,
    fail_formal_background_job,
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
    fence_active_formal_job_lease_in_transaction,
    heartbeat_formal_background_job,
    requeue_formal_background_job,
    validate_active_formal_job_lease,
)


PREFIX = "worker-retry-recovery-9c5d"
NOW = datetime(2026, 7, 19, 9, 0, 0)


@pytest.fixture(autouse=True)
def _app_context(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        try:
            yield
        finally:
            _cleanup(app_module)


def _cleanup(app_module):
    app_module.db.session.rollback()
    app_module.AuditRecord.query.filter(app_module.AuditRecord.target_uid.like(f"{PREFIX}%")).delete(
        synchronize_session=False
    )
    app_module.DocumentAlignmentWorkflowItem.query.filter(
        app_module.DocumentAlignmentWorkflowItem.item_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete(
        synchronize_session=False
    )
    app_module.db.session.commit()


def _setup(app_module, *, attempt_count=1, max_attempts=2):
    _cleanup(app_module)
    run = app_module.DocumentAlignmentWorkflowRun(
        id=951005,
        run_uid=f"{PREFIX}-run",
        source_uid=f"{PREFIX}-source",
        parse_uid=f"{PREFIX}-parse",
        source_version="1",
        course=f"{PREFIX}-course",
        chapter="chapter",
        requested_by="1",
        request_id=f"{PREFIX}-request",
        idempotency_key=f"{PREFIX}-key",
        idempotency_fingerprint=f"{PREFIX}-fingerprint",
        workflow_version=WORKFLOW_VERSION_V1,
        status=ROOT_STATUS_PROCESSING,
        stage="verification",
        created_at="2026-07-19 08:59:00",
    )
    job = app_module.BackgroundJob(
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        status="queued",
        input_json=json.dumps({"workflow_run_uid": run.run_uid, "workflow_version": WORKFLOW_VERSION_V1}),
        result_json="{}",
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        created_at="2026-07-19 08:59:00",
        updated_at="2026-07-19 08:59:00",
    )
    app_module.db.session.add_all([run, job])
    app_module.db.session.flush()
    app_module.db.session.add_all(
        [
            app_module.DocumentAlignmentWorkflowItem(
                item_uid=f"{PREFIX}-item-ready",
                workflow_run_id=run.id,
                item_key=f"{PREFIX}-ready",
                candidate_term="Ready term",
                normalized_term="ready term",
                source_chunk_refs="[]",
                status=ITEM_STATUS_NEEDS_REVIEW,
                stage=ITEM_STAGE_TERMINAL,
            ),
            app_module.DocumentAlignmentWorkflowItem(
                item_uid=f"{PREFIX}-item-failed",
                workflow_run_id=run.id,
                item_key=f"{PREFIX}-failed",
                candidate_term="Failed term",
                normalized_term="failed term",
                source_chunk_refs="[]",
                status=ITEM_STATUS_FAILED,
                stage=ITEM_STAGE_TERMINAL,
                error_code="DOCUMENT_ALIGNMENT_VERIFICATION_FAILED",
                error_message="safe failure",
            ),
        ]
    )
    app_module.db.session.commit()
    lease_dependencies = FormalBackgroundJobExecutionDependencies(
        session=app_module.db.session,
        job_model=app_module.BackgroundJob,
        current_time_factory=lambda: NOW,
        lease_token_factory=lambda: f"{PREFIX}-lease",
    )
    lease = claim_next_formal_background_job(f"{PREFIX}-worker", lease_dependencies).lease
    return run.run_uid, lease, lease_dependencies


def _handler_dependencies(app_module, lease, lease_dependencies, processing):
    def load_job(job_uid):
        job = app_module.BackgroundJob.query.filter_by(job_uid=job_uid).one_or_none()
        if job is None:
            return None
        return FormalDocumentAlignmentJobSnapshot(
            job_uid=job.job_uid,
            job_type=job.job_type,
            status=job.status,
            input_payload=job.input_json,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
        )

    def load_run(run_uid):
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one_or_none()
        if run is None:
            return None
        return FormalDocumentAlignmentRunSnapshot(
            run_uid=run.run_uid,
            workflow_version=run.workflow_version,
            status=run.status,
            stage=run.stage,
            error_code=run.error_code,
        )

    finalizer_dependencies = _dependencies(app_module, lease, lease_dependencies)
    return DocumentAlignmentWorkerHandlerDependencies(
        load_job=load_job,
        load_run=load_run,
        ownership=FormalJobOwnershipCollaborator(
            validate=lambda active: validate_active_formal_job_lease(active, lease_dependencies),
            heartbeat=lambda active: heartbeat_formal_background_job(active, lease_dependencies),
            complete=lambda active: complete_formal_background_job(active, lease_dependencies),
            requeue=lambda active, code, message: requeue_formal_background_job(
                active, lease_dependencies, code, message
            ),
            fail=lambda active, code, message: fail_formal_background_job(
                active, lease_dependencies, code, message
            ),
        ),
        processing=FormalProcessingCollaborator(
            execute=processing,
            finalize_failure=lambda command, code, message: finalize_document_alignment_workflow_failure(
                command, finalizer_dependencies, code, message
            ),
        ),
    )


def _dependencies(app_module, lease, lease_dependencies):
    unavailable = lambda *args, **kwargs: pytest.fail("failure finalization must not execute processing collaborators")
    return DocumentAlignmentProcessingDependencies(
        session=app_module.db.session,
        models=DocumentAlignmentProcessingModels(
            workflow_run=app_module.DocumentAlignmentWorkflowRun,
            workflow_item=app_module.DocumentAlignmentWorkflowItem,
            background_job=app_module.BackgroundJob,
            audit_record=app_module.AuditRecord,
        ),
        bootstrap=WorkflowBootstrapCollaborator(execute=unavailable),
        preparation=ItemPreparationCollaborator(prepare=unavailable, validate_scope=unavailable),
        verification=ItemVerificationCollaborator(execute=unavailable),
        lease=LeaseCollaborator(
            heartbeat=unavailable,
            fence=lambda command: fence_active_formal_job_lease_in_transaction(lease, lease_dependencies),
        ),
        current_time_factory=lambda: NOW + timedelta(seconds=1),
        audit_uid_factory=lambda: f"{PREFIX}-audit",
    )


def test_retry_exhaustion_finalizes_root_once_and_preserves_job_ownership(app_module):
    run_uid, lease, lease_dependencies = _setup(app_module)
    command = ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )
    dependencies = _dependencies(app_module, lease, lease_dependencies)

    first = finalize_document_alignment_workflow_failure(
        command,
        dependencies,
        "DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
        "Formal document alignment worker retry budget was exhausted.",
    )
    second = finalize_document_alignment_workflow_failure(
        command,
        dependencies,
        "DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED",
        "Formal document alignment worker retry budget was exhausted.",
    )

    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    audits = app_module.AuditRecord.query.filter_by(
        target_uid=run_uid,
        event_type="document_alignment_failed",
    ).all()

    assert first.outcome == ROOT_STATUS_FAILED
    assert second.outcome == "already_terminal"
    assert run.status == ROOT_STATUS_FAILED
    assert run.stage == ROOT_STAGE_TERMINAL
    assert run.total_items == 2
    assert run.ready_for_review_items == 1
    assert run.failed_items == 1
    assert run.warning_count == 1
    assert run.error_code == "DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED"
    assert len(audits) == 1
    assert job.status == "running"
    assert job.attempt_count == 1
    _cleanup(app_module)


def test_new_attempt_completes_job_after_root_terminal_before_job_complete_crash(app_module):
    run_uid, old_lease, _ = _setup(app_module, attempt_count=0, max_attempts=3)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    run.status = "ready_for_review"
    run.stage = ROOT_STAGE_TERMINAL
    run.error_code = ""
    run.error_message = ""
    app_module.db.session.commit()
    reclaim_time = old_lease.lease_expires_at
    new_dependencies = FormalBackgroundJobExecutionDependencies(
        session=app_module.db.session,
        job_model=app_module.BackgroundJob,
        current_time_factory=lambda: reclaim_time,
        lease_token_factory=lambda: f"{PREFIX}-replacement-lease",
    )
    new_lease = claim_next_formal_background_job(f"{PREFIX}-replacement", new_dependencies).lease
    assert complete_formal_background_job(old_lease, new_dependencies).outcome == "stale_attempt"

    result = run_claimed_formal_document_alignment_job(
        new_lease,
        _handler_dependencies(
            app_module,
            new_lease,
            new_dependencies,
            lambda command: ProcessDocumentAlignmentWorkflowResult(
                outcome=OUTCOME_ALREADY_TERMINAL,
                workflow_run_uid=run_uid,
                job_uid=new_lease.job_uid,
                run_status="ready_for_review",
                run_stage=ROOT_STAGE_TERMINAL,
            ),
        ),
    )

    app_module.db.session.expire_all()
    job = app_module.BackgroundJob.query.filter_by(job_uid=new_lease.job_uid).one()
    assert result.outcome == "completed"
    assert job.status == "completed"
    assert job.execution_attempt == 2
    assert job.attempt_count == 0
    _cleanup(app_module)


def test_retryable_processing_requeues_once_and_next_claim_preserves_business_count(app_module):
    run_uid, lease, lease_dependencies = _setup(app_module, attempt_count=0, max_attempts=3)
    result = run_claimed_formal_document_alignment_job(
        lease,
        _handler_dependencies(
            app_module,
            lease,
            lease_dependencies,
            lambda command: ProcessDocumentAlignmentWorkflowResult(
                outcome=OUTCOME_RETRYABLE_INTERRUPTION,
                workflow_run_uid=run_uid,
                job_uid=lease.job_uid,
                run_status=ROOT_STATUS_PROCESSING,
                run_stage="verification",
                retryable=True,
                error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
                error_message="Safe interruption.",
            ),
        ),
    )
    app_module.db.session.expire_all()
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    assert result.outcome == "requeued"
    assert job.status == "retrying"
    assert job.attempt_count == 1
    assert job.execution_attempt == 1

    next_dependencies = FormalBackgroundJobExecutionDependencies(
        session=app_module.db.session,
        job_model=app_module.BackgroundJob,
        current_time_factory=lambda: NOW + timedelta(seconds=2),
        lease_token_factory=lambda: f"{PREFIX}-retry-lease",
    )
    next_lease = claim_next_formal_background_job(f"{PREFIX}-retry-worker", next_dependencies).lease
    app_module.db.session.expire_all()
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    assert next_lease.execution_attempt == 2
    assert job.attempt_count == 1
    _cleanup(app_module)


def test_max_attempts_finalizes_root_before_job_failure(app_module):
    run_uid, lease, lease_dependencies = _setup(app_module, attempt_count=1, max_attempts=2)
    result = run_claimed_formal_document_alignment_job(
        lease,
        _handler_dependencies(
            app_module,
            lease,
            lease_dependencies,
            lambda command: ProcessDocumentAlignmentWorkflowResult(
                outcome=OUTCOME_RETRYABLE_INTERRUPTION,
                workflow_run_uid=run_uid,
                job_uid=lease.job_uid,
                run_status=ROOT_STATUS_PROCESSING,
                run_stage="verification",
                retryable=True,
                error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
                error_message="Safe interruption.",
            ),
        ),
    )
    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    assert result.outcome == "retry_exhausted"
    assert run.status == ROOT_STATUS_FAILED
    assert run.stage == ROOT_STAGE_TERMINAL
    assert job.status == "failed"
    assert job.attempt_count == 2
    _cleanup(app_module)
