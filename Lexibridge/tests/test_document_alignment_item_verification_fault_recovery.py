import dataclasses
from datetime import timedelta

import pytest
from sqlalchemy import event

from services import alignment_providers
from services import document_alignment_item_verification_adapter as adapter
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
)
from test_document_alignment_item_verification_adapter_integration import (
    NOW,
    PREFIX,
    _cleanup,
    _command,
    _dependencies,
    _setup,
)


def test_provider_success_then_verification_persistence_failure_recovers_with_one_logical_result(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "provider-db-failure")
        calls = {"provider": 0, "persist": 0}

        def resolver(provider_name):
            calls["provider"] += 1
            return alignment_providers.get_alignment_provider(provider_name)

        normal = _dependencies(app_module, provider_resolver=resolver)
        real_create = normal.verification.create_safe_run

        def fail_once(*args, **kwargs):
            calls["persist"] += 1
            if calls["persist"] == 1:
                raise RuntimeError("controlled verification persistence failure")
            return real_create(*args, **kwargs)

        failing = dataclasses.replace(
            normal,
            verification=dataclasses.replace(normal.verification, create_safe_run=fail_once),
        )
        command = _command(run, item, lease, "provider-db-failure")

        first = adapter.execute_document_alignment_item_verification(command, failing)
        checkpoint = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            execution_key=first.execution_key
        ).one()
        assert checkpoint.execution_status == "provider_completed"
        assert checkpoint.provider_started_at
        assert checkpoint.provider_completed_at
        assert checkpoint.safe_output_fingerprint
        second = adapter.execute_document_alignment_item_verification(command, normal)

        assert first.outcome == "persistence_error"
        assert first.retryable is True
        assert second.outcome == "needs_review"
        assert calls["provider"] == 2
        assert app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=second.execution_key
        ).count() == 1
        assert app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=second.execution_key
        ).count() == 1
        _cleanup(app_module)


def test_attach_failure_rolls_back_card_mutation_and_retry_does_not_reexecute_provider(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "attach-failure")
        calls = {"provider": 0, "attach": 0}

        def resolver(provider_name):
            calls["provider"] += 1
            return alignment_providers.get_alignment_provider(provider_name)

        normal = _dependencies(app_module, provider_resolver=resolver)
        real_attach = normal.verification.attach

        def mutate_then_fail(*args, **kwargs):
            calls["attach"] += 1
            card = real_attach(*args, **kwargs)
            raise RuntimeError("controlled attach persistence failure")

        failing = dataclasses.replace(
            normal,
            verification=dataclasses.replace(normal.verification, attach=mutate_then_fail),
        )
        command = _command(run, item, lease, "attach-failure")

        first = adapter.execute_document_alignment_item_verification(command, failing)
        app_module.db.session.expire_all()
        execution = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            execution_key=first.execution_key
        ).one()
        card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=execution.draft_card_uid).one()
        assert first.outcome == "attach_pending"
        assert execution.execution_status == "attach_pending"
        assert card.get_risk_labels() == ["bilingual_alignment_not_verified"]

        second = adapter.execute_document_alignment_item_verification(command, normal)
        assert second.outcome == "needs_review"
        assert calls["provider"] == 1
        assert calls["attach"] == 1
        _cleanup(app_module)


def test_reclaimed_old_attempt_cannot_create_execution_or_business_records(app_module):
    with app_module.app.app_context():
        run, item, old_lease = _setup(app_module, "stale-attempt")
        new_lease = claim_next_formal_background_job(
            f"{PREFIX}-worker-new",
            FormalBackgroundJobExecutionDependencies(
                session=app_module.db.session,
                job_model=app_module.BackgroundJob,
                current_time_factory=lambda: NOW + timedelta(seconds=31),
                lease_token_factory=lambda: f"{PREFIX}-lease-new",
            ),
        ).lease
        assert new_lease.execution_attempt == old_lease.execution_attempt + 1

        result = adapter.execute_document_alignment_item_verification(
            _command(run, item, old_lease, "stale-attempt"),
            _dependencies(app_module),
        )
        assert result.outcome == "stale_attempt"
        assert app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            workflow_item_uid=item.item_uid
        ).count() == 0
        assert app_module.ConceptAlignmentCard.query.filter_by(
            english_term=item.candidate_term
        ).count() == 0
        assert app_module.AlignmentVerificationRun.query.filter_by(
            card_uid=f"{PREFIX}-item-stale-attempt"
        ).count() == 0
        _cleanup(app_module)


def test_execution_mapping_flush_failure_rolls_back_and_same_session_can_retry(app_module, monkeypatch):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "mapping-flush")
        command = _command(run, item, lease, "mapping-flush")
        original_flush = app_module.db.session.flush
        calls = {"flush": 0}

        def fail_first_flush(*args, **kwargs):
            calls["flush"] += 1
            if calls["flush"] == 1:
                raise RuntimeError("controlled mapping flush failure")
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(app_module.db.session, "flush", fail_first_flush)
        first = adapter.execute_document_alignment_item_verification(command, _dependencies(app_module))
        second = adapter.execute_document_alignment_item_verification(command, _dependencies(app_module))
        assert first.outcome == "persistence_error"
        assert second.outcome == "needs_review"
        assert app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            execution_key=second.execution_key
        ).count() == 1
        _cleanup(app_module)


