import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from services.document_alignment_item_bootstrap import (
    BOOTSTRAP_OUTCOME_CREATED,
    BOOTSTRAP_OUTCOME_INVALID_RUN_STATE,
    BOOTSTRAP_OUTCOME_ITEM_IDEMPOTENCY_CONFLICT,
    BOOTSTRAP_OUTCOME_LEASE_EXPIRED,
    BOOTSTRAP_OUTCOME_LEASE_NOT_OWNED,
    BOOTSTRAP_OUTCOME_NO_CANDIDATES,
    BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR,
    BOOTSTRAP_OUTCOME_REUSED,
    BOOTSTRAP_OUTCOME_SOURCE_CHANGED,
    BOOTSTRAP_OUTCOME_STALE_ATTEMPT,
    BOOTSTRAP_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED,
    BootstrapDocumentAlignmentItemsCommand,
    BootstrapDocumentAlignmentItemsDependencies,
    BootstrapDocumentAlignmentItemsResult,
    bootstrap_document_alignment_workflow_items,
)
from services.document_alignment_term_candidates import GovernedSourceChunkSnapshot
from services.document_alignment_workflow_application import GovernedKnowledgeSourceSnapshot
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ITEM_STAGE_CANDIDATE,
    ITEM_STATUS_CANDIDATE,
    ROOT_STAGE_EVIDENCE_RETRIEVAL,
    ROOT_STAGE_QUEUED,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_BLOCKED,
    ROOT_STATUS_PROCESSING,
    ROOT_STATUS_QUEUED,
    WORKFLOW_VERSION_V1,
    build_document_alignment_item_key,
)
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
)


NOW = datetime(2026, 7, 18, 12, 0, 0)


@pytest.fixture(autouse=True)
def _app_context(app_module):
    with app_module.app.app_context():
        yield


def _source(**overrides):
    values = {
        "source_uid": "source-bootstrap-9c5a",
        "parse_uid": "parse-bootstrap-9c5a",
        "source_version": "3",
        "course": "Signals",
        "chapter": "Frequency",
        "owner_user_id": "1",
        "visibility": "course",
        "source_status": "active",
        "source_trust_level": "trusted",
        "parse_status": "succeeded",
        "parse_quality": "ready",
        "usable_chunk_count": 2,
    }
    values.update(overrides)
    return GovernedKnowledgeSourceSnapshot(**values)


def _chunks(source=None):
    source = source or _source()
    return (
        GovernedSourceChunkSnapshot(
            chunk_uid="chunk-bootstrap-a",
            source_uid=source.source_uid,
            parse_uid=source.parse_uid,
            source_version=source.source_version,
            chunk_index=0,
            text="Fourier Transform",
            language="en",
        ),
        GovernedSourceChunkSnapshot(
            chunk_uid="chunk-bootstrap-b",
            source_uid=source.source_uid,
            parse_uid=source.parse_uid,
            source_version=source.source_version,
            chunk_index=1,
            text="Laplace Transform",
            language="en",
        ),
    )


def _cleanup(app_module):
    app_module.db.session.rollback()
    app_module.DocumentAlignmentWorkflowItem.query.delete()
    app_module.DocumentAlignmentWorkflowRun.query.delete()
    app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete()
    app_module.db.session.commit()
    app_module.db.session.expunge_all()


def _run(app_module, source=None, status=ROOT_STATUS_QUEUED, stage=ROOT_STAGE_QUEUED):
    source = source or _source()
    return app_module.DocumentAlignmentWorkflowRun(
        run_uid="workflow-bootstrap-9c5a",
        source_uid=source.source_uid,
        parse_uid=source.parse_uid,
        source_version=source.source_version,
        course=source.course,
        chapter=source.chapter,
        requested_by="1",
        request_id="request-bootstrap-9c5a",
        idempotency_key="idempotency-bootstrap-9c5a",
        idempotency_fingerprint="fingerprint-bootstrap-9c5a",
        workflow_version=WORKFLOW_VERSION_V1,
        status=status,
        stage=stage,
        created_at="2026-07-18 11:59:00",
        updated_at="2026-07-18 11:59:00",
    )


