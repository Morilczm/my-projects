import itertools

import pytest

from services.document_alignment_workflow_application import (
    DocumentAlignmentSourceAdmissionDecision,
    DocumentAlignmentWorkflowApplicationDependencies,
    DocumentAlignmentWorkflowAuthorizationDecision,
    GovernedKnowledgeSourceSnapshot,
    StartDocumentAlignmentWorkflowCommand,
    start_document_alignment_workflow,
)
from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
from services.formal_document_alignment_provider_selection import (
    FormalDocumentAlignmentProviderSelection,
    resolve_default_formal_document_alignment_provider_selection,
)


PREFIX = "admission-provider-selection-9c5f1"


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        yield
        _cleanup(app_module)


def _cleanup(app_module):
    app_module.db.session.rollback()
    app_module.AuditRecord.query.filter(
        app_module.AuditRecord.target_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowItem.query.filter(
        app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(
            app_module.db.session.query(app_module.DocumentAlignmentWorkflowRun.id).filter(
                app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
            )
        )
    ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete(
        synchronize_session=False
    )
    app_module.db.session.commit()


def _snapshot(source_uid):
    return GovernedKnowledgeSourceSnapshot(
        source_uid=source_uid,
        parse_uid=f"{source_uid}-parse",
        source_version="1",
        course="Provider Selection Course",
        chapter="Frequency",
        owner_user_id="1",
        visibility="course",
        source_status="active",
        source_trust_level="teacher_verified",
        parse_status="success",
        parse_quality="native_text_ok",
        usable_chunk_count=2,
    )


def _command(source_uid, key="provider-selection-key"):
    return StartDocumentAlignmentWorkflowCommand(
        source_uid=source_uid,
        requested_by="1",
        request_id=f"{PREFIX}-request",
        idempotency_key=key,
    )


def _dependencies(app_module, snapshots, *, selection_resolver=None):
    uids = itertools.count(1)
    return DocumentAlignmentWorkflowApplicationDependencies(
        session=app_module.db.session,
        workflow_run_model=app_module.DocumentAlignmentWorkflowRun,
        background_job_model=app_module.BackgroundJob,
        audit_record_model=app_module.AuditRecord,
        source_loader=lambda source_uid: snapshots.get(source_uid),
        authorization_checker=lambda actor, source: DocumentAlignmentWorkflowAuthorizationDecision(True),
        source_admission_checker=lambda source: DocumentAlignmentSourceAdmissionDecision(True),
        current_time_factory=lambda: "2026-07-19 16:00:00",
        uid_factory=lambda: f"{PREFIX}-run-{next(uids)}",
        provider_selection_resolver=(
            selection_resolver or resolve_default_formal_document_alignment_provider_selection
        ),
    )


def test_new_run_freezes_server_owned_provider_model_and_prompt(app_module):
    source = _snapshot(f"{PREFIX}-source-a")
    result = start_document_alignment_workflow(
        _command(source.source_uid),
        _dependencies(app_module, {source.source_uid: source}),
    )

    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=result.run_uid).one()
    assert result.outcome == "created"
    assert run.provider_preference == "mock-rule-v1"
    assert run.model_preference == "mock-rule-v1:v1"
    assert run.prompt_version == "alignment-v1"


def test_replay_preserves_frozen_selection_without_resolving_new_default(app_module):
    source = _snapshot(f"{PREFIX}-source-replay")
    dependencies = _dependencies(app_module, {source.source_uid: source})
    first = start_document_alignment_workflow(_command(source.source_uid), dependencies)

    def must_not_resolve():
        raise AssertionError("idempotent replay must retain persisted selection")

    replay = start_document_alignment_workflow(
        _command(source.source_uid),
        _dependencies(
            app_module,
            {source.source_uid: source},
            selection_resolver=must_not_resolve,
        ),
    )

    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=first.run_uid).one()
    assert replay.outcome == "reused"
    assert replay.run_uid == first.run_uid
    assert (run.provider_preference, run.model_preference, run.prompt_version) == (
        "mock-rule-v1",
        "mock-rule-v1:v1",
        "alignment-v1",
    )
    assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 1
    assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 1


def test_same_key_on_different_sources_creates_independent_frozen_runs(app_module):
    first_source = _snapshot(f"{PREFIX}-source-one")
    second_source = _snapshot(f"{PREFIX}-source-two")
    snapshots = {first_source.source_uid: first_source, second_source.source_uid: second_source}
    dependencies = _dependencies(app_module, snapshots)

    first = start_document_alignment_workflow(_command(first_source.source_uid), dependencies)
    second = start_document_alignment_workflow(_command(second_source.source_uid), dependencies)

    assert first.outcome == second.outcome == "created"
    assert first.run_uid != second.run_uid
    assert app_module.DocumentAlignmentWorkflowRun.query.count() >= 2
    assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 2


def test_selection_failure_fails_closed_without_admission_writes(app_module):
    source = _snapshot(f"{PREFIX}-source-failure")

    def fail_selection():
        raise RuntimeError("LEXIBRIDGE_SENTINEL_SECRET_9C5F1 unavailable")

    result = start_document_alignment_workflow(
        _command(source.source_uid),
        _dependencies(
            app_module,
            {source.source_uid: source},
            selection_resolver=fail_selection,
        ),
    )

    assert result.outcome == "provider_selection_unavailable"
    assert result.error_code == "DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_UNAVAILABLE"
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5F1" not in result.error_message
    assert app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
    ).count() == 0
    assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 0
    assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 0
