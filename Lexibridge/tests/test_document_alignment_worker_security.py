from dataclasses import fields
from pathlib import Path

from services.document_alignment_worker_handler import RunFormalDocumentAlignmentJobResult

from services.document_alignment_workflow_application import (
    StartDocumentAlignmentWorkflowCommand,
    start_document_alignment_workflow,
)
from test_document_alignment_worker_integration import (
    PREFIX,
    _admission_dependencies,
    _cleanup,
    _setup_source,
)


def _card_snapshot(card):
    return {
        column.name: getattr(card, column.name)
        for column in card.__table__.columns
        if column.name != "updated_at"
    }


def test_full_worker_references_approved_cards_without_mutation_or_provider_execution(app_module):
    with app_module.app.app_context():
        source = _setup_source(app_module)
        approved_cards = []
        for index, (english, chinese) in enumerate(
            (("Fourier Transform", "傅里叶变换"), ("Laplace Transform", "拉普拉斯变换"))
        ):
            card = app_module.ConceptAlignmentCard(
                card_uid=f"{PREFIX}-approved-{index}",
                english_term=english,
                chinese_term=chinese,
                course=source.course,
                chapter=source.chapter,
                english_explanation="Teacher approved explanation",
                chinese_explanation="教师已批准说明",
                english_evidence=[{"chunk_uid": f"approved-en-{index}", "snippet": "approved body"}],
                chinese_evidence=[{"chunk_uid": f"approved-zh-{index}", "snippet": "已批准正文"}],
                alignment_reason="Teacher decision",
                confidence_score=0.95,
                risk_labels=["teacher_reviewed"],
                status="approved",
                reviewed_by=42,
                reviewed_at="2026-07-19 10:45:00",
                model_name="teacher",
                prompt_version="teacher-review-v1",
                retrieval_version="approved-retrieval-v1",
                version=7,
            )
            approved_cards.append(card)
            app_module.db.session.add(card)
        app_module.db.session.commit()
        before = {card.card_uid: _card_snapshot(card) for card in approved_cards}
        created = start_document_alignment_workflow(
            StartDocumentAlignmentWorkflowCommand(
                source_uid=source.source_uid,
                requested_by="1",
                request_id=f"{PREFIX}-approved-request",
                idempotency_key=f"{PREFIX}-approved-idempotency",
            ),
            _admission_dependencies(app_module),
        )

        result = app_module.run_formal_worker_once(worker_id=f"{PREFIX}-approved-worker")

        app_module.db.session.expire_all()
        mappings = app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            workflow_run_uid=created.run_uid
        ).all()
        execution_keys = [row.execution_key for row in mappings]
        persisted = app_module.ConceptAlignmentCard.query.filter(
            app_module.ConceptAlignmentCard.card_uid.in_(before)
        ).all()
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=created.run_uid).one_or_none()
        items = (
            app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).all()
            if run is not None
            else []
        )
        assert created.outcome == "created"
        assert result.workflow_run_uid == created.run_uid, (result, created)
        assert result.outcome == "completed"
        assert {card.card_uid: _card_snapshot(card) for card in persisted} == before
        assert len(mappings) == 2, [
            (item.candidate_term, item.status, item.error_code) for item in items
        ]
        assert {row.draft_card_uid for row in mappings} == set(before)
        assert app_module.AlignmentProviderPreflightRun.query.filter(
            app_module.AlignmentProviderPreflightRun.execution_key.in_(execution_keys)
        ).count() == 0
        assert app_module.AlignmentVerificationRun.query.filter(
            app_module.AlignmentVerificationRun.execution_key.in_(execution_keys)
        ).count() == 0
        assert app_module.AlignmentProviderUsageRecord.query.filter(
            app_module.AlignmentProviderUsageRecord.execution_key.in_(execution_keys)
        ).count() == 0
        _cleanup(app_module)


def test_worker_modules_do_not_log_or_return_tokens_payloads_or_network_clients():
    root = Path(__file__).resolve().parents[1]
    handler = (root / "backend" / "services" / "document_alignment_worker_handler.py").read_text(
        encoding="utf-8"
    )
    dispatcher = (root / "backend" / "services" / "formal_background_job_dispatch.py").read_text(
        encoding="utf-8"
    )
    for source in (handler, dispatcher):
        assert "print(" not in source
        assert "logging." not in source
        assert "urllib" not in source
        assert "requests" not in source
        assert "httpx" not in source
    assert "lease_token: str = field(repr=False)" not in handler
    assert "lease_token" not in {field.name for field in fields(RunFormalDocumentAlignmentJobResult)}