def _job(app_module):
    return app_module.BackgroundJob(
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        status="queued",
        priority=100,
        created_by=1,
        input_json=json.dumps({"workflow_run_uid": "workflow-bootstrap-9c5a", "workflow_version": WORKFLOW_VERSION_V1}),
        result_json="{}",
        attempt_count=0,
        max_attempts=3,
        created_at="2026-07-18 11:59:00",
        updated_at="2026-07-18 11:59:00",
    )


def _setup(app_module, source=None, status=ROOT_STATUS_QUEUED, stage=ROOT_STAGE_QUEUED):
    _cleanup(app_module)
    run = _run(app_module, source, status=status, stage=stage)
    job = _job(app_module)
    app_module.db.session.add_all([run, job])
    app_module.db.session.commit()
    lease = claim_next_formal_background_job(
        "worker-bootstrap-9c5a",
        FormalBackgroundJobExecutionDependencies(
            session=app_module.db.session,
            job_model=app_module.BackgroundJob,
            current_time_factory=lambda: NOW,
            lease_token_factory=lambda: "lease-bootstrap-9c5a",
        ),
    ).lease
    return run, job, lease


def _command(lease, **overrides):
    values = {
        "workflow_run_uid": "workflow-bootstrap-9c5a",
        "job_uid": lease.job_uid,
        "worker_id": lease.worker_id,
        "execution_attempt": lease.execution_attempt,
        "lease_token": lease.lease_token,
    }
    values.update(overrides)
    return BootstrapDocumentAlignmentItemsCommand(**values)


def _dependencies(app_module, source=None, chunks=None, extractor=None, session=None, **overrides):
    source = source or _source()
    chunk_values = tuple(chunks if chunks is not None else _chunks(source))
    item_uid_sequence = iter((f"item-bootstrap-{index}" for index in range(1, 1000)))
    values = {
        "session": session if session is not None else app_module.db.session,
        "workflow_run_model": app_module.DocumentAlignmentWorkflowRun,
        "workflow_item_model": app_module.DocumentAlignmentWorkflowItem,
        "background_job_model": app_module.BackgroundJob,
        "source_loader": lambda current_session, source_uid: source if source_uid == source.source_uid else None,
        "chunk_loader": lambda current_session, snapshot: chunk_values,
        "term_extractor": extractor or (lambda text: [{"english_term": text}]),
        "item_uid_factory": lambda: next(item_uid_sequence),
        "current_time_factory": lambda: NOW + timedelta(seconds=1),
    }
    values.update(overrides)
    return BootstrapDocumentAlignmentItemsDependencies(**values)


def test_bootstrap_dtos_are_frozen_and_hide_lease_token(app_module):
    _, _, lease = _setup(app_module)
    command = _command(lease)
    dependencies = _dependencies(app_module)
    result = BootstrapDocumentAlignmentItemsResult(outcome="created")
    for value in (command, dependencies, result):
        with pytest.raises(FrozenInstanceError):
            value.outcome = "changed" if hasattr(value, "outcome") else "changed"
    assert lease.lease_token not in repr(command)
    assert lease.lease_token not in repr(result)
    assert result.canonical_candidate_count == 0
    assert result.retryable is False
    _cleanup(app_module)


def test_active_lease_bootstrap_creates_stable_items_and_advances_root(app_module):
    _, _, lease = _setup(app_module)
    result = bootstrap_document_alignment_workflow_items(_command(lease), _dependencies(app_module))
    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid="workflow-bootstrap-9c5a").one()
    items = app_module.DocumentAlignmentWorkflowItem.query.order_by(app_module.DocumentAlignmentWorkflowItem.item_key).all()

    assert result.outcome == BOOTSTRAP_OUTCOME_CREATED
    assert result.created_item_count == 2
    assert result.canonical_candidate_count == 2
    assert result.reused_item_count == 0
    assert run.status == ROOT_STATUS_PROCESSING
    assert run.stage == ROOT_STAGE_EVIDENCE_RETRIEVAL
    assert run.total_items == 2
    assert [(item.status, item.stage) for item in items] == [(ITEM_STATUS_CANDIDATE, ITEM_STAGE_CANDIDATE)] * 2
    assert {tuple(json.loads(item.source_chunk_refs)) for item in items} == {("chunk-bootstrap-a",), ("chunk-bootstrap-b",)}
    assert all(not item.draft_card_uid and not item.verification_run_uid for item in items)
    _cleanup(app_module)


