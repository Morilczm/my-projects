import dataclasses
import json
import uuid
from datetime import datetime, timedelta

import pytest

from services import alignment_providers
from services import alignment_verification
from services import audit_records
from services import concept_card_drafts
from services import document_alignment_item_verification_adapter as adapter
from services import provider_governance
from services import provider_preflight
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ITEM_STAGE_EVIDENCE_RETRIEVAL,
    ITEM_STATUS_EVIDENCE_READY,
    ROOT_STAGE_VERIFICATION,
    ROOT_STATUS_PROCESSING,
    WORKFLOW_VERSION_V1,
)
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
    fence_active_formal_job_lease_in_transaction,
)


PREFIX = "item-verification-adapter-9c5b-v2"
NOW = datetime(2026, 7, 18, 14, 0, 0)
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
    app_module.ConceptAlignmentCard.query.filter(
        app_module.ConceptAlignmentCard.english_term.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    if card_uids:
        app_module.ConceptAlignmentCard.query.filter(
            app_module.ConceptAlignmentCard.card_uid.in_(card_uids)
        ).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter(
        app_module.BackgroundJob.input_json.like(f"%{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.AlignmentProviderPolicy.query.filter_by(provider_name=PROVIDER).delete(
        synchronize_session=False
    )
    app_module.db.session.commit()
    app_module.db.session.expunge_all()


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


def _setup(app_module, suffix="success"):
    _cleanup(app_module)
    run_uid = f"{PREFIX}-run-{suffix}"
    item_uid = f"{PREFIX}-item-{suffix}"
    course = f"{PREFIX}-course-{suffix}"
    run = app_module.DocumentAlignmentWorkflowRun(
        run_uid=run_uid,
        source_uid=f"{PREFIX}-source-{suffix}",
        parse_uid=f"{PREFIX}-parse-{suffix}",
        source_version="1",
        course=course,
        chapter="Frequency",
        requested_by="1",
        request_id=f"{PREFIX}-request-{suffix}",
        idempotency_key=f"{PREFIX}-idempotency-{suffix}",
        idempotency_fingerprint=f"{PREFIX}-fingerprint-{suffix}",
        workflow_version=WORKFLOW_VERSION_V1,
        retrieval_version="governed-bilingual-v1",
        prompt_version="alignment-verification-v1",
        provider_preference=PROVIDER,
        status=ROOT_STATUS_PROCESSING,
        stage=ROOT_STAGE_VERIFICATION,
    )
    app_module.db.session.add(run)
    app_module.db.session.flush()
    item = app_module.DocumentAlignmentWorkflowItem(
        item_uid=item_uid,
        workflow_run_id=run.id,
        item_key=f"item-key-v1:{suffix}",
        candidate_term=f"{PREFIX} Fourier transform {suffix}",
        normalized_term=f"{PREFIX} fourier transform {suffix}",
        source_chunk_refs=json.dumps([f"{PREFIX}-chunk-en-{suffix}"]),
        english_evidence_refs=json.dumps([f"{PREFIX}-chunk-en-{suffix}"]),
        chinese_evidence_refs=json.dumps([f"{PREFIX}-chunk-zh-{suffix}"]),
        chinese_candidate_summary=json.dumps(
            {
                "values": ["傅里叶变换"],
                "provenance_refs": [f"{PREFIX}-candidate-{suffix}"],
            },
            ensure_ascii=False,
        ),
        status=ITEM_STATUS_EVIDENCE_READY,
        stage=ITEM_STAGE_EVIDENCE_RETRIEVAL,
    )
    job = app_module.BackgroundJob(
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        status="queued",
        input_json=json.dumps({"workflow_run_uid": run_uid, "workflow_version": WORKFLOW_VERSION_V1}),
        result_json="{}",
        attempt_count=0,
        max_attempts=3,
    )
    app_module.db.session.add_all([item, job])
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
    return run, item, lease


def _prepared(run, item, suffix="success"):
    en_ref = f"{PREFIX}-chunk-en-{suffix}"
    zh_ref = f"{PREFIX}-chunk-zh-{suffix}"
    return adapter.PreparedFormalItemVerificationInput(
        workflow_run_uid=run.run_uid,
        workflow_item_uid=item.item_uid,
        workflow_item_key=item.item_key,
        english_term=item.candidate_term,
        chinese_candidate_values=("傅里叶变换",),
        chinese_candidate_provenance_refs=(f"{PREFIX}-candidate-{suffix}",),
        english_evidence_refs=(en_ref,),
        chinese_evidence_refs=(zh_ref,),
        english_snippets=(adapter.PreparedEvidenceSnippet(en_ref, "Bounded English evidence."),),
        chinese_snippets=(adapter.PreparedEvidenceSnippet(zh_ref, "有界中文证据。"),),
        source_uid=run.source_uid,
        source_version=run.source_version,
        course=run.course,
        chapter=run.chapter,
        workflow_version=run.workflow_version,
        retrieval_version=run.retrieval_version,
        provider_name=PROVIDER,
        model_identity="replay-llm:v1",
        prompt_version="alignment-verification-v1",
        parser_version="alignment-output-parser-v1",
        output_schema_version="alignment-output-v1",
        risk_labels=("bilingual_alignment_not_verified",),
    )


def _dependencies(app_module, provider_resolver=alignment_providers.get_alignment_provider):
    models = adapter.DocumentAlignmentItemVerificationModels(
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
    )
    return adapter.DocumentAlignmentItemVerificationDependencies(
        session=app_module.db.session,
        models=models,
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
            resolve_provider=provider_resolver,
            validate_input=alignment_verification.validate_alignment_verification_input,
            create_safe_run=alignment_verification.create_safe_alignment_verification_run,
            attach=alignment_verification.apply_verification_result_to_card_protected,
        ),
        recording=adapter.RecordingCollaborator(
            record_usage=provider_governance.record_provider_usage,
            create_audit=audit_records.create_audit_record,
        ),
        fence_active_lease=fence_active_formal_job_lease_in_transaction,
        current_time_factory=lambda: NOW + timedelta(seconds=1),
        actor_role="teacher",
    )


def _command(run, item, lease, suffix="success"):
    return adapter.ExecuteDocumentAlignmentItemVerificationCommand(
        workflow_run_uid=run.run_uid,
        workflow_item_uid=item.item_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
        prepared_input=_prepared(run, item, suffix),
    )


def test_real_adapter_executes_once_persists_safe_summaries_and_reuses_completed_result(app_module):
    run, item, lease = _setup(app_module)
    calls = {"provider": 0}

    def counting_resolver(provider_name):
        calls["provider"] += 1
        return alignment_providers.get_alignment_provider(provider_name)

    command = _command(run, item, lease)
    dependencies = _dependencies(app_module, provider_resolver=counting_resolver)
    first = adapter.execute_document_alignment_item_verification(command, dependencies)
    second = adapter.execute_document_alignment_item_verification(command, dependencies)

    assert first.outcome == "needs_review"
    assert second.outcome == "reused_completed_result"
    assert calls["provider"] == 1
    assert first.provider_executed is True
    assert second.provider_executed is False
    assert first.execution_key == second.execution_key
    assert second.usage_recorded is True
    assert second.risk_labels == first.risk_labels
    assert second.confidence_summary == first.confidence_summary
    assert second.recommendation == first.recommendation

    app_module.db.session.expire_all()
    execution = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
        execution_key=first.execution_key
    ).one()
    persisted_item = app_module.DocumentAlignmentWorkflowItem.query.filter_by(
        item_uid=item.item_uid
    ).one()
    card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first.draft_card_uid).one()
    verification = app_module.AlignmentVerificationRun.query.filter_by(
        execution_key=first.execution_key
    ).one()
    assert execution.execution_status == "needs_review"
    assert persisted_item.status == "needs_review"
    assert card.status == "needs_review"
    assert app_module.AlignmentProviderPreflightRun.query.filter_by(
        execution_key=first.execution_key
    ).count() == 1
    assert app_module.AlignmentProviderUsageRecord.query.filter_by(
        execution_key=first.execution_key
    ).count() == 1
    assert app_module.AuditRecord.query.filter(
        app_module.AuditRecord.event_identity.like("item-audit-event-v1:%")
    ).count() >= 2

    serialized = "\n".join(
        [
            card.english_evidence,
            card.chinese_evidence,
            verification.input_payload,
            verification.output_payload,
            verification.prompt_summary,
            verification.raw_output_summary,
        ]
    )
    assert "Bounded English evidence" not in serialized
    assert "有界中文证据" not in serialized
    assert "chunk-en-success" in serialized
    assert "chunk-zh-success" in serialized
    _cleanup(app_module)


