from services.document_alignment_workflow_queries import (
    DocumentAlignmentQueryActor,
    DocumentAlignmentWorkflowQueryDependencies,
    GetDocumentAlignmentWorkflowRunCommand,
    ListDocumentAlignmentWorkflowItemsCommand,
    get_document_alignment_workflow_run,
    list_document_alignment_workflow_items,
)

from document_alignment_workflow_query_support import cleanup, create_scenario


def test_real_sqlite_queries_are_read_only_and_session_remains_usable(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(app_module, item_count=6, ready=2, blocked=2, failed=1)
        actor = DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher")
        dependencies = DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module)
        tracked_models = (
            app_module.DocumentAlignmentWorkflowRun,
            app_module.DocumentAlignmentWorkflowItem,
            app_module.BackgroundJob,
            app_module.ConceptAlignmentCard,
            app_module.AlignmentVerificationRun,
            app_module.AlignmentProviderUsageRecord,
            app_module.AuditRecord,
            app_module.AlignmentRun,
            app_module.TerminologyCard,
        )
        before = {model.__name__: model.query.count() for model in tracked_models}

        run_result = get_document_alignment_workflow_run(
            GetDocumentAlignmentWorkflowRunCommand(scenario["run_uid"], actor), dependencies
        )
        page_result = list_document_alignment_workflow_items(
            ListDocumentAlignmentWorkflowItemsCommand(scenario["run_uid"], actor, page=1, page_size=3),
            dependencies,
        )

        after = {model.__name__: model.query.count() for model in tracked_models}
        assert run_result.outcome == page_result.outcome == "found"
        assert before == after
        assert not app_module.db.session.new
        assert not app_module.db.session.dirty
        assert not app_module.db.session.deleted
        assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=scenario["run_uid"]).one()
        cleanup(app_module)


def test_query_reports_consistency_without_repairing_counts(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(
            app_module,
            item_count=2,
            run_status="ready_for_review",
            run_stage="terminal",
            ready=2,
        )
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=scenario["run_uid"]).one()
        app_module.db.session.execute(
            app_module.db.text(
                "UPDATE document_alignment_workflow_runs SET total_items = 1, ready_for_review_items = 2 WHERE id = :id"
            ),
            {"id": run.id},
        )
        app_module.db.session.commit()
        actor = DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher")
        result = get_document_alignment_workflow_run(
            GetDocumentAlignmentWorkflowRunCommand(scenario["run_uid"], actor),
            DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module),
        )

        assert result.outcome == "found"
        assert "DOCUMENT_ALIGNMENT_QUERY_DATA_INCONSISTENT" in result.run.consistency_warnings
        unchanged = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=scenario["run_uid"]).one()
        assert unchanged.total_items == 1
        assert unchanged.ready_for_review_items == 2
        cleanup(app_module)