def test_validating_run_can_resume_bootstrap(app_module):
    _, _, lease = _setup(app_module, status="validating", stage="term_extraction")
    result = bootstrap_document_alignment_workflow_items(_command(lease), _dependencies(app_module))
    assert result.outcome == BOOTSTRAP_OUTCOME_CREATED
    assert app_module.DocumentAlignmentWorkflowRun.query.one().status == ROOT_STATUS_PROCESSING
    _cleanup(app_module)


def test_processing_run_without_complete_items_is_not_bootstrapped_as_new(app_module):
    _, _, lease = _setup(app_module, status=ROOT_STATUS_PROCESSING, stage=ROOT_STAGE_EVIDENCE_RETRIEVAL)
    result = bootstrap_document_alignment_workflow_items(_command(lease), _dependencies(app_module))
    assert result.outcome == BOOTSTRAP_OUTCOME_INVALID_RUN_STATE
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    assert app_module.DocumentAlignmentWorkflowRun.query.one().status == ROOT_STATUS_PROCESSING
    _cleanup(app_module)


def test_initial_parse_block_is_explicit_and_writes_nothing(app_module):
    source = _source(parse_quality="blocked")
    _, _, lease = _setup(app_module, source)
    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, source=source),
    )
    assert result.outcome == "parse_blocked"
    assert result.error_code == "DOCUMENT_ALIGNMENT_PARSE_BLOCKED"
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    assert app_module.DocumentAlignmentWorkflowRun.query.one().status == ROOT_STATUS_QUEUED
    _cleanup(app_module)


def test_extraction_failure_is_retryable_and_does_not_persist_root_or_items(app_module):
    sentinel = "LEXIBRIDGE_SENTINEL_SECRET_9C5A"
    _, _, lease = _setup(app_module)

    def fail(text):
        raise RuntimeError(sentinel)

    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, extractor=fail),
    )
    assert result.outcome == "extraction_failed"
    assert result.retryable is True
    assert sentinel not in result.error_message
    assert sentinel not in repr(result)
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    assert app_module.DocumentAlignmentWorkflowRun.query.one().status == ROOT_STATUS_QUEUED
    _cleanup(app_module)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"worker_id": "wrong-worker"}, BOOTSTRAP_OUTCOME_LEASE_NOT_OWNED),
        ({"execution_attempt": 99}, BOOTSTRAP_OUTCOME_STALE_ATTEMPT),
        ({"lease_token": "wrong-token"}, BOOTSTRAP_OUTCOME_LEASE_NOT_OWNED),
    ],
)
def test_wrong_lease_identity_cannot_write_items_or_root(app_module, overrides, expected):
    _, _, lease = _setup(app_module)
    result = bootstrap_document_alignment_workflow_items(_command(lease, **overrides), _dependencies(app_module))
    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid="workflow-bootstrap-9c5a").one()
    assert result.outcome == expected
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    assert run.status == ROOT_STATUS_QUEUED
    _cleanup(app_module)


def test_expired_lease_cannot_write_items(app_module):
    _, _, lease = _setup(app_module)
    dependencies = _dependencies(app_module, current_time_factory=lambda: lease.lease_expires_at)
    result = bootstrap_document_alignment_workflow_items(_command(lease), dependencies)
    assert result.outcome == BOOTSTRAP_OUTCOME_LEASE_EXPIRED
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    _cleanup(app_module)