def test_adapter_reuses_exact_draft_but_blocks_different_evidence_scope(app_module):
    for suffix, existing_refs, expected in (
        ("draft-reuse", ("item-verification-adapter-9c5b-v2-chunk-en-draft-reuse",), "needs_review"),
        ("draft-conflict", ("different-governed-chunk",), "attach_blocked"),
    ):
        run, item, lease = _setup(app_module, suffix)
        prepared = _prepared(run, item, suffix)
        card = app_module.ConceptAlignmentCard(
            english_term=prepared.english_term,
            chinese_term=prepared.chinese_candidate_values[0],
            course=prepared.course,
            chapter=prepared.chapter,
            english_evidence=[{"chunk_uid": reference} for reference in existing_refs],
            chinese_evidence=[{"chunk_uid": prepared.chinese_evidence_refs[0]}],
            risk_labels=["bilingual_alignment_not_verified"],
            status="needs_review",
            retrieval_version=prepared.retrieval_version,
        )
        app_module.db.session.add(card)
        app_module.db.session.commit()

        result = adapter.execute_document_alignment_item_verification(
            _command(run, item, lease, suffix),
            _dependencies(app_module),
        )
        assert result.outcome == expected
        if expected == "needs_review":
            assert result.reused_draft is True
            assert result.draft_card_uid == card.card_uid
            assert app_module.ConceptAlignmentCard.query.filter_by(
                english_term=prepared.english_term
            ).count() == 1
        else:
            assert result.error_code == "DOCUMENT_ALIGNMENT_DRAFT_CONFLICT"
            assert app_module.AlignmentVerificationRun.query.filter_by(
                execution_key=result.execution_key
            ).count() == 0
        _cleanup(app_module)


