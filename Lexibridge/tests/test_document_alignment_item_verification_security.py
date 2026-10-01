import dataclasses
import json
import socket

from sqlalchemy.orm import sessionmaker

from services import alignment_providers
from services import document_alignment_item_verification_adapter as adapter
from test_document_alignment_item_verification_adapter_integration import (
    _cleanup,
    _command,
    _dependencies,
    _prepared,
    _setup,
)


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5B_V2"


def _legacy_counts(app_module):
    return {
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "terminology_cards": app_module.TerminologyCard.query.count(),
        "usage": app_module.UsageRecord.query.count(),
        "ai_calls": app_module.AICallLog.query.count(),
    }


def _card_snapshot(card):
    return {
        column.name: getattr(card, column.name)
        for column in card.__table__.columns
        if column.name != "updated_at"
    }


def test_existing_approved_card_is_referenced_but_never_modified_or_reverified(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "approved")
        prepared = _prepared(run, item, "approved")
        approved = app_module.ConceptAlignmentCard(
            card_uid="item-verification-adapter-9c5b-v2-approved-card",
            english_term=prepared.english_term,
            chinese_term=prepared.chinese_candidate_values[0],
            course=prepared.course,
            chapter=prepared.chapter,
            english_explanation="Teacher approved explanation",
            chinese_explanation="教师已批准说明",
            english_evidence=[{"chunk_uid": "approved-en", "snippet": "approved body"}],
            chinese_evidence=[{"chunk_uid": "approved-zh", "snippet": "已批准正文"}],
            alignment_reason="Teacher decision",
            confidence_score=0.94,
            risk_labels=["teacher_reviewed"],
            status="approved",
            reviewed_by=42,
            reviewed_at="2026-07-18 13:00:00",
            model_name="teacher",
            prompt_version="teacher-review-v1",
            retrieval_version="approved-retrieval-v1",
            version=7,
        )
        app_module.db.session.add(approved)
        app_module.db.session.commit()
        before = _card_snapshot(approved)

        calls = {"provider": 0}

        def forbidden_provider(_):
            calls["provider"] += 1
            raise AssertionError("approved card must not reach provider")

        result = adapter.execute_document_alignment_item_verification(
            _command(run, item, lease, "approved"),
            _dependencies(app_module, provider_resolver=forbidden_provider),
        )

        app_module.db.session.expire_all()
        persisted = app_module.ConceptAlignmentCard.query.filter_by(card_uid=approved.card_uid).one()
        execution = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            workflow_item_uid=item.item_uid
        ).one()
        assert result.outcome == "approved_card_protected"
        assert calls["provider"] == 0
        assert execution.draft_card_uid == approved.card_uid
        assert _card_snapshot(persisted) == before
        assert app_module.AlignmentProviderPreflightRun.query.filter_by(
            execution_key=result.execution_key
        ).count() == 0
        assert app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=result.execution_key
        ).count() == 0
        assert app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=result.execution_key
        ).count() == 0
        _cleanup(app_module)


def test_external_provider_fails_closed_before_resolver_or_network(app_module, monkeypatch):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "external-blocked")
        prepared = dataclasses.replace(
            _prepared(run, item, "external-blocked"),
            provider_name="deepseek-alignment-v1-disabled",
            model_identity="external-model-disabled",
        )
        run.provider_preference = prepared.provider_name
        run.model_preference = prepared.model_identity
        app_module.db.session.commit()
        command = dataclasses.replace(
            _command(run, item, lease, "external-blocked"),
            prepared_input=prepared,
        )

        def forbidden(*args, **kwargs):
            raise AssertionError("external provider or network was invoked")

        monkeypatch.setattr(socket, "socket", forbidden)
        result = adapter.execute_document_alignment_item_verification(
            command,
            _dependencies(app_module, provider_resolver=forbidden),
        )
        assert result.outcome == "provider_policy_blocked"
        assert result.provider_executed is False
        assert app_module.AlignmentProviderPreflightRun.query.filter_by(
            execution_key=result.execution_key
        ).count() == 0
        assert app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=result.execution_key
        ).count() == 0
        assert app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=result.execution_key
        ).count() == 0
        _cleanup(app_module)