def test_repeated_bootstrap_reuses_items_without_resetting_downstream_state(app_module):
    _, _, lease = _setup(app_module)
    dependencies = _dependencies(app_module)
    first = bootstrap_document_alignment_workflow_items(_command(lease), dependencies)
    item = app_module.DocumentAlignmentWorkflowItem.query.first()
    item.status = "needs_review"
    item.stage = "terminal"
    item.draft_card_uid = "draft-existing-9c5a"
    item.verification_run_uid = "verification-existing-9c5a"
    app_module.db.session.commit()

    second = bootstrap_document_alignment_workflow_items(_command(lease), dependencies)
    app_module.db.session.expire_all()
    stored = app_module.DocumentAlignmentWorkflowItem.query.filter_by(item_uid=item.item_uid).one()
    assert first.outcome == BOOTSTRAP_OUTCOME_CREATED
    assert second.outcome == BOOTSTRAP_OUTCOME_REUSED
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 2
    assert stored.status == "needs_review"
    assert stored.draft_card_uid == "draft-existing-9c5a"
    assert stored.verification_run_uid == "verification-existing-9c5a"
    _cleanup(app_module)


def test_no_candidates_block_but_item_overflow_preserves_bounded_items(app_module):
    _, _, lease = _setup(app_module)
    no_candidates = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, extractor=lambda text: []),
    )
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid="workflow-bootstrap-9c5a").one()
    assert no_candidates.outcome == BOOTSTRAP_OUTCOME_NO_CANDIDATES
    assert run.status == ROOT_STATUS_BLOCKED
    assert run.stage == ROOT_STAGE_TERMINAL
    assert run.error_code == "DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES"
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0

    _, _, lease = _setup(app_module)
    terms = [{"english_term": f"Candidate Term {index}"} for index in range(51)]
    limited = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, extractor=lambda text: terms),
    )
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid="workflow-bootstrap-9c5a").one()
    governance = json.loads(run.risk_summary)["candidate_set_overflow"]
    assert limited.outcome == BOOTSTRAP_OUTCOME_CREATED
    assert limited.canonical_candidate_count == 51
    assert limited.admitted_candidate_count == 50
    assert limited.overflow_candidate_count == 1
    assert len(limited.overflow_candidate_ids) == 1
    assert run.status == ROOT_STATUS_PROCESSING
    assert run.error_code == ""
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 50
    assert governance["canonical_count"] == 51
    assert governance["admitted_count"] == 50
    assert governance["overflow_count"] == 1
    assert governance["item_limit"] == 50
    assert governance["overflow_candidates"][0]["candidate_id"] == limited.overflow_candidate_ids[0]
    assert governance["overflow_candidates"][0]["source_uid"] == "source-bootstrap-9c5a"
    assert governance["overflow_candidates"][0]["source_chunk_uids"]
    _cleanup(app_module)


def test_source_snapshot_drift_before_persistence_blocks_without_items(app_module):
    source = _source()
    _, _, lease = _setup(app_module, source)
    calls = {"count": 0}

    def changing_source(session, source_uid):
        calls["count"] += 1
        return source if calls["count"] == 1 else replace(source, source_version="4")

    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, source=source, source_loader=changing_source),
    )
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid="workflow-bootstrap-9c5a").one()
    assert result.outcome == BOOTSTRAP_OUTCOME_SOURCE_CHANGED
    assert run.status == ROOT_STATUS_BLOCKED
    assert run.error_code == "DOCUMENT_ALIGNMENT_SOURCE_CHANGED"
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    _cleanup(app_module)


@pytest.mark.parametrize(
    "change",
    [
        lambda source: replace(source, parse_uid="parse-bootstrap-changed"),
        lambda source: replace(source, parse_quality="blocked"),
    ],
)
def test_parse_drift_before_persistence_blocks_without_items(app_module, change):
    source = _source()
    _, _, lease = _setup(app_module, source)
    calls = {"count": 0}

    def changing_source(session, source_uid):
        calls["count"] += 1
        return source if calls["count"] == 1 else change(source)

    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, source=source, source_loader=changing_source),
    )
    assert result.outcome == BOOTSTRAP_OUTCOME_SOURCE_CHANGED
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    _cleanup(app_module)


def test_chunk_membership_drift_before_persistence_blocks_without_items(app_module):
    source = _source()
    chunks = _chunks(source)
    _, _, lease = _setup(app_module, source)
    calls = {"count": 0}

    def changing_chunks(session, snapshot):
        calls["count"] += 1
        return chunks if calls["count"] == 1 else chunks[:1]

    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, source=source, chunk_loader=changing_chunks),
    )
    assert result.outcome == BOOTSTRAP_OUTCOME_SOURCE_CHANGED
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    _cleanup(app_module)


