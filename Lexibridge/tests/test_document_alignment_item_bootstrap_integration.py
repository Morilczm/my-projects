import json
import threading
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from services.document_alignment_item_bootstrap import (
    BOOTSTRAP_OUTCOME_CREATED,
    BOOTSTRAP_OUTCOME_REUSED,
    BOOTSTRAP_OUTCOME_SOURCE_CHANGED,
    BOOTSTRAP_OUTCOME_STALE_ATTEMPT,
    BootstrapDocumentAlignmentItemsCommand,
    BootstrapDocumentAlignmentItemsDependencies,
    bootstrap_document_alignment_workflow_items,
)
from services.document_alignment_term_candidates import GovernedSourceChunkSnapshot
from services.document_alignment_workflow_application import GovernedKnowledgeSourceSnapshot
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ROOT_STAGE_QUEUED,
    ROOT_STATUS_QUEUED,
    WORKFLOW_VERSION_V1,
)
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
)


NOW = datetime(2026, 7, 18, 13, 0, 0)
PREFIX = "bootstrap-integration-9c5a"


@pytest.fixture(autouse=True)
def _app_context(app_module):
    with app_module.app.app_context():
        yield


def _cleanup(app_module):
    app_module.db.session.rollback()
    app_module.DocumentAlignmentWorkflowItem.query.filter(
        app_module.DocumentAlignmentWorkflowItem.item_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).filter(
        app_module.BackgroundJob.input_json.like(f"%{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.KnowledgeChunk.query.filter(
        app_module.KnowledgeChunk.source_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.KnowledgeSource.query.filter(
        app_module.KnowledgeSource.source_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentParseRecord.query.filter(
        app_module.DocumentParseRecord.parse_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.db.session.commit()
    app_module.db.session.expunge_all()


def _setup(app_module, suffix="real"):
    _cleanup(app_module)
    run_uid = f"{PREFIX}-run-{suffix}"
    source_uid = f"{PREFIX}-source-{suffix}"
    parse_uid = f"{PREFIX}-parse-{suffix}"
    parse = app_module.DocumentParseRecord(
        parse_uid=parse_uid,
        source_filename="formal-bootstrap.txt",
        parse_status="success",
        quality_status="native_text_ok",
        block_count=2,
        extracted_text_chars=64,
    )
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        title="Formal bootstrap source",
        name="Formal bootstrap source",
        course="Signals",
        chapter="Frequency",
        owner_user_id=1,
        visibility="course",
        trust_level="teacher_verified",
        parse_uid=parse_uid,
        version=1,
        quality_status="native_text_ok",
        status="active",
    )
    app_module.db.session.add_all([parse, source])
    app_module.db.session.flush()
    chunks = [
        app_module.KnowledgeChunk(
            chunk_uid=f"{PREFIX}-chunk-{suffix}-{index}",
            source_uid=source_uid,
            knowledge_source_id=source.id,
            document_id=0,
            parse_uid=parse_uid,
            course="Signals",
            chapter="Frequency",
            chunk_index=index,
            content=term,
            language="en",
            status="active",
            is_active=True,
            quality_status="native_text_ok",
            trust_level="teacher_verified",
        )
        for index, term in enumerate(("Fourier Transform", "Laplace Transform"))
    ]
    run = app_module.DocumentAlignmentWorkflowRun(
        run_uid=run_uid,
        source_uid=source_uid,
        parse_uid=parse_uid,
        source_version="1",
        course="Signals",
        chapter="Frequency",
        requested_by="1",
        request_id=f"{PREFIX}-request-{suffix}",
        idempotency_key=f"{PREFIX}-idem-{suffix}",
        idempotency_fingerprint=f"{PREFIX}-fingerprint-{suffix}",
        workflow_version=WORKFLOW_VERSION_V1,
        status=ROOT_STATUS_QUEUED,
        stage=ROOT_STAGE_QUEUED,
        created_at="2026-07-18 12:59:00",
    )
    job = app_module.BackgroundJob(
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        status="queued",
        priority=100,
        created_by=1,
        input_json=json.dumps({"workflow_run_uid": run_uid, "workflow_version": WORKFLOW_VERSION_V1}),
        result_json="{}",
        attempt_count=0,
        max_attempts=3,
        created_at="2026-07-18 12:59:00",
        updated_at="2026-07-18 12:59:00",
    )
    app_module.db.session.add_all([*chunks, run, job])
    app_module.db.session.commit()
    lease = claim_next_formal_background_job(
        f"{PREFIX}-worker-old",
        FormalBackgroundJobExecutionDependencies(
            session=app_module.db.session,
            job_model=app_module.BackgroundJob,
            current_time_factory=lambda: NOW,
            lease_token_factory=lambda: f"{PREFIX}-lease-old",
        ),
    ).lease
    return run_uid, source_uid, lease


def _source_loader(app_module):
    def load(session, source_uid):
        source = session.query(app_module.KnowledgeSource).filter_by(source_uid=source_uid).one_or_none()
        if source is None:
            return None
        parse = session.query(app_module.DocumentParseRecord).filter_by(parse_uid=source.parse_uid).one_or_none()
        chunk_count = session.query(app_module.KnowledgeChunk).filter_by(
            source_uid=source.source_uid,
            parse_uid=source.parse_uid,
            status="active",
            is_active=True,
        ).count()
        return GovernedKnowledgeSourceSnapshot(
            source_uid=source.source_uid,
            parse_uid=source.parse_uid,
            source_version=str(source.version or ""),
            course=source.course,
            chapter=source.chapter,
            owner_user_id=str(source.owner_user_id or ""),
            visibility=source.visibility,
            source_status=source.status,
            source_trust_level=source.trust_level,
            parse_status=parse.parse_status if parse else "",
            parse_quality=parse.quality_status if parse else "",
            usable_chunk_count=chunk_count,
        )

    return load


def _chunk_loader(app_module):
    def load(session, source):
        rows = session.query(app_module.KnowledgeChunk).filter_by(
            source_uid=source.source_uid,
            parse_uid=source.parse_uid,
            status="active",
            is_active=True,
        ).order_by(app_module.KnowledgeChunk.chunk_index, app_module.KnowledgeChunk.chunk_uid).all()
        return tuple(
            GovernedSourceChunkSnapshot(
                chunk_uid=row.chunk_uid,
                source_uid=row.source_uid,
                parse_uid=row.parse_uid,
                source_version=source.source_version,
                chunk_index=row.chunk_index,
                text=row.content,
                language=row.language,
                chapter_scope=row.chapter,
            )
            for row in rows
        )

    return load


def _command(run_uid, lease):
    return BootstrapDocumentAlignmentItemsCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )


def _dependencies(app_module, session, *, suffix="real", term_extractor=None, now=None):
    item_counter = iter(range(1000))
    return BootstrapDocumentAlignmentItemsDependencies(
        session=session,
        workflow_run_model=app_module.DocumentAlignmentWorkflowRun,
        workflow_item_model=app_module.DocumentAlignmentWorkflowItem,
        background_job_model=app_module.BackgroundJob,
        source_loader=_source_loader(app_module),
        chunk_loader=_chunk_loader(app_module),
        term_extractor=term_extractor or (lambda text: [{"english_term": text}]),
        item_uid_factory=lambda: f"{PREFIX}-item-{suffix}-{next(item_counter)}-{uuid.uuid4().hex[:6]}",
        current_time_factory=lambda: now or NOW + timedelta(seconds=1),
    )


def test_real_governed_bootstrap_reuses_across_independent_sessions_and_enforces_unique_key(app_module):
    run_uid, _, lease = _setup(app_module, "replay")
    Session = sessionmaker(bind=app_module.db.engine)
    first_session = Session()
    second_session = Session()
    try:
        first = bootstrap_document_alignment_workflow_items(
            _command(run_uid, lease),
            _dependencies(app_module, first_session, suffix="replay-first"),
        )
        second = bootstrap_document_alignment_workflow_items(
            _command(run_uid, lease),
            _dependencies(app_module, second_session, suffix="replay-second"),
        )
        assert first.outcome == BOOTSTRAP_OUTCOME_CREATED
        assert second.outcome == BOOTSTRAP_OUTCOME_REUSED
        app_module.db.session.expire_all()
        items = app_module.DocumentAlignmentWorkflowItem.query.order_by(
            app_module.DocumentAlignmentWorkflowItem.item_key
        ).all()
        assert len(items) == 2
        duplicate = app_module.DocumentAlignmentWorkflowItem(
            item_uid=f"{PREFIX}-item-duplicate",
            workflow_run_id=items[0].workflow_run_id,
            item_key=items[0].item_key,
            candidate_term=items[0].candidate_term,
            normalized_term=items[0].normalized_term,
            source_chunk_refs=items[0].source_chunk_refs,
            status="candidate",
            stage="candidate",
            created_at="2026-07-18 13:01:00",
        )
        app_module.db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 2
    finally:
        first_session.close()
        second_session.close()
        _cleanup(app_module)


def test_real_stale_reclaim_fences_old_attempt_from_business_writes(app_module):
    run_uid, _, old_lease = _setup(app_module, "stale")
    Session = sessionmaker(bind=app_module.db.engine)
    reclaim_session = Session()
    old_session = Session()
    try:
        reclaimed = claim_next_formal_background_job(
            f"{PREFIX}-worker-new",
            FormalBackgroundJobExecutionDependencies(
                session=reclaim_session,
                job_model=app_module.BackgroundJob,
                current_time_factory=lambda: old_lease.lease_expires_at + timedelta(seconds=1),
                lease_token_factory=lambda: f"{PREFIX}-lease-new",
            ),
        ).lease
        assert reclaimed.execution_attempt == old_lease.execution_attempt + 1
        old_result = bootstrap_document_alignment_workflow_items(
            _command(run_uid, old_lease),
            _dependencies(
                app_module,
                old_session,
                suffix="stale-old",
                now=old_lease.lease_expires_at + timedelta(seconds=2),
            ),
        )
        assert old_result.outcome == BOOTSTRAP_OUTCOME_STALE_ATTEMPT
        app_module.db.session.expire_all()
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
        assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one().status == ROOT_STATUS_QUEUED
    finally:
        reclaim_session.close()
        old_session.close()
        _cleanup(app_module)


@pytest.mark.parametrize("iteration", range(5))
def test_two_independent_sessions_converge_without_duplicate_items_or_database_lock(app_module, iteration):
    run_uid, _, lease = _setup(app_module, f"concurrent-{iteration}")
    Session = sessionmaker(bind=app_module.db.engine)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def invoke(worker_suffix):
        session = Session()
        waited = False

        def extractor(text):
            nonlocal waited
            if not waited:
                waited = True
                barrier.wait(timeout=5)
            return [{"english_term": text}]

        try:
            results.append(
                bootstrap_document_alignment_workflow_items(
                    _command(run_uid, lease),
                    _dependencies(
                        app_module,
                        session,
                        suffix=f"concurrent-{iteration}-{worker_suffix}",
                        term_extractor=extractor,
                    ),
                )
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=invoke, args=(suffix,)) for suffix in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(result.outcome for result in results) == [BOOTSTRAP_OUTCOME_CREATED, BOOTSTRAP_OUTCOME_REUSED]
    app_module.db.session.expire_all()
    assert app_module.DocumentAlignmentWorkflowItem.query.count() == 2
    _cleanup(app_module)


def test_real_source_version_drift_between_compute_and_fenced_persistence_writes_no_items(app_module):
    run_uid, source_uid, lease = _setup(app_module, "drift")
    Session = sessionmaker(bind=app_module.db.engine)
    bootstrap_session = Session()
    drift_session = Session()
    changed = False

    def extractor(text):
        nonlocal changed
        if not changed:
            changed = True
            source = drift_session.query(app_module.KnowledgeSource).filter_by(source_uid=source_uid).one()
            source.version = 2
            drift_session.commit()
        return [{"english_term": text}]

    try:
        result = bootstrap_document_alignment_workflow_items(
            _command(run_uid, lease),
            _dependencies(app_module, bootstrap_session, suffix="drift", term_extractor=extractor),
        )
        assert result.outcome == BOOTSTRAP_OUTCOME_SOURCE_CHANGED
        app_module.db.session.expire_all()
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
        assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one().status == "blocked"
    finally:
        bootstrap_session.close()
        drift_session.close()
        _cleanup(app_module)


def test_real_bootstrap_has_no_formal_downstream_or_legacy_dual_writes(app_module):
    run_uid, _, lease = _setup(app_module, "write-set")
    before = {
        "cards": app_module.ConceptAlignmentCard.query.count(),
        "verification": app_module.AlignmentVerificationRun.query.count(),
        "usage": app_module.UsageRecord.query.count(),
        "audit": app_module.AuditRecord.query.count(),
        "legacy_runs": app_module.AlignmentRun.query.count(),
        "legacy_cards": app_module.TerminologyCard.query.count(),
        "legacy_calls": app_module.AICallLog.query.count(),
    }
    Session = sessionmaker(bind=app_module.db.engine)
    session = Session()
    try:
        result = bootstrap_document_alignment_workflow_items(
            _command(run_uid, lease),
            _dependencies(app_module, session, suffix="write-set"),
        )
        assert result.outcome == BOOTSTRAP_OUTCOME_CREATED
        after = {
            "cards": app_module.ConceptAlignmentCard.query.count(),
            "verification": app_module.AlignmentVerificationRun.query.count(),
            "usage": app_module.UsageRecord.query.count(),
            "audit": app_module.AuditRecord.query.count(),
            "legacy_runs": app_module.AlignmentRun.query.count(),
            "legacy_cards": app_module.TerminologyCard.query.count(),
            "legacy_calls": app_module.AICallLog.query.count(),
        }
        assert after == before
    finally:
        session.close()
        _cleanup(app_module)
