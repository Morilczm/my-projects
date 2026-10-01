from dataclasses import FrozenInstanceError

import pytest

from services.document_alignment_workflow_queries import (
    DocumentAlignmentQueryActor,
    DocumentAlignmentWorkflowQueryDependencies,
    GetDocumentAlignmentWorkflowRunCommand,
    get_document_alignment_workflow_run,
)

from document_alignment_workflow_query_support import cleanup, create_scenario


def _get(app_module, scenario):
    return get_document_alignment_workflow_run(
        GetDocumentAlignmentWorkflowRunCommand(
            scenario["run_uid"],
            DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher"),
        ),
        DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module),
    )


@pytest.mark.parametrize(
    ("status", "stage", "total", "ready", "blocked", "failed", "expected"),
    [
        ("queued", "queued", 0, 0, 0, 0, 0),
        ("validating", "source_validation", 10, 2, 1, 0, 30),
        ("processing", "verification", 10, 3, 1, 1, 50),
        ("ready_for_review", "terminal", 10, 8, 1, 1, 100),
        ("completed_with_warnings", "terminal", 10, 6, 2, 2, 100),
        ("blocked", "terminal", 0, 0, 0, 0, 100),
        ("failed", "terminal", 0, 0, 0, 0, 100),
    ],
)
def test_run_summary_and_progress(app_module, status, stage, total, ready, blocked, failed, expected):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(
            app_module,
            item_count=total,
            run_status=status,
            run_stage=stage,
            ready=ready,
            blocked=blocked,
            failed=failed,
        )
        result = _get(app_module, scenario)

        assert result.outcome == "found"
        assert result.run.progress_percent == expected
        terminal_statuses = {"ready_for_review", "completed_with_warnings", "blocked", "failed"}
        assert result.run.is_terminal is (status in terminal_statuses)
        assert result.run.source_title == "Governed query source"
        assert result.run.source_filename == "teacher-notes.pdf"
        assert not hasattr(result.run, "job_uid")
        assert not hasattr(result.run, "worker_id")
        assert not hasattr(result.run, "id")
        with pytest.raises(FrozenInstanceError):
            result.run.status = "failed"
        cleanup(app_module)


def test_run_not_found_and_invalid_request(app_module):
    with app_module.app.app_context():
        actor = DocumentAlignmentQueryActor("1", "admin")
        dependencies = DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module)
        missing = get_document_alignment_workflow_run(
            GetDocumentAlignmentWorkflowRunCommand("missing-9c5e", actor), dependencies
        )
        invalid = get_document_alignment_workflow_run(
            GetDocumentAlignmentWorkflowRunCommand("", actor), dependencies
        )
        assert missing.outcome == "not_found"
        assert invalid.outcome == "invalid_request"