def test_term_scope_limit_blocks_without_silent_provenance_truncation(app_module):
    source = _source(usable_chunk_count=101)
    chunks = tuple(
        GovernedSourceChunkSnapshot(
            chunk_uid=f"scope-chunk-{index:03d}",
            source_uid=source.source_uid,
            parse_uid=source.parse_uid,
            source_version=source.source_version,
            chunk_index=index,
            text="Shared Term",
        )
        for index in range(101)
    )
    _, _, lease = _setup(app_module, source)
    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, source=source, chunks=chunks),
    )
    assert result.outcome == BOOTSTRAP_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED
    assert result.canonical_candidate_count == 1
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    _cleanup(app_module)


def test_existing_item_key_with_conflicting_fields_is_not_overwritten(app_module):
    run, _, lease = _setup(app_module)
    key = build_document_alignment_item_key("fourier transform", ("chunk-bootstrap-a",))
    app_module.db.session.add(app_module.DocumentAlignmentWorkflowItem(
        item_uid="conflicting-item-9c5a",
        workflow_run_id=run.id,
        item_key=key,
        candidate_term="Different Term",
        normalized_term="different term",
        source_chunk_refs=json.dumps(["chunk-bootstrap-a"]),
        status=ITEM_STATUS_CANDIDATE,
        stage=ITEM_STAGE_CANDIDATE,
        created_at="2026-07-18 11:59:30",
    ))
    app_module.db.session.commit()
    result = bootstrap_document_alignment_workflow_items(_command(lease), _dependencies(app_module))
    stored = app_module.DocumentAlignmentWorkflowItem.query.filter_by(item_uid="conflicting-item-9c5a").one()
    assert result.outcome == BOOTSTRAP_OUTCOME_ITEM_IDEMPOTENCY_CONFLICT
    assert result.error_code == "DOCUMENT_ALIGNMENT_ITEM_IDEMPOTENCY_CONFLICT"
    assert stored.normalized_term == "different term"
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 1
    _cleanup(app_module)


def test_bootstrap_write_phase_commits_once(app_module):
    class CountCommits:
        def __init__(self, session):
            self.session = session
            self.commit_count = 0

        def __getattr__(self, name):
            return getattr(self.session, name)

        def commit(self):
            self.commit_count += 1
            return self.session.commit()

    _, _, lease = _setup(app_module)
    wrapped = CountCommits(app_module.db.session)
    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, session=wrapped),
    )
    assert result.outcome == BOOTSTRAP_OUTCOME_CREATED
    assert wrapped.commit_count == 1
    _cleanup(app_module)


def test_matching_item_key_integrity_conflict_reacquires_fence_and_reuses_consistent_rows(app_module):
    class InsertCompetitorThenConflict:
        def __init__(self, session):
            self.session = session
            self.injected = False

        def __getattr__(self, name):
            return getattr(self.session, name)

        def commit(self):
            if self.injected:
                return self.session.commit()
            self.injected = True
            self.session.rollback()
            run = app_module.DocumentAlignmentWorkflowRun.query.one()
            for index, (term, chunk_uid) in enumerate(
                (("Fourier Transform", "chunk-bootstrap-a"), ("Laplace Transform", "chunk-bootstrap-b")),
                start=1,
            ):
                self.session.add(app_module.DocumentAlignmentWorkflowItem(
                    item_uid=f"competing-item-{index}",
                    workflow_run_id=run.id,
                    item_key=build_document_alignment_item_key(term.casefold(), (chunk_uid,)),
                    candidate_term=term,
                    normalized_term=term.casefold(),
                    source_chunk_refs=json.dumps([chunk_uid], separators=(",", ":")),
                    status=ITEM_STATUS_CANDIDATE,
                    stage=ITEM_STAGE_CANDIDATE,
                    created_at="2026-07-18 12:00:01",
                ))
            self.session.commit()
            raise IntegrityError(
                "INSERT",
                {},
                RuntimeError(
                    "UNIQUE constraint failed: document_alignment_workflow_items.workflow_run_id, "
                    "document_alignment_workflow_items.item_key"
                ),
            )

    _, _, lease = _setup(app_module)
    wrapped = InsertCompetitorThenConflict(app_module.db.session)
    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, session=wrapped),
    )
    assert result.outcome == BOOTSTRAP_OUTCOME_REUSED
    assert result.created_item_count == 0
    assert result.reused_item_count == 2
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 2
    assert app_module.DocumentAlignmentWorkflowRun.query.one().status == ROOT_STATUS_PROCESSING
    _cleanup(app_module)


