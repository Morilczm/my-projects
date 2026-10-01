import pytest

from formal_document_alignment_retry_support import logical_counts
from scripts.formal_document_alignment_api_e2e_support import (
    cleanup_formal_api_state,
    create_formal_source,
    find_job_for_run,
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


def _start_and_process(server, app_module, teacher, source_uid, key):
    started = http_json(
        server.base_url,
        "/api/document-alignment-runs",
        method="POST",
        token=teacher.token,
        body={"source_uid": source_uid},
        headers={"Idempotency-Key": key},
    )
    assert started.status == 202
    run_uid = started.body["data"]["run_uid"]
    with app_module.app.app_context():
        assert app_module.run_formal_worker_once(worker_id=f"{key}-worker").outcome == "completed"
    run = http_json(
        server.base_url,
        f"/api/document-alignment-runs/{run_uid}",
        token=teacher.token,
    )
    items = http_json(
        server.base_url,
        f"/api/document-alignment-runs/{run_uid}/items",
        token=teacher.token,
    )
    return run_uid, run, items


def test_partial_business_failure_completes_transport_with_warnings(app_module):
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix="partial",
            terms=("Fourier Transform", "Unmapped Course Term"),
            bilingual_terms={"Fourier Transform": "傅里叶变换"},
        )

    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        run_uid, run, items = _start_and_process(
            server,
            app_module,
            teacher,
            source.source_uid,
            "partial-key",
        )

        assert run.body["data"]["status"] == "completed_with_warnings"
        assert run.body["data"]["ready_for_review_items"] == 1
        assert run.body["data"]["blocked_items"] >= 1
        assert run.body["data"]["warning_count"] >= 1
        statuses = [item["status"] for item in items.body["data"]["items"]]
        assert statuses.count("needs_review") == 1
        assert statuses.count("blocked") == run.body["data"]["blocked_items"]
        with app_module.app.app_context():
            assert find_job_for_run(app_module, run_uid).status == "completed"
            assert logical_counts(app_module, run_uid)["usage"] == 0


def test_all_business_blocked_is_not_transport_failure(app_module):
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix="all-blocked",
            terms=("Unmapped Term Alpha", "Unmapped Term Beta"),
            bilingual_terms={},
        )

    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        run_uid, run, items = _start_and_process(
            server,
            app_module,
            teacher,
            source.source_uid,
            "all-blocked-key",
        )

        assert run.body["data"]["status"] == "blocked"
        assert run.body["data"]["blocked_items"] >= 1
        assert {item["status"] for item in items.body["data"]["items"]} == {"blocked"}
        assert {
            item["safe_error_code"] for item in items.body["data"]["items"]
        } == {"DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE"}
        with app_module.app.app_context():
            assert find_job_for_run(app_module, run_uid).status == "completed"
            assert logical_counts(app_module, run_uid)["usage"] == 0
