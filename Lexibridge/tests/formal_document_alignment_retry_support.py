from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func

from document_alignment_workflow_route_support import bearer
from services.document_alignment_processing_composition import (
    build_document_alignment_processing_dependencies,
)
from services.document_alignment_processing_orchestrator import (
    ProcessDocumentAlignmentWorkflowCommand,
    ProcessDocumentAlignmentWorkflowResult,
    process_document_alignment_workflow,
)
from services.document_alignment_worker_handler import (
    run_claimed_formal_document_alignment_job,
)
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
)


PREFIX = "formal-retry-budget-9c5f2"


def start_http_run(client, app_module, teacher_token, *, key="retry-contract"):
    source = create_retry_source(app_module)
    response = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source.source_uid},
        headers={
            **bearer(teacher_token),
            "Idempotency-Key": f"{PREFIX}-{key}",
            "X-Request-ID": f"{PREFIX}-{key}-request",
        },
    )
    assert response.status_code == 202, response.get_data(as_text=True)
    run_uid = response.get_json()["data"]["run_uid"]
    job = app_module.BackgroundJob.query.filter(
        app_module.BackgroundJob.input_json.like(f"%{run_uid}%")
    ).one()
    minimum_priority = app_module.db.session.query(
        func.min(app_module.BackgroundJob.priority)
    ).filter(
        app_module.BackgroundJob.job_type == "formal_document_alignment_workflow_v1"
    ).scalar()
    job.priority = min(int(job.priority or 100), int(minimum_priority or 0) - 1)
    app_module.db.session.commit()
    return response, run_uid, job.job_uid