def test_non_item_key_integrity_error_is_not_treated_as_idempotent_success(app_module):
    class WrongConstraintFailure:
        def __init__(self, session):
            self.session = session

        def __getattr__(self, name):
            return getattr(self.session, name)

        def commit(self):
            self.session.rollback()
            raise IntegrityError(
                "INSERT",
                {},
                RuntimeError("UNIQUE constraint failed: document_alignment_workflow_items.item_uid"),
            )

    _, _, lease = _setup(app_module)
    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, session=WrongConstraintFailure(app_module.db.session)),
    )
    assert result.outcome == BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    assert app_module.DocumentAlignmentWorkflowRun.query.one().status == ROOT_STATUS_QUEUED
    _cleanup(app_module)


@pytest.mark.parametrize("status", ["ready_for_review", "completed_with_warnings", "blocked", "failed"])
def test_terminal_or_post_bootstrap_run_state_is_not_mutated(app_module, status):
    _, _, lease = _setup(app_module, status=status, stage=ROOT_STAGE_TERMINAL)
    result = bootstrap_document_alignment_workflow_items(_command(lease), _dependencies(app_module))
    assert result.outcome == BOOTSTRAP_OUTCOME_INVALID_RUN_STATE
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    assert app_module.DocumentAlignmentWorkflowRun.query.one().status == status
    _cleanup(app_module)


def test_bootstrap_writes_no_downstream_legacy_usage_or_audit_records(app_module):
    _, _, lease = _setup(app_module)
    before = {
        "cards": app_module.ConceptAlignmentCard.query.count(),
        "verification": app_module.AlignmentVerificationRun.query.count(),
        "usage": app_module.UsageRecord.query.count(),
        "preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "audit": app_module.AuditRecord.query.count(),
        "legacy_runs": app_module.AlignmentRun.query.count(),
        "legacy_cards": app_module.TerminologyCard.query.count(),
        "legacy_calls": app_module.AICallLog.query.count(),
    }
    result = bootstrap_document_alignment_workflow_items(_command(lease), _dependencies(app_module))
    after = {
        "cards": app_module.ConceptAlignmentCard.query.count(),
        "verification": app_module.AlignmentVerificationRun.query.count(),
        "usage": app_module.UsageRecord.query.count(),
        "preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "audit": app_module.AuditRecord.query.count(),
        "legacy_runs": app_module.AlignmentRun.query.count(),
        "legacy_cards": app_module.TerminologyCard.query.count(),
        "legacy_calls": app_module.AICallLog.query.count(),
    }
    assert result.outcome == BOOTSTRAP_OUTCOME_CREATED
    assert after == before
    _cleanup(app_module)


def test_bootstrap_commit_failure_rolls_back_fence_items_and_root_and_session_recovers(app_module):
    class FailCommitOnce:
        def __init__(self, session):
            self.session = session
            self.failed = False

        def __getattr__(self, name):
            return getattr(self.session, name)

        def commit(self):
            if not self.failed:
                self.failed = True
                raise RuntimeError("commit failed")
            return self.session.commit()

    _, _, lease = _setup(app_module)
    wrapped = FailCommitOnce(app_module.db.session)
    result = bootstrap_document_alignment_workflow_items(
        _command(lease),
        _dependencies(app_module, session=wrapped),
    )
    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.one()
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    assert result.outcome == BOOTSTRAP_OUTCOME_PERSISTENCE_ERROR
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
    assert run.status == ROOT_STATUS_QUEUED
    assert job.heartbeat_at == NOW.strftime("%Y-%m-%d %H:%M:%S")
    assert app_module.DocumentAlignmentWorkflowRun.query.count() == 1
    _cleanup(app_module)
