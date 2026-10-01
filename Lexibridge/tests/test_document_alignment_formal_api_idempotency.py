import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.formal_document_alignment_api_e2e_support import (
    cleanup_formal_api_state,
    create_formal_source,
    http_json,
    login,
    start_threaded_server,
)
from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
)


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)


def _post(base_url, auth, source_uid, key):
    return http_json(
        base_url,
        "/api/document-alignment-runs",
        method="POST",
        token=auth.token,
        opener=auth.opener,
        headers={"Idempotency-Key": key},
        body={"source_uid": source_uid},
    )


def test_source_scoped_replay_different_source_and_contract_drift(app_module):
    with app_module.app.app_context():
        source_a = create_formal_source(
            app_module,
            suffix="idem-a",
            terms=("Fourier Transform",),
            bilingual_terms={"Fourier Transform": "傅里叶变换"},
        )
        source_b = create_formal_source(
            app_module,
            suffix="idem-b",
            terms=("Laplace Transform",),
            bilingual_terms={"Laplace Transform": "拉普拉斯变换"},
        )

    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        first = _post(server.base_url, teacher, source_a.source_uid, "source-scoped-key")
        replay = _post(server.base_url, teacher, source_a.source_uid, "source-scoped-key")
        other_source = _post(server.base_url, teacher, source_b.source_uid, "source-scoped-key")

        assert first.status == replay.status == other_source.status == 202
        assert first.body["data"]["reused"] is False
        assert replay.body["data"]["reused"] is True
        assert replay.body["data"]["run_uid"] == first.body["data"]["run_uid"]
        assert replay.headers["Location"] == first.headers["Location"]
        assert other_source.body["data"]["reused"] is False
        assert other_source.body["data"]["run_uid"] != first.body["data"]["run_uid"]

        with app_module.app.app_context():
            source = app_module.KnowledgeSource.query.filter_by(
                source_uid=source_a.source_uid
            ).one()
            source.version = 2
            app_module.db.session.commit()
        conflict = _post(server.base_url, teacher, source_a.source_uid, "source-scoped-key")

        assert conflict.status == 409
        assert conflict.body["error_code"] == "DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT"
        with app_module.app.app_context():
            assert app_module.DocumentAlignmentWorkflowRun.query.filter(
                app_module.DocumentAlignmentWorkflowRun.source_uid.in_(
                    [source_a.source_uid, source_b.source_uid]
                )
            ).count() == 2
            assert app_module.BackgroundJob.query.filter_by(
                job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
            ).count() == 2
            assert app_module.AuditRecord.query.filter_by(
                event_type="document_alignment_requested"
            ).filter(
                app_module.AuditRecord.target_uid.in_([
                    first.body["data"]["run_uid"],
                    other_source.body["data"]["run_uid"],
                ])
            ).count() == 2


@pytest.mark.parametrize("round_index", range(5))
def test_concurrent_real_http_replay_has_one_run_and_job(app_module, round_index):
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix=f"concurrent-{round_index}",
            terms=("Fourier Transform",),
            bilingual_terms={"Fourier Transform": "傅里叶变换"},
        )

    with start_threaded_server(app_module.app) as server:
        first_client = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        second_client = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        barrier = threading.Barrier(2)

        def submit(auth):
            barrier.wait(timeout=5)
            return _post(
                server.base_url,
                auth,
                source.source_uid,
                f"concurrent-source-key-{round_index}",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(submit, (first_client, second_client)))

        assert [response.status for response in responses] == [202, 202]
        run_uids = {response.body["data"]["run_uid"] for response in responses}
        assert len(run_uids) == 1
        assert sorted(response.body["data"]["reused"] for response in responses) == [False, True]
        run_uid = next(iter(run_uids))
        with app_module.app.app_context():
            assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(
                source_uid=source.source_uid
            ).count() == 1
            assert app_module.BackgroundJob.query.filter(
                app_module.BackgroundJob.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
                app_module.BackgroundJob.input_json.like(f"%{run_uid}%"),
            ).count() == 1
            assert app_module.AuditRecord.query.filter_by(
                target_uid=run_uid,
                event_type="document_alignment_requested",
            ).count() == 1
