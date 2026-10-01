import json

import pytest

from services.document_alignment_workflow_application import (
    DocumentAlignmentSourceAdmissionDecision,
    DocumentAlignmentWorkflowApplicationDependencies,
    DocumentAlignmentWorkflowAuthorizationDecision,
    GovernedKnowledgeSourceSnapshot,
    StartDocumentAlignmentWorkflowCommand,
    start_document_alignment_workflow,
)
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ITEM_STATUS_NEEDS_REVIEW,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_READY_FOR_REVIEW,
)
from services.formal_document_alignment_provider_selection import (
    FORMAL_DEFAULT_MODEL_IDENTITY,
    FORMAL_DEFAULT_PROVIDER_NAME,
)


PREFIX = "formal-worker-integration-9c5d"


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
    runs = app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
        | app_module.DocumentAlignmentWorkflowRun.source_uid.like(f"{PREFIX}%")
    ).all()
    run_ids = [row.id for row in runs]
    run_uids = [row.run_uid for row in runs]
    items = (
        app_module.DocumentAlignmentWorkflowItem.query.filter(
            app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(run_ids)
        ).all()
        if run_ids
        else []
    )
    item_uids = [item.item_uid for item in items]
    mappings = (
        app_module.DocumentAlignmentItemVerificationExecution.query.filter(
            app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.in_(run_uids)
        ).all()
        if run_uids
        else []
    )
    execution_keys = [row.execution_key for row in mappings]
    if execution_keys:
        app_module.AlignmentProviderUsageRecord.query.filter(
            app_module.AlignmentProviderUsageRecord.execution_key.in_(execution_keys)
        ).delete(synchronize_session=False)
        app_module.AlignmentVerificationRun.query.filter(
            app_module.AlignmentVerificationRun.execution_key.in_(execution_keys)
        ).delete(synchronize_session=False)
        app_module.AlignmentProviderPreflightRun.query.filter(
            app_module.AlignmentProviderPreflightRun.execution_key.in_(execution_keys)
        ).delete(synchronize_session=False)
    if run_uids:
        app_module.AuditRecord.query.filter(
            app_module.AuditRecord.target_uid.in_(run_uids + item_uids)
            | app_module.AuditRecord.target_uid.like(f"{PREFIX}%")
        ).delete(synchronize_session=False)
        app_module.DocumentAlignmentItemVerificationExecution.query.filter(
            app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.in_(run_uids)
        ).delete(synchronize_session=False)
    if run_ids:
        app_module.DocumentAlignmentWorkflowItem.query.filter(
            app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(run_ids)
        ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
        | app_module.DocumentAlignmentWorkflowRun.source_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.ConceptAlignmentCard.query.filter(
        app_module.ConceptAlignmentCard.course.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete(
        synchronize_session=False
    )
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


def _source_snapshot(app_module, source_uid):
    source = app_module.KnowledgeSource.query.filter_by(source_uid=source_uid).one_or_none()
    if source is None:
        return None
    parse = app_module.DocumentParseRecord.query.filter_by(parse_uid=source.parse_uid).one()
    usable = app_module.KnowledgeChunk.query.filter_by(
        source_uid=source.source_uid,
        parse_uid=source.parse_uid,
        status="active",
        is_active=True,
    ).count()
    return GovernedKnowledgeSourceSnapshot(
        source_uid=source.source_uid,
        parse_uid=source.parse_uid,
        source_version=str(source.version),
        course=source.course,
        chapter=source.chapter,
        owner_user_id=str(source.owner_user_id or ""),
        visibility=source.visibility,
        source_status=source.status,
        source_trust_level=source.trust_level,
        parse_status=parse.parse_status,
        parse_quality=parse.quality_status,
        usable_chunk_count=usable,
    )


def _setup_source(app_module):
    _cleanup(app_module)
    course = f"{PREFIX}-course"
    chapter = "Frequency"
    parse_en = app_module.DocumentParseRecord(
        parse_uid=f"{PREFIX}-parse-en",
        source_filename="formal-worker-en.txt",
        parse_status="success",
        quality_status="native_text_ok",
        block_count=2,
        extracted_text_chars=64,
    )
    parse_zh = app_module.DocumentParseRecord(
        parse_uid=f"{PREFIX}-parse-zh",
        source_filename="formal-worker-zh.txt",
        parse_status="success",
        quality_status="native_text_ok",
        block_count=2,
        extracted_text_chars=64,
    )
    source_en = app_module.KnowledgeSource(
        source_uid=f"{PREFIX}-source-en",
        title="Formal worker English source",
        name="Formal worker English source",
        course=course,
        chapter=chapter,
        owner_user_id=1,
        visibility="course",
        language="en",
        source_type="course_material",
        source_role="english_course_material",
        trust_level="teacher_verified",
        parse_uid=parse_en.parse_uid,
        version=1,
        quality_status="native_text_ok",
        status="active",
        allow_derivative_cards=True,
    )
    source_zh = app_module.KnowledgeSource(
        source_uid=f"{PREFIX}-source-zh",
        title="Formal worker bilingual source",
        name="Formal worker bilingual source",
        course=course,
        chapter=chapter,
        owner_user_id=1,
        visibility="course",
        language="mixed",
        source_type="reference",
        source_role="bilingual_reference",
        trust_level="teacher_verified",
        parse_uid=parse_zh.parse_uid,
        version=1,
        quality_status="native_text_ok",
        status="active",
        allow_derivative_cards=True,
    )
    app_module.db.session.add_all([parse_en, parse_zh, source_en, source_zh])
    app_module.db.session.flush()
    for index, term in enumerate(("Fourier Transform", "Laplace Transform")):
        app_module.db.session.add(
            app_module.KnowledgeChunk(
                chunk_uid=f"{PREFIX}-chunk-en-{index}",
                source_uid=source_en.source_uid,
                knowledge_source_id=source_en.id,
                document_id=0,
                parse_uid=parse_en.parse_uid,
                course=course,
                chapter=chapter,
                chunk_index=index,
                content=term,
                language="en",
                status="active",
                is_active=True,
                quality_status="native_text_ok",
                trust_level="teacher_verified",
                visibility="course",
            )
        )
    for index, (english, chinese) in enumerate(
        (("Fourier Transform", "傅里叶变换"), ("Laplace Transform", "拉普拉斯变换"))
    ):
        app_module.db.session.add(
            app_module.KnowledgeChunk(
                chunk_uid=f"{PREFIX}-chunk-zh-{index}",
                source_uid=source_zh.source_uid,
                knowledge_source_id=source_zh.id,
                document_id=0,
                parse_uid=parse_zh.parse_uid,
                course=course,
                chapter=chapter,
                chunk_index=index,
                content=f"{chinese}（{english}）用于课程概念分析。",
                language="mixed",
                status="active",
                is_active=True,
                quality_status="native_text_ok",
                trust_level="teacher_verified",
                visibility="course",
            )
        )
    app_module.db.session.commit()
    return source_en


def _admission_dependencies(app_module):
    return DocumentAlignmentWorkflowApplicationDependencies(
        session=app_module.db.session,
        workflow_run_model=app_module.DocumentAlignmentWorkflowRun,
        background_job_model=app_module.BackgroundJob,
        audit_record_model=app_module.AuditRecord,
        source_loader=lambda source_uid: _source_snapshot(app_module, source_uid),
        authorization_checker=lambda actor, source: DocumentAlignmentWorkflowAuthorizationDecision(True),
        source_admission_checker=lambda source: DocumentAlignmentSourceAdmissionDecision(True),
        current_time_factory=app_module.current_time_text,
        uid_factory=lambda: f"{PREFIX}-run",
    )


def test_admission_job_is_claimed_and_processed_by_real_formal_worker(app_module):
    source = _setup_source(app_module)
    created = start_document_alignment_workflow(
        StartDocumentAlignmentWorkflowCommand(
            source_uid=source.source_uid,
            requested_by="1",
            request_id=f"{PREFIX}-request",
            idempotency_key=f"{PREFIX}-idempotency",
        ),
        _admission_dependencies(app_module),
    )
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=created.run_uid).one()
    assert run.provider_preference == FORMAL_DEFAULT_PROVIDER_NAME
    assert run.model_preference == FORMAL_DEFAULT_MODEL_IDENTITY
    assert run.prompt_version == "alignment-v1"
    legacy_before = {
        "runs": app_module.AlignmentRun.query.count(),
        "cards": app_module.TerminologyCard.query.count(),
        "usage": app_module.UsageRecord.query.count(),
        "calls": app_module.AICallLog.query.count(),
    }

    result = app_module.run_formal_worker_once(worker_id=f"{PREFIX}-worker")

    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=created.run_uid).one()
    job = app_module.BackgroundJob.query.filter(
        app_module.BackgroundJob.input_json.like(f"%{created.run_uid}%")
    ).one()
    items = app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).all()
    mappings = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
        workflow_run_uid=run.run_uid
    ).all()
    execution_keys = [row.execution_key for row in mappings]
    legacy_after = {
        "runs": app_module.AlignmentRun.query.count(),
        "cards": app_module.TerminologyCard.query.count(),
        "usage": app_module.UsageRecord.query.count(),
        "calls": app_module.AICallLog.query.count(),
    }

    assert created.outcome == "created"
    assert result.outcome == "completed"
    assert result.completed is True
    assert run.status == ROOT_STATUS_READY_FOR_REVIEW, [
        (item.candidate_term, item.status, item.error_code, item.error_message) for item in items
    ]
    assert run.stage == ROOT_STAGE_TERMINAL
    assert job.status == "completed"
    assert len(items) == 2
    assert all(item.status == ITEM_STATUS_NEEDS_REVIEW for item in items)
    assert run.total_items == 2
    assert run.ready_for_review_items == 2
    assert len(mappings) == 2
    assert app_module.AlignmentProviderPreflightRun.query.filter(
        app_module.AlignmentProviderPreflightRun.execution_key.in_(execution_keys)
    ).count() == 0
    assert app_module.AlignmentVerificationRun.query.filter(
        app_module.AlignmentVerificationRun.execution_key.in_(execution_keys)
    ).count() == 0
    assert app_module.AlignmentProviderUsageRecord.query.filter(
        app_module.AlignmentProviderUsageRecord.execution_key.in_(execution_keys)
    ).count() == 0
    assert legacy_after == legacy_before
    assert app_module.run_formal_worker_once(worker_id=f"{PREFIX}-worker-repeat").outcome == "no_job_available"
    app_module.db.session.rollback()
    assert app_module.BackgroundJob.query.count() >= 1
    _cleanup(app_module)