def create_retry_source(app_module):
    suffix = uuid.uuid4().hex[:12]
    course = app_module.Course.query.filter_by(name="OCR Test Course").one()
    teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").one()
    parse_en = app_module.DocumentParseRecord(
        parse_uid=f"{PREFIX}-parse-{suffix}-en",
        source_filename="formal-retry-en.txt",
        parse_status="success",
        quality_status="native_text_ok",
        block_count=2,
        extracted_text_chars=64,
    )
    parse_zh = app_module.DocumentParseRecord(
        parse_uid=f"{PREFIX}-parse-{suffix}-zh",
        source_filename="formal-retry-zh.txt",
        parse_status="success",
        quality_status="native_text_ok",
        block_count=2,
        extracted_text_chars=64,
    )
    source_en = app_module.KnowledgeSource(
        source_uid=f"{PREFIX}-source-{suffix}-en",
        title="Formal retry English source",
        name="Formal retry English source",
        course_id=course.id,
        course=course.name,
        chapter="Frequency",
        owner_user_id=teacher.id,
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
        source_uid=f"{PREFIX}-source-{suffix}-zh",
        title="Formal retry bilingual source",
        name="Formal retry bilingual source",
        course_id=course.id,
        course=course.name,
        chapter="Frequency",
        owner_user_id=teacher.id,
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
    terms = (("Fourier Transform", "傅里叶变换"), ("Laplace Transform", "拉普拉斯变换"))
    for index, (english, chinese) in enumerate(terms):
        app_module.db.session.add_all([
            app_module.KnowledgeChunk(
                chunk_uid=f"{PREFIX}-chunk-{suffix}-en-{index}",
                source_uid=source_en.source_uid,
                knowledge_source_id=source_en.id,
                document_id=0,
                parse_uid=parse_en.parse_uid,
                course=course.name,
                chapter="Frequency",
                chunk_index=index,
                content=english,
                language="en",
                visibility="course",
                status="active",
                is_active=True,
                quality_status="native_text_ok",
                trust_level="teacher_verified",
            ),
            app_module.KnowledgeChunk(
                chunk_uid=f"{PREFIX}-chunk-{suffix}-zh-{index}",
                source_uid=source_zh.source_uid,
                knowledge_source_id=source_zh.id,
                document_id=0,
                parse_uid=parse_zh.parse_uid,
                course=course.name,
                chapter="Frequency",
                chunk_index=index,
                content=f"{chinese}（{english}）用于课程概念分析。",
                language="mixed",
                visibility="course",
                status="active",
                is_active=True,
                quality_status="native_text_ok",
                trust_level="teacher_verified",
            ),
        ])
    app_module.db.session.commit()
    return source_en


def cleanup_retry_state(app_module):
    session = app_module.db.session
    session.rollback()
    runs = app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.source_uid.like(f"{PREFIX}%")
    ).all()
    run_ids = [run.id for run in runs]
    run_uids = [run.run_uid for run in runs]
    items = (
        app_module.DocumentAlignmentWorkflowItem.query.filter(
            app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(run_ids)
        ).all()
        if run_ids else []
    )
    item_uids = [item.item_uid for item in items]
    mappings = (
        app_module.DocumentAlignmentItemVerificationExecution.query.filter(
            app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.in_(run_uids)
        ).all()
        if run_uids else []
    )
    execution_keys = [mapping.execution_key for mapping in mappings]
    card_uids = [mapping.draft_card_uid for mapping in mappings if mapping.draft_card_uid]
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
    if run_uids or item_uids:
        app_module.AuditRecord.query.filter(
            app_module.AuditRecord.target_uid.in_(run_uids + item_uids)
        ).delete(synchronize_session=False)
    if run_uids:
        app_module.DocumentAlignmentItemVerificationExecution.query.filter(
            app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.in_(run_uids)
        ).delete(synchronize_session=False)
    if run_ids:
        app_module.DocumentAlignmentWorkflowItem.query.filter(
            app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(run_ids)
        ).delete(synchronize_session=False)
        app_module.DocumentAlignmentWorkflowRun.query.filter(
            app_module.DocumentAlignmentWorkflowRun.id.in_(run_ids)
        ).delete(synchronize_session=False)
    if card_uids:
        app_module.ConceptAlignmentCard.query.filter(
            app_module.ConceptAlignmentCard.card_uid.in_(card_uids)
        ).delete(synchronize_session=False)
    for run_uid in run_uids:
        app_module.BackgroundJob.query.filter(
            app_module.BackgroundJob.input_json.like(f"%{run_uid}%")
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
    session.commit()
    session.expunge_all()


def claim(app_module, worker_id, *, expected_job_uid=None, now=None, token=None):
    dependencies = FormalBackgroundJobExecutionDependencies(
        session=app_module.db.session,
        job_model=app_module.BackgroundJob,
        current_time_factory=lambda: now or datetime.utcnow(),
        lease_token_factory=lambda: token or f"{PREFIX}-{worker_id}-lease",
    )
    result = claim_next_formal_background_job(worker_id, dependencies)
    assert result.lease is not None, result
    if expected_job_uid is not None:
        assert result.lease.job_uid == expected_job_uid
    return result.lease


def reclaim_after_expiry(app_module, lease, worker_id):
    return claim(
        app_module,
        worker_id,
        expected_job_uid=lease.job_uid,
        now=lease.lease_expires_at + timedelta(seconds=1),
        token=f"{PREFIX}-{worker_id}-replacement-lease",
    )


def run_claimed_with_retryable_verification(app_module, lease, *, complete_first=0):
    processing_dependencies = build_document_alignment_processing_dependencies(
        session=app_module.db.session,
        models=app_module._formal_processing_composition_models(),
        lease=lease,
        term_extractor=app_module.extract_terms_from_text,
        current_time_factory=datetime.utcnow,
    )
    real_execute = processing_dependencies.verification.execute
    completed = {"count": 0}

    def execute(command, item_uid, prepared):
        if completed["count"] < complete_first:
            result = real_execute(command, item_uid, prepared)
            completed["count"] += 1
            return result
        return SimpleNamespace(
            outcome="persistence_error",
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
            error_message="Safe test-only retryable interruption.",
        )

    processing_dependencies = replace(
        processing_dependencies,
        verification=replace(processing_dependencies.verification, execute=execute),
    )
    handler_dependencies = app_module._formal_worker_handler_dependencies(lease)
    handler_dependencies = replace(
        handler_dependencies,
        processing=replace(
            handler_dependencies.processing,
            execute=lambda command: process_document_alignment_workflow(
                command,
                processing_dependencies,
            ),
        ),
    )
    return run_claimed_formal_document_alignment_job(lease, handler_dependencies)


def process_until_first_item_then_crash(app_module, lease):
    processing_dependencies = build_document_alignment_processing_dependencies(
        session=app_module.db.session,
        models=app_module._formal_processing_composition_models(),
        lease=lease,
        term_extractor=app_module.extract_terms_from_text,
        current_time_factory=datetime.utcnow,
    )
    real_execute = processing_dependencies.verification.execute
    completed = {"count": 0}

    def execute(command, item_uid, prepared):
        if completed["count"]:
            raise RuntimeError("test-only crash after first completed item")
        result = real_execute(command, item_uid, prepared)
        completed["count"] += 1
        return result

    processing_dependencies = replace(
        processing_dependencies,
        verification=replace(processing_dependencies.verification, execute=execute),
    )
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    run_uid = json.loads(job.input_json)["workflow_run_uid"]
    command = ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )
    return process_document_alignment_workflow(command, processing_dependencies)


def retryable_result(run_uid, job_uid):
    return ProcessDocumentAlignmentWorkflowResult(
        outcome="retryable_interruption",
        workflow_run_uid=run_uid,
        job_uid=job_uid,
        run_status="processing",
        run_stage="verification",
        retryable=True,
        error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
        error_message="Safe retryable interruption.",
    )


def logical_counts(app_module, run_uid):
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    mappings = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
        workflow_run_uid=run_uid
    ).all()
    keys = [mapping.execution_key for mapping in mappings]
    items = app_module.DocumentAlignmentWorkflowItem.query.filter_by(
        workflow_run_id=run.id
    ).all()
    return {
        "items": len(items),
        "needs_review": sum(item.status == "needs_review" for item in items),
        "preflights": app_module.AlignmentProviderPreflightRun.query.filter(
            app_module.AlignmentProviderPreflightRun.execution_key.in_(keys)
        ).count() if keys else 0,
        "verifications": app_module.AlignmentVerificationRun.query.filter(
            app_module.AlignmentVerificationRun.execution_key.in_(keys)
        ).count() if keys else 0,
        "usage": app_module.AlignmentProviderUsageRecord.query.filter(
            app_module.AlignmentProviderUsageRecord.execution_key.in_(keys)
        ).count() if keys else 0,
        "failed_audits": app_module.AuditRecord.query.filter_by(
            target_uid=run_uid,
            event_type="document_alignment_failed",
        ).count(),
    }
