import pytest

from scripts.formal_document_alignment_api_e2e_support import (
    cleanup_formal_api_state,
    create_e2e_teacher,
    create_formal_source,
    http_json,
    login,
    start_threaded_server,
)


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)


def test_real_http_permissions_and_anti_enumeration(app_module):
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix="permissions",
            terms=("Fourier Transform",),
            bilingual_terms={"Fourier Transform": "傅里叶变换"},
        )
        course_teacher = create_e2e_teacher(
            app_module,
            suffix="course-teacher",
            course_member=True,
        )
        unrelated_teacher = create_e2e_teacher(
            app_module,
            suffix="unrelated-teacher",
            course_member=False,
        )

    with start_threaded_server(app_module.app) as server:
        requester = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        admin = login(server.base_url, "admin.test@lexibridge.local", "Admin1234")
        student = login(server.base_url, "student.test@lexibridge.local", "Student1234")
        peer = login(server.base_url, course_teacher.email, course_teacher.password)
        unrelated = login(
            server.base_url,
            unrelated_teacher.email,
            unrelated_teacher.password,
        )
        started = http_json(
            server.base_url,
            "/api/document-alignment-runs",
            method="POST",
            token=requester.token,
            body={"source_uid": source.source_uid},
            headers={"Idempotency-Key": "permissions-key"},
        )
        assert started.status == 202
        run_uid = started.body["data"]["run_uid"]
        run_path = f"/api/document-alignment-runs/{run_uid}"
        items_path = f"{run_path}/items"

        for actor in (requester, admin, peer):
            assert http_json(server.base_url, run_path, token=actor.token).status == 200
            assert http_json(server.base_url, items_path, token=actor.token).status == 200

        assert http_json(server.base_url, run_path, token=unrelated.token).status == 404
        assert http_json(server.base_url, items_path, token=unrelated.token).status == 404
        assert http_json(server.base_url, run_path, token=student.token).status == 403
        assert http_json(server.base_url, items_path, token=student.token).status == 403
        assert http_json(server.base_url, run_path).status == 401
        assert http_json(server.base_url, items_path).status == 401
        assert http_json(
            server.base_url,
            "/api/document-alignment-runs",
            method="POST",
            token=student.token,
            body={"source_uid": source.source_uid},
            headers={"Idempotency-Key": "student-denied-key"},
        ).status == 403
        assert http_json(
            server.base_url,
            "/api/document-alignment-runs",
            method="POST",
            body={"source_uid": source.source_uid},
            headers={"Idempotency-Key": "anonymous-denied-key"},
        ).status == 401