def test_preflight_blocked_is_terminal_without_provider_or_usage(app_module):
    run, item, lease = _setup(app_module, "preflight-blocked")
    policy = app_module.AlignmentProviderPolicy.query.filter_by(provider_name=PROVIDER).one()
    policy.max_calls_per_month = 0
    app_module.db.session.commit()
    calls = {"provider": 0}

    def forbidden_provider(_):
        calls["provider"] += 1
        raise AssertionError("preflight-blocked item must not execute provider")

    result = adapter.execute_document_alignment_item_verification(
        _command(run, item, lease, "preflight-blocked"),
        _dependencies(app_module, provider_resolver=forbidden_provider),
    )
    assert result.outcome == "provider_preflight_blocked"
    assert result.execution_status == "preflight_blocked"
    assert result.item_status == "blocked"
    assert calls["provider"] == 0
    assert app_module.AlignmentProviderPreflightRun.query.filter_by(
        execution_key=result.execution_key
    ).count() == 1
    assert app_module.AlignmentVerificationRun.query.filter_by(
        execution_key=result.execution_key
    ).count() == 0
    assert app_module.AlignmentProviderUsageRecord.query.filter_by(
        execution_key=result.execution_key
    ).count() == 0
    _cleanup(app_module)


def test_parser_failure_persists_one_safe_failed_run_and_one_usage_without_attach(app_module):
    run, item, lease = _setup(app_module, "parser-failed")
    calls = {"provider": 0}

    class ParseFailedProvider:
        def verify_alignment(self, input_data):
            calls["provider"] += 1
            return {
                "provider_name": PROVIDER,
                "provider_type": "replay_llm",
                "provider_version": "v1",
                "alignment_confidence": None,
                "recommendation": "needs_review",
                "risk_labels": ["provider_schema_invalid"],
                "verification_status": "failed",
                "provider_response_status": "parse_failed",
                "prompt_version": "alignment-verification-v1",
                "prompt_summary": {"prompt_chars": 120, "stores_full_prompt": False},
                "raw_output_summary": {
                    "raw_output_preview": "must-not-persist",
                    "raw_output_chars": 18,
                    "stores_full_raw_output": False,
                },
                "parser_version": "alignment-output-parser-v1",
                "output_schema_version": "alignment-output-v1",
                "error_code": "provider_schema_invalid",
                "error_message": "Provider output did not match the formal schema.",
                "can_auto_approve": False,
                "is_production_result": False,
            }

    result = adapter.execute_document_alignment_item_verification(
        _command(run, item, lease, "parser-failed"),
        _dependencies(app_module, provider_resolver=lambda _: ParseFailedProvider()),
    )
    verification = app_module.AlignmentVerificationRun.query.filter_by(
        execution_key=result.execution_key
    ).one()
    assert result.outcome == "parser_failed"
    assert calls["provider"] == 1
    assert app_module.AlignmentProviderUsageRecord.query.filter_by(
        execution_key=result.execution_key
    ).count() == 1
    assert "must-not-persist" not in verification.raw_output_summary
    assert app_module.DocumentAlignmentWorkflowItem.query.filter_by(
        item_uid=item.item_uid
    ).one().status == "failed"
    _cleanup(app_module)


