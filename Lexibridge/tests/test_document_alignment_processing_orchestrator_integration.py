import json
import itertools
import dataclasses
from datetime import datetime, timedelta

import pytest

from services import bilingual_evidence_workflow
from services import chinese_term_candidates
from services import alignment_providers
from services import alignment_verification
from services import audit_records
from services import concept_card_drafts
from services import document_alignment_item_verification_adapter as adapter
from services import document_alignment_item_preparation as preparation
from services import document_alignment_processing_orchestrator as orchestrator
from services import provider_governance
from services import provider_preflight
from services.document_alignment_item_bootstrap import (
    BOOTSTRAP_OUTCOME_CREATED,
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
    fence_active_formal_job_lease_in_transaction,
    heartbeat_formal_background_job,
)


PREFIX = "processing-orchestrator-9c5c"
NOW = datetime(2026, 7, 18, 16, 0, 0)
PROVIDER = "external-llm-replay-v1"


@pytest.fixture(autouse=True)
def _app_context(app_module):
    with app_module.app.app_context():
        yield


def _cleanup(app_module):
    app_module.db.session.rollback()
    mappings = app_module.DocumentAlignmentItemVerificationExecution.query.filter(
        app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.like(f"{PREFIX}%")
    ).all()
    execution_keys = [row.execution_key for row in mappings]
    card_uids = [row.draft_card_uid for row in mappings if row.draft_card_uid]
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
    app_module.AuditRecord.query.filter(
        app_module.AuditRecord.target_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentAlignmentItemVerificationExecution.query.filter(
        app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowItem.query.filter(
        app_module.DocumentAlignmentWorkflowItem.item_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    if card_uids:
        app_module.ConceptAlignmentCard.query.filter(
            app_module.ConceptAlignmentCard.card_uid.in_(card_uids)
        ).delete(synchronize_session=False)
    app_module.ConceptAlignmentCard.query.filter(
        app_module.ConceptAlignmentCard.english_term.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter(
        app_module.BackgroundJob.input_json.like(f"%{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.AlignmentProviderPolicy.query.filter_by(provider_name=PROVIDER).delete(
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


def _formal_counts_for_run(app_module, run_uid):
    mappings = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
        workflow_run_uid=run_uid
    ).all()
    execution_keys = [row.execution_key for row in mappings]
    card_uids = [row.draft_card_uid for row in mappings if row.draft_card_uid]
    return {
        "mappings": len(mappings),
        "cards": (
            app_module.ConceptAlignmentCard.query.filter(
                app_module.ConceptAlignmentCard.card_uid.in_(card_uids)
            ).count()
            if card_uids else 0
        ),
        "preflights": (
            app_module.AlignmentProviderPreflightRun.query.filter(
                app_module.AlignmentProviderPreflightRun.execution_key.in_(execution_keys)
            ).count()
            if execution_keys else 0
        ),
        "verifications": (
            app_module.AlignmentVerificationRun.query.filter(
                app_module.AlignmentVerificationRun.execution_key.in_(execution_keys)
            ).count()
            if execution_keys else 0
        ),
        "usage": (
            app_module.AlignmentProviderUsageRecord.query.filter(
                app_module.AlignmentProviderUsageRecord.execution_key.in_(execution_keys)
            ).count()
            if execution_keys else 0
        ),
    }


def _source_loader(app_module):
    def load(session, source_uid):
        source = session.query(app_module.KnowledgeSource).filter_by(source_uid=source_uid).one_or_none()
        if source is None:
            return None
        parse = session.query(app_module.DocumentParseRecord).filter_by(parse_uid=source.parse_uid).one_or_none()
        usable = session.query(app_module.KnowledgeChunk).filter_by(
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
            usable_chunk_count=usable,
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


def _safe_policy(app_module, course):
    provider_governance.create_or_update_provider_policy(
        app_module.db.session,
        app_module.AlignmentProviderPolicy,
        PROVIDER,
        {
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_external_calls": False,
            "allow_attach_to_card": True,
            "allow_production_result": False,
            "allow_auto_approve": False,
            "require_human_review": True,
            "allowed_courses": [course],
            "allowed_roles": ["teacher", "admin"],
            "max_calls_per_day": 10,
            "max_calls_per_month": 100,
            "max_estimated_cost_per_call": 0.25,
            "max_estimated_cost_per_day": 1.0,
            "max_prompt_chars": 8000,
            "max_output_chars": 4000,
            "timeout_seconds": 30,
            "max_retries": 0,
        },
        now_fn=app_module.current_time_text,
        commit=True,
    )


def _setup_governed_workflow(
    app_module,
    suffix="prepared",
    *,
    bootstrap=True,
    terms=("Fourier Transform",),
    bilingual_terms=None,
):
    _cleanup(app_module)
    course = f"{PREFIX}-course-{suffix}"
    chapter = "Frequency"
    source_uid = f"{PREFIX}-source-en-{suffix}"
    bilingual_source_uid = f"{PREFIX}-source-bilingual-{suffix}"
    parse_uid = f"{PREFIX}-parse-en-{suffix}"
    bilingual_parse_uid = f"{PREFIX}-parse-bilingual-{suffix}"
    run_uid = f"{PREFIX}-run-{suffix}"
    parses = [
        app_module.DocumentParseRecord(
            parse_uid=parse_uid,
            source_filename="formal-source.txt",
            parse_status="success",
            quality_status="native_text_ok",
            block_count=1,
            extracted_text_chars=128,
        ),
        app_module.DocumentParseRecord(
            parse_uid=bilingual_parse_uid,
            source_filename="formal-bilingual-source.txt",
            parse_status="success",
            quality_status="native_text_ok",
            block_count=1,
            extracted_text_chars=128,
        ),
    ]
    english_source = app_module.KnowledgeSource(
        source_uid=source_uid,
        title="Formal English source",
        name="Formal English source",
        course=course,
        chapter=chapter,
        owner_user_id=1,
        visibility="course",
        language="en",
        source_type="course_material",
        source_role="english_course_material",
        trust_level="teacher_verified",
        parse_uid=parse_uid,
        version=1,
        quality_status="native_text_ok",
        status="active",
        allow_derivative_cards=True,
    )
    bilingual_source = app_module.KnowledgeSource(
        source_uid=bilingual_source_uid,
        title="Formal bilingual source",
        name="Formal bilingual source",
        course=course,
        chapter=chapter,
        owner_user_id=1,
        visibility="course",
        language="mixed",
        source_type="reference",
        source_role="bilingual_reference",
        trust_level="teacher_verified",
        parse_uid=bilingual_parse_uid,
        version=1,
        quality_status="native_text_ok",
        status="active",
        allow_derivative_cards=True,
    )
    app_module.db.session.add_all([*parses, english_source, bilingual_source])
    app_module.db.session.flush()
    bilingual_terms = {"Fourier Transform": "傅里叶变换"} if bilingual_terms is None else dict(bilingual_terms)
    chunks = [
        *[
        app_module.KnowledgeChunk(
            chunk_uid=(
                f"{PREFIX}-chunk-en-{suffix}"
                if len(terms) == 1
                else f"{PREFIX}-chunk-en-{suffix}-{index}"
            ),
            source_uid=source_uid,
            knowledge_source_id=english_source.id,
            document_id=0,
            parse_uid=parse_uid,
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
        for index, term in enumerate(terms)
        ],
        *[
        app_module.KnowledgeChunk(
            chunk_uid=(
                f"{PREFIX}-chunk-zh-{suffix}"
                if len(bilingual_terms) == 1
                else f"{PREFIX}-chunk-zh-{suffix}-{index}"
            ),
            source_uid=bilingual_source_uid,
            knowledge_source_id=bilingual_source.id,
            document_id=0,
            parse_uid=bilingual_parse_uid,
            course=course,
            chapter=chapter,
            chunk_index=index,
            content=f"{chinese_term}（{english_term}）用于课程概念分析。",
            language="mixed",
            status="active",
            is_active=True,
            quality_status="native_text_ok",
            trust_level="teacher_verified",
            visibility="course",
        )
        for index, (english_term, chinese_term) in enumerate(sorted(bilingual_terms.items()))
        ],
    ]
    run = app_module.DocumentAlignmentWorkflowRun(
        run_uid=run_uid,
        source_uid=source_uid,
        parse_uid=parse_uid,
        source_version="1",
        course=course,
        chapter=chapter,
        requested_by="1",
        request_id=f"{PREFIX}-request-{suffix}",
        idempotency_key=f"{PREFIX}-idempotency-{suffix}",
        idempotency_fingerprint=f"{PREFIX}-fingerprint-{suffix}",
        workflow_version=WORKFLOW_VERSION_V1,
        retrieval_version="governed-bilingual-v1",
        prompt_version="alignment-verification-v1",
        provider_preference=PROVIDER,
        model_preference="replay-llm:v1",
        status=ROOT_STATUS_QUEUED,
        stage=ROOT_STAGE_QUEUED,
        created_at="2026-07-18 15:59:00",
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
        created_at="2026-07-18 15:59:00",
        updated_at="2026-07-18 15:59:00",
    )
    app_module.db.session.add_all([*chunks, run, job])
    app_module.db.session.commit()
    _safe_policy(app_module, course)
    lease = claim_next_formal_background_job(
        f"{PREFIX}-worker-{suffix}",
        FormalBackgroundJobExecutionDependencies(
            session=app_module.db.session,
            job_model=app_module.BackgroundJob,
            current_time_factory=lambda: NOW,
            lease_token_factory=lambda: f"{PREFIX}-lease-{suffix}",
        ),
    ).lease
    if not bootstrap:
        return run_uid, lease
    bootstrap_result = bootstrap_document_alignment_workflow_items(
        BootstrapDocumentAlignmentItemsCommand(
            workflow_run_uid=run_uid,
            job_uid=lease.job_uid,
            worker_id=lease.worker_id,
            execution_attempt=lease.execution_attempt,
            lease_token=lease.lease_token,
        ),
        _bootstrap_dependencies(app_module, app_module.db.session, suffix),
    )
    assert bootstrap_result.outcome == BOOTSTRAP_OUTCOME_CREATED
    return run_uid, lease


def _bootstrap_dependencies(app_module, session, suffix):
    item_counter = itertools.count()
    return BootstrapDocumentAlignmentItemsDependencies(
        session=session,
        workflow_run_model=app_module.DocumentAlignmentWorkflowRun,
        workflow_item_model=app_module.DocumentAlignmentWorkflowItem,
        background_job_model=app_module.BackgroundJob,
        source_loader=_source_loader(app_module),
        chunk_loader=_chunk_loader(app_module),
        term_extractor=lambda text: [{"english_term": text}],
        item_uid_factory=lambda: f"{PREFIX}-item-{suffix}-{next(item_counter)}",
        current_time_factory=lambda: NOW + timedelta(seconds=2),
    )


def _preparation_dependencies(app_module, session):
    return preparation.DocumentAlignmentItemPreparationDependencies(
        session=session,
        models=preparation.DocumentAlignmentItemPreparationModels(
            workflow_run=app_module.DocumentAlignmentWorkflowRun,
            workflow_item=app_module.DocumentAlignmentWorkflowItem,
            source=app_module.KnowledgeSource,
            chunk=app_module.KnowledgeChunk,
            concept_card=app_module.ConceptAlignmentCard,
        ),
        candidate_generator=chinese_term_candidates.generate_chinese_term_candidates,
        evidence_retriever=bilingual_evidence_workflow.retrieve_bilingual_evidence,
    )


def _verification_dependencies(app_module, session):
    return adapter.DocumentAlignmentItemVerificationDependencies(
        session=session,
        models=adapter.DocumentAlignmentItemVerificationModels(
            workflow_run=app_module.DocumentAlignmentWorkflowRun,
            workflow_item=app_module.DocumentAlignmentWorkflowItem,
            execution=app_module.DocumentAlignmentItemVerificationExecution,
            concept_card=app_module.ConceptAlignmentCard,
            provider_policy=app_module.AlignmentProviderPolicy,
            preflight_run=app_module.AlignmentProviderPreflightRun,
            verification_run=app_module.AlignmentVerificationRun,
            provider_usage=app_module.AlignmentProviderUsageRecord,
            audit_record=app_module.AuditRecord,
            background_job=app_module.BackgroundJob,
        ),
        draft=adapter.DraftVerificationCollaborator(
            create_or_reuse=concept_card_drafts.create_or_reuse_prepared_concept_card_draft,
        ),
        governance=adapter.ProviderGovernanceCollaborator(
            provider_type_for=provider_governance.provider_type_for,
            evaluate_policy=provider_governance.evaluate_provider_request,
            run_preflight=provider_preflight.run_provider_preflight,
            can_attach=provider_governance.can_attach_verification_to_card,
        ),
        verification=adapter.VerificationCollaborator(
            resolve_provider=alignment_providers.get_alignment_provider,
            validate_input=alignment_verification.validate_alignment_verification_input,
            create_safe_run=alignment_verification.create_safe_alignment_verification_run,
            attach=alignment_verification.apply_verification_result_to_card_protected,
        ),
        recording=adapter.RecordingCollaborator(
            record_usage=provider_governance.record_provider_usage,
            create_audit=audit_records.create_audit_record,
        ),
        fence_active_lease=fence_active_formal_job_lease_in_transaction,
        current_time_factory=lambda: NOW + timedelta(seconds=3),
        actor_role="teacher",
    )


def _orchestrator_dependencies(app_module, session, lease, suffix):
    lease_dependencies = lambda: FormalBackgroundJobExecutionDependencies(
        session=session,
        job_model=app_module.BackgroundJob,
        current_time_factory=lambda: NOW + timedelta(seconds=4),
    )
    return orchestrator.DocumentAlignmentProcessingDependencies(
        session=session,
        models=orchestrator.DocumentAlignmentProcessingModels(
            workflow_run=app_module.DocumentAlignmentWorkflowRun,
            workflow_item=app_module.DocumentAlignmentWorkflowItem,
            background_job=app_module.BackgroundJob,
            audit_record=app_module.AuditRecord,
        ),
        bootstrap=orchestrator.WorkflowBootstrapCollaborator(
            execute=lambda command: bootstrap_document_alignment_workflow_items(
                BootstrapDocumentAlignmentItemsCommand(
                    workflow_run_uid=command.workflow_run_uid,
                    job_uid=command.job_uid,
                    worker_id=command.worker_id,
                    execution_attempt=command.execution_attempt,
                    lease_token=command.lease_token,
                ),
                _bootstrap_dependencies(app_module, session, suffix),
            )
        ),
        preparation=orchestrator.ItemPreparationCollaborator(
            prepare=lambda command, item_uid: preparation.prepare_document_alignment_item(
                preparation.PrepareDocumentAlignmentItemCommand(
                    workflow_run_uid=command.workflow_run_uid,
                    workflow_item_uid=item_uid,
                ),
                _preparation_dependencies(app_module, session),
            ),
            validate_scope=lambda command, item_uid, prepared: preparation.validate_document_alignment_prepared_scope(
                preparation.PrepareDocumentAlignmentItemCommand(
                    workflow_run_uid=command.workflow_run_uid,
                    workflow_item_uid=item_uid,
                ),
                _preparation_dependencies(app_module, session),
                prepared,
            ),
        ),
        verification=orchestrator.ItemVerificationCollaborator(
            execute=lambda command, item_uid, prepared: adapter.execute_document_alignment_item_verification(
                adapter.ExecuteDocumentAlignmentItemVerificationCommand(
                    workflow_run_uid=command.workflow_run_uid,
                    workflow_item_uid=item_uid,
                    job_uid=command.job_uid,
                    worker_id=command.worker_id,
                    execution_attempt=command.execution_attempt,
                    lease_token=command.lease_token,
                    prepared_input=prepared,
                ),
                _verification_dependencies(app_module, session),
            )
        ),
        lease=orchestrator.LeaseCollaborator(
            heartbeat=lambda command: heartbeat_formal_background_job(lease, lease_dependencies()),
            fence=lambda command: fence_active_formal_job_lease_in_transaction(lease, lease_dependencies()),
        ),
        current_time_factory=lambda: NOW + timedelta(seconds=5),
        audit_uid_factory=lambda: f"{PREFIX}-audit-{suffix}",
    )


def test_real_item_preparation_composes_governed_candidate_and_bilingual_evidence(app_module):
    run_uid, _ = _setup_governed_workflow(app_module)
    item = app_module.DocumentAlignmentWorkflowItem.query.one()
    result = preparation.prepare_document_alignment_item(
        preparation.PrepareDocumentAlignmentItemCommand(
            workflow_run_uid=run_uid,
            workflow_item_uid=item.item_uid,
        ),
        preparation.DocumentAlignmentItemPreparationDependencies(
            session=app_module.db.session,
            models=preparation.DocumentAlignmentItemPreparationModels(
                workflow_run=app_module.DocumentAlignmentWorkflowRun,
                workflow_item=app_module.DocumentAlignmentWorkflowItem,
                source=app_module.KnowledgeSource,
                chunk=app_module.KnowledgeChunk,
                concept_card=app_module.ConceptAlignmentCard,
            ),
            candidate_generator=chinese_term_candidates.generate_chinese_term_candidates,
            evidence_retriever=bilingual_evidence_workflow.retrieve_bilingual_evidence,
        ),
    )

    assert result.outcome == preparation.PREPARATION_OUTCOME_PREPARED
    assert result.prepared_input.english_term == "Fourier Transform"
    assert result.prepared_input.chinese_candidate_values == ("傅里叶变换",)
    assert result.prepared_input.english_evidence_refs == (f"{PREFIX}-chunk-en-prepared",)
    assert result.prepared_input.chinese_evidence_refs == (f"{PREFIX}-chunk-zh-prepared",)
    assert result.prepared_input.english_snippets
    assert result.prepared_input.chinese_snippets
    assert app_module.DocumentAlignmentWorkflowItem.query.one().status == "candidate"
    _cleanup(app_module)


def test_real_orchestrator_composes_all_formal_stages_and_finalizes_root_only(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "complete", bootstrap=False)
    command = orchestrator.ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )

    result = orchestrator.process_document_alignment_workflow(
        command,
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "complete"),
    )

    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    item = app_module.DocumentAlignmentWorkflowItem.query.one()
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    assert result.outcome == "ready_for_review"
    assert run.status == "ready_for_review"
    assert run.stage == "terminal"
    assert run.total_items == 1
    assert run.ready_for_review_items == 1
    assert item.status == "needs_review"
    assert item.draft_card_uid
    assert item.verification_run_uid
    assert job.status == "running"
    assert _formal_counts_for_run(app_module, run_uid) == {
        "mappings": 1,
        "cards": 1,
        "preflights": 1,
        "verifications": 1,
        "usage": 1,
    }
    root_events = app_module.AuditRecord.query.filter_by(target_uid=run_uid).all()
    assert {event.event_type for event in root_events} == {
        "document_alignment_processing_started",
        "document_alignment_ready_for_review",
    }
    _cleanup(app_module)


def _processing_command(run_uid, lease):
    return orchestrator.ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )


def test_orchestrator_rejects_job_payload_mismatch_without_bootstrap(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "job-mismatch", bootstrap=False)
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    job.input_json = json.dumps(
        {
            "workflow_run_uid": "another-run",
            "workflow_version": WORKFLOW_VERSION_V1,
        }
    )
    app_module.db.session.commit()

    result = orchestrator.process_document_alignment_workflow(
        _processing_command(run_uid, lease),
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "job-mismatch"),
    )
    assert result.outcome == "invalid_run_state"
    assert result.error_code == "DOCUMENT_ALIGNMENT_JOB_MISMATCH"
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).count() == 0
    _cleanup(app_module)


def test_orchestrator_rejects_reclaimed_attempt_before_business_write(app_module):
    run_uid, old_lease = _setup_governed_workflow(app_module, "stale-root", bootstrap=False)
    job = app_module.BackgroundJob.query.filter_by(job_uid=old_lease.job_uid).one()
    job.execution_attempt = old_lease.execution_attempt + 1
    job.locked_by = f"{PREFIX}-worker-stale-root-replacement"
    job.lease_token = f"{PREFIX}-lease-stale-root-replacement"
    job.lease_expires_at = "2026-07-18 16:01:00"
    app_module.db.session.commit()

    result = orchestrator.process_document_alignment_workflow(
        _processing_command(run_uid, old_lease),
        _orchestrator_dependencies(app_module, app_module.db.session, old_lease, "stale-root"),
    )
    assert result.outcome == "stale_attempt"
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).count() == 0
    assert app_module.AuditRecord.query.filter_by(target_uid=run_uid).count() == 0
    _cleanup(app_module)


def test_orchestrator_rejects_unknown_root_state_without_processing(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "invalid-state", bootstrap=False)
    app_module.db.session.execute(
        app_module.DocumentAlignmentWorkflowRun.__table__.update()
        .where(app_module.DocumentAlignmentWorkflowRun.run_uid == run_uid)
        .values(status="unsupported_state")
    )
    app_module.db.session.commit()

    result = orchestrator.process_document_alignment_workflow(
        _processing_command(run_uid, lease),
        _orchestrator_dependencies(app_module, app_module.db.session, lease, "invalid-state"),
    )
    assert result.outcome == "invalid_run_state"
    assert result.error_code == "DOCUMENT_ALIGNMENT_INVALID_RUN_STATE"
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).count() == 0
    _cleanup(app_module)


