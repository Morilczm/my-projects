"""Explicit production composition for formal document alignment processing."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from services import alignment_providers
from services import alignment_verification
from services import audit_records
from services import bilingual_evidence_workflow
from services import chinese_term_candidates
from services import concept_card_drafts
from services import document_alignment_item_preparation as preparation
from services import document_alignment_item_verification_adapter as adapter
from services import document_alignment_processing_orchestrator as orchestrator
from services import provider_governance
from services import provider_preflight
from services import provider_readiness
from services.document_alignment_item_bootstrap import (
    BootstrapDocumentAlignmentItemsCommand,
    BootstrapDocumentAlignmentItemsDependencies,
    bootstrap_document_alignment_workflow_items,
)
from services.document_alignment_term_candidates import GovernedSourceChunkSnapshot
from services.document_alignment_workflow_application import GovernedKnowledgeSourceSnapshot
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    fence_active_formal_job_lease_in_transaction,
    heartbeat_formal_background_job,
)


@dataclass(frozen=True)
class DocumentAlignmentProcessingCompositionModels:
    workflow_run: Any
    workflow_item: Any
    item_execution: Any
    background_job: Any
    audit_record: Any
    parse_record: Any
    knowledge_source: Any
    knowledge_chunk: Any
    concept_card: Any
    provider_policy: Any
    preflight_run: Any
    verification_run: Any
    provider_usage: Any


def _utc_now() -> datetime:
    return datetime.utcnow()


def _load_governed_source(session, models, source_uid):
    source = session.query(models.knowledge_source).filter_by(source_uid=source_uid).one_or_none()
    if source is None:
        return None
    parse = session.query(models.parse_record).filter_by(parse_uid=source.parse_uid).one_or_none()
    usable = session.query(models.knowledge_chunk).filter_by(
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


def _load_governed_chunks(session, models, source):
    rows = session.query(models.knowledge_chunk).filter_by(
        source_uid=source.source_uid,
        parse_uid=source.parse_uid,
        status="active",
        is_active=True,
    ).order_by(models.knowledge_chunk.chunk_index, models.knowledge_chunk.chunk_uid).all()
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


def build_document_alignment_processing_dependencies(
    *,
    session: Any,
    models: DocumentAlignmentProcessingCompositionModels,
    lease: Any,
    term_extractor: Callable[[str], Any],
    current_time_factory: Callable[[], datetime] = _utc_now,
    evaluation_context: Any = None,
) -> orchestrator.DocumentAlignmentProcessingDependencies:
    def lease_dependencies():
        return FormalBackgroundJobExecutionDependencies(
            session=session,
            job_model=models.background_job,
            current_time_factory=current_time_factory,
        )

    def bootstrap_dependencies():
        return BootstrapDocumentAlignmentItemsDependencies(
            session=session,
            workflow_run_model=models.workflow_run,
            workflow_item_model=models.workflow_item,
            background_job_model=models.background_job,
            source_loader=lambda active_session, source_uid: _load_governed_source(
                active_session, models, source_uid
            ),
            chunk_loader=lambda active_session, source: _load_governed_chunks(
                active_session, models, source
            ),
            term_extractor=term_extractor,
            current_time_factory=current_time_factory,
        )

    def preparation_dependencies():
        return preparation.DocumentAlignmentItemPreparationDependencies(
            session=session,
            models=preparation.DocumentAlignmentItemPreparationModels(
                workflow_run=models.workflow_run,
                workflow_item=models.workflow_item,
                source=models.knowledge_source,
                chunk=models.knowledge_chunk,
                concept_card=models.concept_card,
            ),
            candidate_generator=chinese_term_candidates.generate_chinese_term_candidates,
            evidence_retriever=bilingual_evidence_workflow.retrieve_bilingual_evidence,
            evaluation_context=evaluation_context,
        )

    verification_dependencies = adapter.DocumentAlignmentItemVerificationDependencies(
        session=session,
        models=adapter.DocumentAlignmentItemVerificationModels(
            workflow_run=models.workflow_run,
            workflow_item=models.workflow_item,
            execution=models.item_execution,
            concept_card=models.concept_card,
            provider_policy=models.provider_policy,
            preflight_run=models.preflight_run,
            verification_run=models.verification_run,
            provider_usage=models.provider_usage,
            audit_record=models.audit_record,
            background_job=models.background_job,
        ),
        draft=adapter.DraftVerificationCollaborator(
            create_or_reuse=lambda active_session, card_model, **kwargs: concept_card_drafts.create_or_reuse_prepared_concept_card_draft(
                active_session,
                card_model,
                chunk_model=models.knowledge_chunk,
                source_model=models.knowledge_source,
                **kwargs,
            ),
        ),
        governance=adapter.ProviderGovernanceCollaborator(
            provider_type_for=provider_governance.provider_type_for,
            evaluate_policy=provider_governance.evaluate_provider_request,
            run_preflight=provider_preflight.run_provider_preflight,
            can_attach=lambda verification, policy: provider_governance.can_attach_verification_to_card(
                verification,
                policy
                or provider_governance.builtin_local_policy(
                    getattr(verification, "provider_name", "")
                ),
            ),
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
        current_time_factory=current_time_factory,
        actor_role="teacher",
        evaluation_context=evaluation_context,
        evaluate_provider_readiness=provider_readiness.evaluate_formal_prepared_readiness,
    )

    return orchestrator.DocumentAlignmentProcessingDependencies(
        session=session,
        models=orchestrator.DocumentAlignmentProcessingModels(
            workflow_run=models.workflow_run,
            workflow_item=models.workflow_item,
            background_job=models.background_job,
            audit_record=models.audit_record,
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
                bootstrap_dependencies(),
            )
        ),
        preparation=orchestrator.ItemPreparationCollaborator(
            prepare=lambda command, item_uid: preparation.prepare_document_alignment_item(
                preparation.PrepareDocumentAlignmentItemCommand(
                    workflow_run_uid=command.workflow_run_uid,
                    workflow_item_uid=item_uid,
                ),
                preparation_dependencies(),
            ),
            validate_scope=lambda command, item_uid, prepared: preparation.validate_document_alignment_prepared_scope(
                preparation.PrepareDocumentAlignmentItemCommand(
                    workflow_run_uid=command.workflow_run_uid,
                    workflow_item_uid=item_uid,
                ),
                preparation_dependencies(),
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
                verification_dependencies,
            )
        ),
        lease=orchestrator.LeaseCollaborator(
            heartbeat=lambda command: heartbeat_formal_background_job(lease, lease_dependencies()),
            fence=lambda command: fence_active_formal_job_lease_in_transaction(
                lease, lease_dependencies()
            ),
        ),
        current_time_factory=current_time_factory,
        audit_uid_factory=lambda: uuid.uuid4().hex,
    )
