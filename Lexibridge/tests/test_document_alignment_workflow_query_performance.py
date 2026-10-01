from sqlalchemy import event

from services.document_alignment_workflow_queries import (
    DocumentAlignmentQueryActor,
    DocumentAlignmentWorkflowQueryDependencies,
    GetDocumentAlignmentWorkflowRunCommand,
    ListDocumentAlignmentWorkflowItemsCommand,
    get_document_alignment_workflow_run,
    list_document_alignment_workflow_items,
)

from document_alignment_workflow_query_support import cleanup, create_scenario


def _count_selects(app_module, callback):
    statements = []

    def before_cursor_execute(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = app_module.db.engine
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        callback()
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    return statements


def test_run_and_item_query_counts_do_not_scale_with_item_count(app_module):
    counts = []
    with app_module.app.app_context():
        for item_count in (1, 10, 50):
            cleanup(app_module)
            scenario = create_scenario(app_module, item_count=item_count)
            actor = DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher")
            dependencies = DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module)
            run_statements = _count_selects(
                app_module,
                lambda: get_document_alignment_workflow_run(
                    GetDocumentAlignmentWorkflowRunCommand(scenario["run_uid"], actor), dependencies
                ),
            )
            page_statements = _count_selects(
                app_module,
                lambda: list_document_alignment_workflow_items(
                    ListDocumentAlignmentWorkflowItemsCommand(scenario["run_uid"], actor, page=1, page_size=20),
                    dependencies,
                ),
            )
            counts.append((len(run_statements), len(page_statements)))

        assert len({run_count for run_count, _ in counts}) == 1
        assert len({page_count for _, page_count in counts}) == 1
        assert max(page_count for _, page_count in counts) <= 6
        cleanup(app_module)


def test_item_query_uses_limit_offset_and_order_by(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(app_module, item_count=50)
        actor = DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher")
        statements = _count_selects(
            app_module,
            lambda: list_document_alignment_workflow_items(
                ListDocumentAlignmentWorkflowItemsCommand(scenario["run_uid"], actor, page=2, page_size=20),
                DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module),
            ),
        )
        page_sql = " ".join(
            statement.upper()
            for statement in statements
            if "DOCUMENT_ALIGNMENT_WORKFLOW_ITEMS" in statement.upper()
        )
        assert "ORDER BY" in page_sql
        assert "LIMIT" in page_sql
        assert "OFFSET" in page_sql
        cleanup(app_module)
