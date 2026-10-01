import json
import uuid

from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
from services.document_alignment_workflow_application import (
    DocumentAlignmentSourceAdmissionDecision,
    DocumentAlignmentWorkflowApplicationDependencies,
    DocumentAlignmentWorkflowAuthorizationDecision,
    GovernedKnowledgeSourceSnapshot,
    StartDocumentAlignmentWorkflowCommand,
    start_document_alignment_workflow,
)


def _uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _create_governed_source(app_module, *, source_uid=None, parse_uid=None, chunk_count=1, parse_status="success", quality_status="native_text_ok"):
    parse_uid = parse_uid or _uid("parse-9c4x")
    source_uid = source_uid or _uid("source-9c4x")
    parse = app_module.DocumentParseRecord(
        parse_uid=parse_uid,
        source_filename="formal-admission.txt",
        parse_status=parse_status,
        quality_status=quality_status,
        block_count=chunk_count,
        extracted_text_chars=128,
    )
    app_module.db.session.add(parse)
    app_module.db.session.flush()
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        title="Formal admission source",
        name="Formal admission source",
        course="Signals",
        chapter="Frequency",
        visibility="course",
        trust_level="teacher_verified",
        status="active",
        quality_status=quality_status,
        parse_uid=parse.parse_uid,
        version=1,
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    for index in range(chunk_count):
        app_module.db.session.add(app_module.KnowledgeChunk(
            chunk_uid=_uid("chunk-9c4x"),
            source_uid=source.source_uid,
            knowledge_source_id=source.id,
            document_id=0,
            parse_uid=parse.parse_uid,
            course=source.course,
            chapter=source.chapter,
            content=f"Governed evidence chunk {index}",
            status="active",
            quality_status=quality_status,
            trust_level="teacher_verified",
        ))
    app_module.db.session.commit()
    return source


def _loader(app_module):
    def load(source_uid):
        source = app_module.KnowledgeSource.query.filter_by(source_uid=source_uid).first()
        if source is None:
            return None
        parse = app_module.DocumentParseRecord.query.filter_by(parse_uid=source.parse_uid).first()
        usable_chunks = app_module.KnowledgeChunk.query.filter_by(
            knowledge_source_id=source.id,
            status="active",
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
            parse_status=getattr(parse, "parse_status", "") if parse else "",
            parse_quality=getattr(parse, "quality_status", "") if parse else source.quality_status,
            usable_chunk_count=usable_chunks,
        )
    return load


def _authorize(actor, snapshot):
    if str(actor).startswith("student"):
        return DocumentAlignmentWorkflowAuthorizationDecision(
            allowed=False,
            safe_error_code="DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE",
            safe_error_message="Source is not available.",
        )
    return DocumentAlignmentWorkflowAuthorizationDecision(allowed=True)


def _admit(snapshot):
    if snapshot.source_status != "active":
        return DocumentAlignmentSourceAdmissionDecision(False, "DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE", "Source is not available.", "source_not_available")
    if snapshot.source_trust_level not in {"teacher_verified", "governed", "approved"}:
        return DocumentAlignmentSourceAdmissionDecision(False, "DOCUMENT_ALIGNMENT_SOURCE_NOT_GOVERNED", "Source is not governed.", "source_not_governed")
    if snapshot.parse_status != "success" or snapshot.parse_quality not in {"native_text_ok", "partial_text"}:
        return DocumentAlignmentSourceAdmissionDecision(False, "DOCUMENT_ALIGNMENT_PARSE_BLOCKED", "Parse is blocked.", "parse_blocked")
    if snapshot.usable_chunk_count <= 0:
        return DocumentAlignmentSourceAdmissionDecision(False, "DOCUMENT_ALIGNMENT_NO_USABLE_CHUNKS", "No usable chunks.", "no_usable_chunks")
    return DocumentAlignmentSourceAdmissionDecision(True)


def _dependencies(app_module, **overrides):
    values = {
        "session": app_module.db.session,
        "workflow_run_model": app_module.DocumentAlignmentWorkflowRun,
        "background_job_model": app_module.BackgroundJob,
        "audit_record_model": app_module.AuditRecord,
        "source_loader": _loader(app_module),
        "authorization_checker": _authorize,
        "source_admission_checker": _admit,
        "current_time_factory": app_module.current_time_text,
        "uid_factory": lambda: _uid("workflow-run-9c4x"),
    }
    values.update(overrides)
    return DocumentAlignmentWorkflowApplicationDependencies(**values)