def test_active_lease_for_a_different_workflow_cannot_write_item_records(app_module):
    run, item, lease = _setup(app_module, "job-mismatch")
    job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
    job.input_json = json.dumps(
        {
            "workflow_run_uid": f"{PREFIX}-different-run",
            "workflow_version": run.workflow_version,
        }
    )
    app_module.db.session.commit()

    result = adapter.execute_document_alignment_item_verification(
        _command(run, item, lease, "job-mismatch"),
        _dependencies(app_module),
    )

    assert result.outcome == "execution_conflict"
    assert result.error_code == "FORMAL_ITEM_VERIFICATION_JOB_MISMATCH"
    assert app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
        workflow_item_uid=item.item_uid
    ).count() == 0
    assert app_module.ConceptAlignmentCard.query.filter_by(
        english_term=item.candidate_term
    ).count() == 0
    _cleanup(app_module)


@pytest.mark.parametrize(
    "prepared_change",
    [
        {"english_term": "Cross-scope term"},
        {
            "english_evidence_refs": ("cross-scope-en",),
            "english_snippets": (
                adapter.PreparedEvidenceSnippet("cross-scope-en", "Cross-scope evidence."),
            ),
        },
        {
            "chinese_candidate_values": ("错误候选",),
            "chinese_candidate_provenance_refs": ("cross-scope-candidate",),
        },
    ],
)
def test_prepared_input_must_match_persisted_item_scope(app_module, prepared_change):
    run, item, lease = _setup(app_module, "prepared-mismatch")
    command = _command(run, item, lease, "prepared-mismatch")
    command = dataclasses.replace(
        command,
        prepared_input=dataclasses.replace(command.prepared_input, **prepared_change),
    )

    result = adapter.execute_document_alignment_item_verification(
        command,
        _dependencies(app_module),
    )

    assert result.outcome == "execution_conflict"
    assert result.error_code == "FORMAL_ITEM_VERIFICATION_INPUT_MISMATCH"
    assert app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
        workflow_item_uid=item.item_uid
    ).count() == 0
    _cleanup(app_module)
