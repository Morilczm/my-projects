import uuid
from types import SimpleNamespace

from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def token_for_user(app_module, user_id):
    token_value = f"formal-route-token-{user_id}-{uuid.uuid4().hex}"
    app_module.db.session.add(
        app_module.AuthToken(
            user_id=user_id,
            token=token_value,
            token_hash=app_module.token_hash(token_value),
            created_at=app_module.current_time_text(),
            expires_at=app_module.future_time_text(60),
            revoked=False,
        )
    )
    app_module.db.session.commit()
    return token_value


def cleanup(app_module):
    app_module.db.session.rollback()
    runs = app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.source_uid.like("source-9c5f-%")
    ).all()
    run_ids = [run.id for run in runs]
    run_uids = [run.run_uid for run in runs]
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
            app_module.BackgroundJob.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            app_module.BackgroundJob.input_json.like(f'%"workflow_run_uid": "{run_uid}"%'),
        ).delete(synchronize_session=False)
    app_module.KnowledgeChunk.query.filter(
        app_module.KnowledgeChunk.source_uid.like("source-9c5f-%")
    ).delete(synchronize_session=False)
    app_module.KnowledgeSource.query.filter(
        app_module.KnowledgeSource.source_uid.like("source-9c5f-%")
    ).delete(synchronize_session=False)
    app_module.DocumentParseRecord.query.filter(
        app_module.DocumentParseRecord.parse_uid.like("parse-9c5f-%")
    ).delete(synchronize_session=False)
    app_module.db.session.commit()


def create_governed_source(
    app_module,
    *,
    owner_user_id=None,
    source_uid=None,
    parse_status="success",
    quality_status="native_text_ok",
    trust_level="teacher_verified",
    source_status="active",
    chunk_count=2,
):
    suffix = uuid.uuid4().hex[:10]
    source_uid = source_uid or f"source-9c5f-{suffix}"
    parse_uid = f"parse-9c5f-{suffix}"
    teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").one()
    course = app_module.Course.query.filter_by(name="OCR Test Course").one()
    owner_user_id = owner_user_id or teacher.id
    app_module.db.session.add(
        app_module.DocumentParseRecord(
            parse_uid=parse_uid,
            source_filename="formal-route-source.txt",
            parse_status=parse_status,
            quality_status=quality_status,
            block_count=max(1, chunk_count),
            extracted_text_chars=128,
        )
    )
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        source_type="teacher_upload",
        title="Formal route source",
        course_id=course.id,
        course=course.name,
        chapter="Frequency Domain",
        language="en",
        visibility="course",
        trust_level=trust_level,
        status=source_status,
        owner_user_id=owner_user_id,
        parse_uid=parse_uid,
        version="1",
        quality_status=quality_status,
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    for index in range(chunk_count):
        app_module.db.session.add(
            app_module.KnowledgeChunk(
                chunk_uid=f"chunk-9c5f-{suffix}-{index}",
                document_id=0,
                knowledge_source_id=source.id,
                source_uid=source_uid,
                parse_uid=parse_uid,
                chunk_index=index,
                content=f"Governed evidence chunk {index}",
                language="en",
                course=course.name,
                chapter="Frequency Domain",
                status="active",
                is_active=True,
                quality_status=quality_status,
                trust_level=trust_level,
            )
        )
    app_module.db.session.commit()
    return SimpleNamespace(source_uid=source_uid, parse_uid=parse_uid)


def workflow_counts(app_module):
    return {
        "runs": app_module.DocumentAlignmentWorkflowRun.query.count(),
        "jobs": app_module.BackgroundJob.query.filter_by(
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
        ).count(),
        "audits": app_module.AuditRecord.query.filter_by(
            event_type="document_alignment_requested"
        ).count(),
    }
