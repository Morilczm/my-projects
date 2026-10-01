from dataclasses import asdict

from services.document_alignment_workflow_queries import (
    DocumentAlignmentQueryActor,
    DocumentAlignmentWorkflowQueryDependencies,
    GetDocumentAlignmentWorkflowRunCommand,
    ListDocumentAlignmentWorkflowItemsCommand,
    get_document_alignment_workflow_run,
    list_document_alignment_workflow_items,
)

from document_alignment_workflow_query_support import cleanup, create_scenario


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5E"


def test_query_results_hide_transport_and_sensitive_content(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(
            app_module,
            item_count=1,
            source_filename=f"/private/internal/{SENTINEL}/safe-name.pdf",
        )
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=scenario["run_uid"]).one()
        item = app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).one()
        secret_run_error = f"traceback Authorization: Bearer {SENTINEL}"
        secret_item_error = f"provider output {SENTINEL}"
        secret_refs = f'["{SENTINEL}"]'
        confidence_summary = '{"alignment_confidence": 0.8, "raw_output": "untrusted provider body"}'
        app_module.db.session.execute(
            app_module.db.text(
                "UPDATE document_alignment_workflow_runs SET error_message = :secret WHERE id = :id"
            ),
            {"secret": secret_run_error, "id": run.id},
        )
        app_module.db.session.execute(
            app_module.db.text(
                "UPDATE document_alignment_workflow_items "
                "SET error_message = :secret, source_chunk_refs = :refs, "
                "confidence_summary = :confidence WHERE id = :id"
            ),
            {
                "secret": secret_item_error,
                "refs": secret_refs,
                "confidence": confidence_summary,
                "id": item.id,
            },
        )
        app_module.db.session.commit()
        actor = DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher")
        dependencies = DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module)
        run_result = get_document_alignment_workflow_run(
            GetDocumentAlignmentWorkflowRunCommand(scenario["run_uid"], actor), dependencies
        )
        item_result = list_document_alignment_workflow_items(
            ListDocumentAlignmentWorkflowItemsCommand(scenario["run_uid"], actor), dependencies
        )

        rendered = repr((asdict(run_result), asdict(item_result)))
        assert SENTINEL not in rendered
        assert "Authorization" not in rendered
        assert "untrusted provider body" not in rendered
        assert run_result.run.source_filename == "safe-name.pdf"
        assert not hasattr(run_result.run, "background_job")
        assert not hasattr(item_result.page.items[0], "preflight_run_uid")
        assert not hasattr(item_result.page.items[0], "usage_uid")
        cleanup(app_module)


def test_query_module_has_no_network_or_framework_dependencies():
    from pathlib import Path

    source = Path("backend/services/document_alignment_workflow_queries.py").read_text()
    forbidden = (
        "from flask",
        "import flask",
        "requests.",
        "httpx.",
        "urllib.",
        "socket.",
        "BackgroundJob",
        "lease_token",
        "worker_id",
    )
    assert all(marker not in source for marker in forbidden)


def test_legal_course_text_is_not_removed_by_credential_keyword_filtering(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(app_module, item_count=1)
        item = app_module.DocumentAlignmentWorkflowItem.query.join(
            app_module.DocumentAlignmentWorkflowRun
        ).filter(app_module.DocumentAlignmentWorkflowRun.run_uid == scenario["run_uid"]).one()
        item.candidate_term = "Password reset token protocol"
        item.normalized_term = "password reset token protocol"
        app_module.db.session.commit()
        result = list_document_alignment_workflow_items(
            ListDocumentAlignmentWorkflowItemsCommand(
                scenario["run_uid"],
                DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher"),
            ),
            DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module),
        )

        assert result.page.items[0].candidate_term == "Password reset token protocol"
        cleanup(app_module)