def test_draft_flush_failure_rolls_back_to_prepared_and_retry_creates_one_draft(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "draft-flush")
        normal = _dependencies(app_module)

        def fail_draft(*args, **kwargs):
            raise RuntimeError("controlled draft flush failure")

        failing = dataclasses.replace(
            normal,
            draft=dataclasses.replace(normal.draft, create_or_reuse=fail_draft),
        )
        command = _command(run, item, lease, "draft-flush")
        first = adapter.execute_document_alignment_item_verification(command, failing)
        second = adapter.execute_document_alignment_item_verification(command, normal)

        assert first.outcome == "persistence_error"
        assert second.outcome == "needs_review"
        assert app_module.ConceptAlignmentCard.query.filter_by(
            english_term=item.candidate_term
        ).count() == 1
        _cleanup(app_module)


def test_crash_after_preflight_and_provider_started_reuses_preflight_on_resume(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "provider-started-crash")
        command = _command(run, item, lease, "provider-started-crash")

        def crash_before_provider(_):
            raise SystemExit("simulated worker crash after provider_started commit")

        with pytest.raises(SystemExit):
            adapter.execute_document_alignment_item_verification(
                command,
                _dependencies(app_module, provider_resolver=crash_before_provider),
            )
        app_module.db.session.expire_all()
        execution = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            workflow_item_uid=item.item_uid
        ).one()
        assert execution.execution_status == "provider_started"
        assert app_module.AlignmentProviderPreflightRun.query.filter_by(
            execution_key=execution.execution_key
        ).count() == 1
        assert app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=execution.execution_key
        ).count() == 0

        resumed = adapter.execute_document_alignment_item_verification(command, _dependencies(app_module))
        assert resumed.outcome == "needs_review"
        assert resumed.reused_preflight is True
        assert app_module.AlignmentProviderPreflightRun.query.filter_by(
            execution_key=resumed.execution_key
        ).count() == 1
        _cleanup(app_module)


def test_provider_failure_is_terminal_when_failed_items_are_not_retryable(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "provider-terminal")
        command = _command(run, item, lease, "provider-terminal")

        class FailingProvider:
            def verify_alignment(self, input_data):
                raise RuntimeError("controlled deterministic provider failure")

        first = adapter.execute_document_alignment_item_verification(
            command,
            _dependencies(app_module, provider_resolver=lambda _: FailingProvider()),
        )
        second = adapter.execute_document_alignment_item_verification(
            command,
            _dependencies(app_module),
        )

        assert first.outcome == "verification_failed"
        assert first.item_status == "failed"
        assert first.retryable is False
        assert second.outcome == "execution_conflict"
        _cleanup(app_module)


def test_lease_reclaimed_during_provider_prevents_result_usage_audit_and_attach_writes(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "lease-lost")
        command = _command(run, item, lease, "lease-lost")
        real_provider = alignment_providers.get_alignment_provider("external-llm-replay-v1")

        class LeaseStealingProvider:
            def verify_alignment(self, input_data):
                job = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
                job.execution_attempt += 1
                job.locked_by = "replacement-worker"
                job.lease_token = "replacement-lease"
                job.lease_expires_at = "2026-07-18 15:00:00"
                app_module.db.session.commit()
                return real_provider.verify_alignment(input_data)

        result = adapter.execute_document_alignment_item_verification(
            command,
            _dependencies(app_module, provider_resolver=lambda _: LeaseStealingProvider()),
        )
        execution = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            workflow_item_uid=item.item_uid
        ).one()
        assert result.outcome == "stale_attempt"
        assert execution.execution_status == "provider_started"
        assert app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=execution.execution_key
        ).count() == 0
        assert app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=execution.execution_key
        ).count() == 0
        assert app_module.AuditRecord.query.filter_by(
            event_identity=adapter.build_formal_item_audit_event_identity(
                execution.execution_key,
                "item_verification_provider_completed",
            )
        ).count() == 0
        _cleanup(app_module)


def test_item_update_failure_rolls_back_attached_card_and_persists_attach_pending(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "item-update-failure")
        command = _command(run, item, lease, "item-update-failure")

        def fail_needs_review_update(mapper, connection, target):
            if target.item_uid == item.item_uid and target.status == "needs_review":
                raise RuntimeError("controlled item update failure")

        event.listen(app_module.DocumentAlignmentWorkflowItem, "before_update", fail_needs_review_update)
        try:
            first = adapter.execute_document_alignment_item_verification(command, _dependencies(app_module))
        finally:
            event.remove(app_module.DocumentAlignmentWorkflowItem, "before_update", fail_needs_review_update)

        app_module.db.session.expire_all()
        execution = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            execution_key=first.execution_key
        ).one()
        card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=execution.draft_card_uid).one()
        assert first.outcome == "attach_pending"
        assert execution.execution_status == "attach_pending"
        assert card.get_risk_labels() == ["bilingual_alignment_not_verified"]

        second = adapter.execute_document_alignment_item_verification(command, _dependencies(app_module))
        assert second.outcome == "needs_review"
        _cleanup(app_module)
