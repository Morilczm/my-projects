import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from services import document_alignment_processing_orchestrator as orchestrator


def test_processing_command_and_result_are_frozen_safe_dtos():
    command = orchestrator.ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid="run-9c5c",
        job_uid="job-9c5c",
        worker_id="worker-9c5c",
        execution_attempt=1,
        lease_token="LEXIBRIDGE_SENTINEL_SECRET_9C5C_LEASE",
    )
    result = orchestrator.ProcessDocumentAlignmentWorkflowResult(
        outcome="retryable_interruption",
        workflow_run_uid=command.workflow_run_uid,
        job_uid=command.job_uid,
        run_status="processing",
        run_stage="evidence_retrieval",
        total_items=2,
        ready_for_review_items=1,
        blocked_items=0,
        failed_items=0,
        warning_count=0,
        processed_in_this_invocation=1,
        reused_items=0,
        stopped_at_item_uid="item-2",
        retryable=True,
        error_code="DOCUMENT_ALIGNMENT_PROCESSING_INTERRUPTED",
        error_message="Processing was interrupted safely.",
    )

    assert orchestrator.ProcessDocumentAlignmentWorkflowCommand.__dataclass_params__.frozen is True
    assert orchestrator.ProcessDocumentAlignmentWorkflowResult.__dataclass_params__.frozen is True
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5C_LEASE" not in repr(command)
    assert not hasattr(result, "lease_token")
    with pytest.raises(dataclasses.FrozenInstanceError):
        command.worker_id = "other"


def test_root_audit_identity_is_stable_and_attempt_independent():
    first = orchestrator.build_document_alignment_root_audit_event_identity(
        "run-9c5c",
        "formal-document-alignment-v1",
        "document_alignment_processing_started",
    )
    repeat = orchestrator.build_document_alignment_root_audit_event_identity(
        "run-9c5c",
        "formal-document-alignment-v1",
        "document_alignment_processing_started",
    )
    terminal = orchestrator.build_document_alignment_root_audit_event_identity(
        "run-9c5c",
        "formal-document-alignment-v1",
        "document_alignment_ready_for_review",
    )

    assert first == repeat
    assert first != terminal
    assert first.startswith("document-alignment-root-audit-v1:")
    assert "worker" not in first
    assert "attempt" not in first


def test_orchestrator_module_has_no_http_worker_transport_or_legacy_dependencies():
    source_path = Path(inspect.getsourcefile(orchestrator))
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

    forbidden = (
        "flask",
        "routes",
        "worker",
        "urllib",
        "requests",
        "httpx",
        "socket",
        "services.legacy",
    )
    assert not any(name.startswith(forbidden) for name in imports)
    source = source_path.read_text(encoding="utf-8")
    assert "complete_formal_background_job" not in source
    assert "fail_formal_background_job" not in source
    assert "requeue_formal_background_job" not in source