def test_evidence_secret_stays_in_memory_and_formal_execution_has_no_legacy_dual_write(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "secret")
        prepared = dataclasses.replace(
            _prepared(run, item, "secret"),
            english_snippets=(
                adapter.PreparedEvidenceSnippet(
                    "item-verification-adapter-9c5b-v2-chunk-en-secret",
                    f"Governed evidence with in-memory {SENTINEL}.",
                ),
            ),
            chinese_snippets=(
                adapter.PreparedEvidenceSnippet(
                    "item-verification-adapter-9c5b-v2-chunk-zh-secret",
                    f"受治理证据仅在内存中 {SENTINEL}。",
                ),
            ),
        )
        command = dataclasses.replace(
            _command(run, item, lease, "secret"),
            prepared_input=prepared,
        )
        before = _legacy_counts(app_module)

        result = adapter.execute_document_alignment_item_verification(command, _dependencies(app_module))
        after = _legacy_counts(app_module)
        assert result.outcome == "needs_review"
        assert after == before

        execution = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            execution_key=result.execution_key
        ).one()
        card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=result.draft_card_uid).one()
        verification = app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=result.execution_key
        ).one()
        usage = app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=result.execution_key
        ).one()
        audits = app_module.AuditRecord.query.filter(
            app_module.AuditRecord.event_identity.like("item-audit-event-v1:%")
        ).all()
        serialized = json.dumps(
            {
                "result": dataclasses.asdict(result),
                "execution": {column.name: getattr(execution, column.name) for column in execution.__table__.columns},
                "card": {column.name: getattr(card, column.name) for column in card.__table__.columns},
                "verification": {
                    column.name: getattr(verification, column.name)
                    for column in verification.__table__.columns
                },
                "usage": {column.name: getattr(usage, column.name) for column in usage.__table__.columns},
                "audits": [
                    {column.name: getattr(record, column.name) for column in record.__table__.columns}
                    for record in audits
                ],
            },
            ensure_ascii=False,
            default=str,
        )
        assert SENTINEL not in serialized
        assert result.item_status == "needs_review"
        assert card.status == "needs_review"
        assert card.confidence_score is None
        _cleanup(app_module)


def test_card_approved_during_provider_execution_is_not_changed_by_attach(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "approved-race")
        approved_snapshot = {}
        Session = sessionmaker(bind=app_module.db.engine, expire_on_commit=False)
        real_provider = alignment_providers.get_alignment_provider("external-llm-replay-v1")

        class ApprovalRacingProvider:
            def verify_alignment(self, input_data):
                independent = Session()
                try:
                    card = independent.query(app_module.ConceptAlignmentCard).filter_by(
                        english_term=item.candidate_term
                    ).one()
                    card.status = "approved"
                    card.reviewed_by = 42
                    card.reviewed_at = "2026-07-18 14:00:01"
                    card.alignment_reason = "Concurrent teacher approval"
                    card.confidence_score = 0.91
                    card.risk_labels = ["teacher_reviewed"]
                    independent.commit()
                    approved_snapshot.update(_card_snapshot(card))
                finally:
                    independent.close()
                return real_provider.verify_alignment(input_data)

        dependencies = _dependencies(
            app_module,
            provider_resolver=lambda _: ApprovalRacingProvider(),
        )

        result = adapter.execute_document_alignment_item_verification(
            _command(run, item, lease, "approved-race"),
            dependencies,
        )
        app_module.db.session.expire_all()
        card = app_module.ConceptAlignmentCard.query.filter_by(
            english_term=item.candidate_term
        ).one()
        assert result.outcome == "attach_blocked"
        assert _card_snapshot(card) == approved_snapshot
        assert card.status == "approved"
        assert app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=result.execution_key
        ).count() == 1
        _cleanup(app_module)


def test_provider_controlled_secret_fields_are_not_persisted(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "provider-secret")
        real_provider = alignment_providers.get_alignment_provider("external-llm-replay-v1")

        class SecretFieldProvider:
            def verify_alignment(self, input_data):
                output = real_provider.verify_alignment(input_data)
                output.update(
                    {
                        "provider_version": SENTINEL,
                        "recommendation": SENTINEL,
                        "risk_labels": [SENTINEL],
                        "estimated_cost": {
                            "estimated_input_tokens": 1,
                            "estimated_output_tokens": 1,
                            "estimated_cost": 0.0,
                            "credential": SENTINEL,
                        },
                    }
                )
                return output

        result = adapter.execute_document_alignment_item_verification(
            _command(run, item, lease, "provider-secret"),
            _dependencies(app_module, provider_resolver=lambda _: SecretFieldProvider()),
        )
        verification = app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=result.execution_key
        ).one()
        card = app_module.ConceptAlignmentCard.query.filter_by(
            card_uid=result.draft_card_uid
        ).one()
        usage = app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=result.execution_key
        ).one()
        serialized = json.dumps(
            {
                "verification": {
                    column.name: getattr(verification, column.name)
                    for column in verification.__table__.columns
                },
                "card": {
                    column.name: getattr(card, column.name)
                    for column in card.__table__.columns
                },
                "usage": {
                    column.name: getattr(usage, column.name)
                    for column in usage.__table__.columns
                },
            },
            ensure_ascii=False,
            default=str,
        )
        assert SENTINEL not in serialized
        _cleanup(app_module)
