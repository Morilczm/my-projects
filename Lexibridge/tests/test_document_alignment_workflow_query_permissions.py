from services.document_alignment_workflow_queries import (
    DocumentAlignmentQueryActor,
    GetDocumentAlignmentWorkflowRunCommand,
    get_document_alignment_workflow_run,
)

from document_alignment_workflow_query_support import cleanup, create_scenario


def _result(app_module, scenario, actor):
    from services.document_alignment_workflow_queries import DocumentAlignmentWorkflowQueryDependencies

    return get_document_alignment_workflow_run(
        GetDocumentAlignmentWorkflowRunCommand(scenario["run_uid"], actor),
        DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module),
    )


def test_permission_matrix_and_anti_enumeration(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(app_module)
        admin = app_module.User.query.filter_by(role="admin").first()
        student = app_module.User.query.filter_by(role="student").first()

        assert _result(app_module, scenario, DocumentAlignmentQueryActor(str(admin.id), "admin")).outcome == "found"
        requester = DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher")
        course_teacher = DocumentAlignmentQueryActor(str(scenario["course_teacher_id"]), "teacher")
        unrelated = DocumentAlignmentQueryActor(str(scenario["unrelated_teacher_id"]), "teacher")
        assert _result(app_module, scenario, requester).outcome == "found"
        assert _result(app_module, scenario, course_teacher).outcome == "found"
        denied = _result(app_module, scenario, unrelated)
        student_denied = _result(app_module, scenario, DocumentAlignmentQueryActor(str(student.id), "student"))
        anonymous = _result(app_module, scenario, DocumentAlignmentQueryActor("", ""))

        assert denied.outcome == student_denied.outcome == anonymous.outcome == "not_found"
        assert denied.run is student_denied.run is anonymous.run is None
        cleanup(app_module)


def test_private_source_is_limited_to_requester_and_admin(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(app_module, visibility="private")
        admin = app_module.User.query.filter_by(role="admin").first()

        assert _result(app_module, scenario, DocumentAlignmentQueryActor(str(admin.id), "admin")).outcome == "found"
        requester = DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher")
        course_teacher = DocumentAlignmentQueryActor(str(scenario["course_teacher_id"]), "teacher")
        assert _result(app_module, scenario, requester).outcome == "found"
        assert _result(app_module, scenario, course_teacher).outcome == "not_found"
        cleanup(app_module)