def _command(source_uid, **overrides):
    values = {
        "source_uid": source_uid,
        "requested_by": "teacher-9c4x",
        "request_id": _uid("request-9c4x"),
        "idempotency_key": "idem-9c4x",
    }
    values.update(overrides)
    return StartDocumentAlignmentWorkflowCommand(**values)


def _cleanup(app_module):
    app_module.db.session.rollback()
    app_module.DocumentAlignmentWorkflowItem.query.delete()
    app_module.DocumentAlignmentWorkflowRun.query.delete()
    app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete()
    app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").delete()
    app_module.KnowledgeChunk.query.filter(app_module.KnowledgeChunk.source_uid.like("source-9c4x%")).delete(synchronize_session=False)
    app_module.KnowledgeSource.query.filter(app_module.KnowledgeSource.source_uid.like("source-9c4x%")).delete(synchronize_session=False)
    app_module.DocumentParseRecord.query.filter(app_module.DocumentParseRecord.parse_uid.like("parse-9c4x%")).delete(synchronize_session=False)
    app_module.db.session.commit()


def test_real_start_creates_root_job_and_audit_in_one_transaction(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        source = _create_governed_source(app_module, source_uid="source-9c4x-real", parse_uid="parse-9c4x-real")

        result = start_document_alignment_workflow(_command(source.source_uid), _dependencies(app_module))

        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=result.run_uid).one()
        job = app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).one()
        audit = app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").one()

        assert result.outcome == "created"
        assert run.source_uid == source.source_uid
        assert run.parse_uid == source.parse_uid
        assert run.status == "queued"
        assert run.stage == "queued"
        assert run.total_items == 0
        assert json.loads(job.input_json) == {
            "workflow_run_uid": run.run_uid,
            "workflow_version": run.workflow_version,
        }
        assert audit.target_uid == run.run_uid
        assert audit.request_id == result.request_id
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
        _cleanup(app_module)


def test_real_idempotency_reuses_conflicts_and_preserves_session(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        source = _create_governed_source(app_module, source_uid="source-9c4x-idem", parse_uid="parse-9c4x-idem")
        created = start_document_alignment_workflow(_command(source.source_uid), _dependencies(app_module))

        reused = start_document_alignment_workflow(
            _command(source.source_uid, request_id=_uid("request-9c4x-replay")),
            _dependencies(app_module),
        )
        source.parse_uid = "parse-9c4x-idem-updated"
        app_module.db.session.add(app_module.DocumentParseRecord(
            parse_uid=source.parse_uid,
            source_filename="changed.txt",
            parse_status="success",
            quality_status="native_text_ok",
            block_count=1,
            extracted_text_chars=64,
        ))
        app_module.db.session.commit()
        conflict = start_document_alignment_workflow(
            _command(source.source_uid, request_id=_uid("request-9c4x-conflict")),
            _dependencies(app_module),
        )

        assert created.outcome == "created"
        assert reused.outcome == "reused"
        assert reused.run_uid == created.run_uid
        assert conflict.outcome == "idempotency_conflict"
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 1
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 1
        assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 1
        assert app_module.DocumentAlignmentWorkflowRun.query.first()
        _cleanup(app_module)


def test_real_blocked_paths_and_rollback_create_no_business_records(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        legacy_counts_before = {
            "runs": app_module.AlignmentRun.query.count(),
            "terms": app_module.TerminologyCard.query.count(),
            "ai_call_logs": app_module.AICallLog.query.count(),
        }
        source = _create_governed_source(app_module, source_uid="source-9c4x-blocked", parse_uid="parse-9c4x-blocked", chunk_count=0)
        no_chunks = start_document_alignment_workflow(_command(source.source_uid), _dependencies(app_module))
        denied = start_document_alignment_workflow(_command(source.source_uid, requested_by="student-9c4x"), _dependencies(app_module))

        def failing_audit(*args, **kwargs):
            raise RuntimeError("audit unavailable")

        source_with_chunk = _create_governed_source(app_module, source_uid="source-9c4x-rollback", parse_uid="parse-9c4x-rollback")
        failed = start_document_alignment_workflow(
            _command(source_with_chunk.source_uid, idempotency_key="idem-rollback"),
            _dependencies(app_module, audit_recorder=failing_audit),
        )

        assert no_chunks.outcome == "no_usable_chunks"
        assert denied.outcome == "source_not_available"
        assert failed.outcome == "persistence_error"
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 0
        assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 0
        assert app_module.AlignmentRun.query.count() == legacy_counts_before["runs"]
        assert app_module.TerminologyCard.query.count() == legacy_counts_before["terms"]
        assert app_module.AICallLog.query.count() == legacy_counts_before["ai_call_logs"]
        _cleanup(app_module)
