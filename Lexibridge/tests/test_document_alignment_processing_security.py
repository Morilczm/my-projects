import ast
import dataclasses
import inspect
import json
import socket
from pathlib import Path

import pytest

from services import document_alignment_item_preparation as preparation
from services import document_alignment_processing_orchestrator as orchestrator
from test_document_alignment_processing_orchestrator_integration import (
    _cleanup,
    _formal_counts_for_run,
    _orchestrator_dependencies,
    _setup_governed_workflow,
)


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5C"


@pytest.fixture(autouse=True)
def _app_context(app_module):
    with app_module.app.app_context():
        yield


def test_item_preparation_contract_is_frozen_and_hides_prepared_input():
    command = preparation.PrepareDocumentAlignmentItemCommand(
        workflow_run_uid="run-9c5c",
        workflow_item_uid="item-9c5c",
    )
    result = preparation.PrepareDocumentAlignmentItemResult(
        outcome="chinese_candidate_unavailable",
        workflow_run_uid=command.workflow_run_uid,
        workflow_item_uid=command.workflow_item_uid,
        error_code="DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE",
        error_message="No governed Chinese candidate is available.",
    )

    assert preparation.PrepareDocumentAlignmentItemCommand.__dataclass_params__.frozen is True
    assert preparation.PrepareDocumentAlignmentItemResult.__dataclass_params__.frozen is True
    assert "prepared_input=None" not in repr(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        command.workflow_item_uid = "other"


def test_primary_candidate_selection_is_stable_and_rejects_secret_like_values():
    candidates = [
        {"candidate_uid": "b", "chinese_term": "拉普拉斯变换", "score": 0.8},
        {"candidate_uid": "a", "chinese_term": "傅里叶变换", "score": 0.8},
        {
            "candidate_uid": "secret",
            "chinese_term": "LEXIBRIDGE_SENTINEL_SECRET_9C5C",
            "score": 1.0,
        },
    ]

    selected = preparation.select_primary_chinese_candidate(candidates)

    assert selected["candidate_uid"] == "a"
    assert selected["chinese_term"] == "傅里叶变换"


def test_item_preparation_module_has_no_network_or_legacy_execution_imports():
    source_path = Path(inspect.getsourcefile(preparation))
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    forbidden = ("urllib", "requests", "httpx", "socket", "services.ai_providers", "services.legacy")
    assert not any(name.startswith(forbidden) for name in imports)


def _command(run_uid, lease):
    return orchestrator.ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )


def _legacy_counts(app_module):
    return {
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "terminology_cards": app_module.TerminologyCard.query.count(),
        "usage": app_module.UsageRecord.query.count(),
        "ai_calls": app_module.AICallLog.query.count(),
    }


def _row_values(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def test_real_orchestrator_keeps_evidence_secret_in_memory_and_has_no_legacy_or_network_write(
    app_module,
    monkeypatch,
):
    run_uid, lease = _setup_governed_workflow(app_module, "security-secret", bootstrap=True)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    chunk = app_module.KnowledgeChunk.query.filter_by(source_uid=run.source_uid).one()
    chunk.content = f"Fourier Transform governed evidence {SENTINEL}"
    chinese = app_module.KnowledgeChunk.query.filter(
        app_module.KnowledgeChunk.course == run.course,
        app_module.KnowledgeChunk.source_uid != run.source_uid,
    ).one()
    chinese.content = f"傅里叶变换（Fourier Transform）受治理证据 {SENTINEL}"
    app_module.db.session.commit()
    before = _legacy_counts(app_module)

    def forbidden_network(*args, **kwargs):
        raise AssertionError("formal deterministic processing must not open a socket")

    monkeypatch.setattr(socket, "socket", forbidden_network)
    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(
            app_module,
            app_module.db.session,
            lease,
            "security-secret",
        ),
    )

    mapping = app_module.DocumentAlignmentItemVerificationExecution.query.one()
    card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=mapping.draft_card_uid).one()
    verification = app_module.AlignmentVerificationRun.query.filter_by(
        execution_key=mapping.execution_key
    ).one()
    usage = app_module.AlignmentProviderUsageRecord.query.filter_by(
        execution_key=mapping.execution_key
    ).one()
    audits = app_module.AuditRecord.query.filter(
        (app_module.AuditRecord.target_uid == run_uid)
        | (app_module.AuditRecord.event_identity.like("item-audit-event-v1:%"))
    ).all()
    serialized = json.dumps(
        {
            "result": dataclasses.asdict(result),
            "run": _row_values(app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()),
            "item": _row_values(app_module.DocumentAlignmentWorkflowItem.query.one()),
            "mapping": _row_values(mapping),
            "card": _row_values(card),
            "verification": _row_values(verification),
            "usage": _row_values(usage),
            "audits": [_row_values(row) for row in audits],
            "job": _row_values(app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()),
        },
        ensure_ascii=False,
        default=str,
    )
    assert result.outcome == "ready_for_review"
    assert SENTINEL not in serialized
    assert _legacy_counts(app_module) == before
    assert card.status == "needs_review"
    _cleanup(app_module)


def test_real_orchestrator_never_mutates_existing_approved_card(app_module):
    run_uid, lease = _setup_governed_workflow(app_module, "security-approved", bootstrap=True)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    item = app_module.DocumentAlignmentWorkflowItem.query.one()
    approved = app_module.ConceptAlignmentCard(
        card_uid="processing-orchestrator-9c5c-approved-card",
        english_term=item.candidate_term,
        chinese_term="傅里叶变换",
        course=run.course,
        chapter=run.chapter,
        english_explanation="Teacher approved explanation",
        chinese_explanation="教师已批准说明",
        english_evidence=[{"chunk_uid": "approved-en", "snippet": "approved body"}],
        chinese_evidence=[{"chunk_uid": "approved-zh", "snippet": "已批准正文"}],
        alignment_reason="Teacher decision",
        confidence_score=0.95,
        risk_labels=["teacher_reviewed"],
        status="approved",
        reviewed_by=42,
        reviewed_at="2026-07-18 15:00:00",
        model_name="teacher",
        prompt_version="teacher-review-v1",
        retrieval_version="approved-retrieval-v1",
        version=9,
    )
    app_module.db.session.add(approved)
    app_module.db.session.commit()
    before = _row_values(approved)

    result = orchestrator.process_document_alignment_workflow(
        _command(run_uid, lease),
        _orchestrator_dependencies(
            app_module,
            app_module.db.session,
            lease,
            "security-approved",
        ),
    )

    app_module.db.session.expire_all()
    persisted = app_module.ConceptAlignmentCard.query.filter_by(card_uid=approved.card_uid).one()
    assert result.outcome == "blocked"
    assert _row_values(persisted) == before
    counts = _formal_counts_for_run(app_module, run_uid)
    assert counts["verifications"] == 0
    assert counts["usage"] == 0
    _cleanup(app_module)