def test_item_iteration_is_stable_and_heartbeat_covers_each_boundary(app_module):
    run_uid, lease = _setup_governed_workflow(
        app_module,
        "stable-order",
        bootstrap=False,
        terms=("Laplace Transform", "Fourier Transform"),
        bilingual_terms={
            "Fourier Transform": "傅里叶变换",
            "Laplace Transform": "拉普拉斯变换",
        },
    )
    dependencies = _orchestrator_dependencies(
        app_module,
        app_module.db.session,
        lease,
        "stable-order",
    )
    real_verify = dependencies.verification.execute
    real_heartbeat = dependencies.lease.heartbeat
    visited = []
    heartbeat_calls = []

    def record_verify(command, item_uid, prepared):
        visited.append(item_uid)
        return real_verify(command, item_uid, prepared)

    def record_heartbeat(command):
        heartbeat_calls.append(command.workflow_run_uid)
        return real_heartbeat(command)

    result = orchestrator.process_document_alignment_workflow(
        _processing_command(run_uid, lease),
        dataclasses.replace(
            dependencies,
            verification=dataclasses.replace(dependencies.verification, execute=record_verify),
            lease=dataclasses.replace(dependencies.lease, heartbeat=record_heartbeat),
        ),
    )
    expected = [
        item.item_uid
        for item in app_module.DocumentAlignmentWorkflowItem.query.order_by(
            app_module.DocumentAlignmentWorkflowItem.id,
            app_module.DocumentAlignmentWorkflowItem.item_key,
        ).all()
    ]
    assert result.outcome == "ready_for_review"
    assert visited == expected
    assert len(heartbeat_calls) == 3 + (3 * len(expected)) + 1
    assert app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one().status == "running"
    _cleanup(app_module)
