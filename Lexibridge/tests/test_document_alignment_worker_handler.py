from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.document_alignment_processing_orchestrator import (
    OUTCOME_READY_FOR_REVIEW,
    ProcessDocumentAlignmentWorkflowResult,
)
from services.document_alignment_worker_handler import (
    OUTCOME_COMPLETED,
    DocumentAlignmentWorkerHandlerDependencies,
    FormalDocumentAlignmentJobSnapshot,
    FormalDocumentAlignmentRunSnapshot,
    FormalJobOwnershipCollaborator,
    FormalProcessingCollaborator,
    RunFormalDocumentAlignmentJobResult,
    load_formal_document_alignment_job_payload,
    run_claimed_formal_document_alignment_job,
)
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    ROOT_STAGE_TERMINAL,
    ROOT_STATUS_READY_FOR_REVIEW,
    WORKFLOW_VERSION_V1,
)
from services.formal_background_job_execution import (
    LEASE_OUTCOME_ACCEPTED,
    FormalJobExecutionLease,
    FormalJobLeaseOperationResult,
)


NOW = datetime(2026, 7, 19, 1, 0, 0)


def _lease():
    return FormalJobExecutionLease(
        job_uid="formal-job-9c5d",
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        worker_id="formal-worker-9c5d",
        execution_attempt=3,
        lease_token="LEXIBRIDGE_SENTINEL_SECRET_9C5D_LEASE",
        claimed_at=NOW,
        heartbeat_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
        status="running",
    )


def _accepted(status="running"):
    return FormalJobLeaseOperationResult(
        outcome=LEASE_OUTCOME_ACCEPTED,
        job_uid="formal-job-9c5d",
        execution_attempt=3,
        status=status,
    )


def _job(payload=None):
    return FormalDocumentAlignmentJobSnapshot(
        job_uid="formal-job-9c5d",
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        status="running",
        input_payload=payload or {
            "workflow_run_uid": "formal-run-9c5d",
            "workflow_version": WORKFLOW_VERSION_V1,
        },
        attempt_count=0,
        max_attempts=3,
    )


def _run(status=ROOT_STATUS_READY_FOR_REVIEW, stage=ROOT_STAGE_TERMINAL):
    return FormalDocumentAlignmentRunSnapshot(
        run_uid="formal-run-9c5d",
        workflow_version=WORKFLOW_VERSION_V1,
        status=status,
        stage=stage,
    )


def test_worker_result_and_dependencies_are_frozen_and_hide_lease_token():
    result = RunFormalDocumentAlignmentJobResult(
        outcome=OUTCOME_COMPLETED,
        job_uid="formal-job-9c5d",
        workflow_run_uid="formal-run-9c5d",
        job_status="completed",
        run_status=ROOT_STATUS_READY_FOR_REVIEW,
        run_stage=ROOT_STAGE_TERMINAL,
        execution_attempt=3,
        orchestrator_outcome=OUTCOME_READY_FOR_REVIEW,
        completed=True,
    )
    with pytest.raises(FrozenInstanceError):
        result.outcome = "failed"

    lease = _lease()
    assert lease.lease_token not in repr(lease)
    assert lease.lease_token not in repr(result)


def test_payload_contract_is_strict_and_does_not_echo_raw_payload():
    parsed = load_formal_document_alignment_job_payload(_job().input_payload)
    assert parsed.workflow_run_uid == "formal-run-9c5d"
    assert parsed.workflow_version == WORKFLOW_VERSION_V1

    with pytest.raises(ValueError, match="FORMAL_DOCUMENT_JOB_PAYLOAD_INVALID"):
        load_formal_document_alignment_job_payload(
            {
                "workflow_run_uid": "formal-run-9c5d",
                "workflow_version": WORKFLOW_VERSION_V1,
                "credential": "LEXIBRIDGE_SENTINEL_SECRET_9C5D",
            }
        )


def test_handler_maps_terminal_root_to_job_complete_and_calls_only_orchestrator_once():
    calls = {"process": 0, "complete": 0}

    def process(command):
        calls["process"] += 1
        assert command.workflow_run_uid == "formal-run-9c5d"
        assert command.job_uid == "formal-job-9c5d"
        assert command.worker_id == "formal-worker-9c5d"
        assert command.execution_attempt == 3
        assert command.lease_token == _lease().lease_token
        return ProcessDocumentAlignmentWorkflowResult(
            outcome=OUTCOME_READY_FOR_REVIEW,
            workflow_run_uid=command.workflow_run_uid,
            job_uid=command.job_uid,
            run_status=ROOT_STATUS_READY_FOR_REVIEW,
            run_stage=ROOT_STAGE_TERMINAL,
        )

    dependencies = DocumentAlignmentWorkerHandlerDependencies(
        load_job=lambda _: _job(),
        load_run=lambda _: _run(),
        ownership=FormalJobOwnershipCollaborator(
            validate=lambda _: _accepted(),
            heartbeat=lambda _: _accepted(),
            complete=lambda _: calls.__setitem__("complete", calls["complete"] + 1) or _accepted("completed"),
            requeue=lambda *_: pytest.fail("terminal outcome must not requeue"),
            fail=lambda *_: pytest.fail("terminal outcome must not fail"),
        ),
        processing=FormalProcessingCollaborator(
            execute=process,
            finalize_failure=lambda *_: pytest.fail("terminal outcome must not finalize failure"),
        ),
    )

    result = run_claimed_formal_document_alignment_job(_lease(), dependencies)

    assert result.outcome == OUTCOME_COMPLETED
    assert result.completed is True
    assert result.job_status == "completed"
    assert calls == {"process": 1, "complete": 1}


def test_handler_module_has_no_http_or_direct_processing_imports():
    source = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "services"
        / "document_alignment_worker_handler.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "from flask",
        "backend.app",
        "bilingual_evidence_workflow",
        "chinese_term_candidates",
        "concept_card_drafts",
        "alignment_providers",
        "alignment_verification",
        "urllib",
        "requests",
        "httpx",
    )
    assert not any(value in source for value in forbidden)
