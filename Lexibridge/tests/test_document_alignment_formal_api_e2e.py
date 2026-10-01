import pytest

from scripts import run_formal_document_alignment_api_e2e as api_runner
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


def test_real_http_start_worker_poll_terminal_and_items(app_module):
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix="success",
            terms=("Fourier Transform", "Laplace Transform"),
            bilingual_terms={
                "Fourier Transform": "傅里叶变换",
                "Laplace Transform": "拉普拉斯变换",
            },
        )
        legacy_before = {
            "runs": app_module.AlignmentRun.query.count(),
            "cards": app_module.TerminologyCard.query.count(),
            "usage": app_module.UsageRecord.query.count(),
            "calls": app_module.AICallLog.query.count(),
        }

    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        started = http_json(
            server.base_url,
            "/api/document-alignment-runs",
            method="POST",
            token=teacher.token,
            headers={
                "Idempotency-Key": "formal-api-e2e-success",
                "X-Request-ID": "formal-api-e2e-success-request",
            },
            body={"source_uid": source.source_uid},
        )

        assert started.status == 202, started.body
        assert started.headers["Location"] == started.body["data"]["status_url"]
        assert started.headers["Retry-After"] == "2"
        assert started.headers["X-Request-ID"]
        assert started.body["data"]["reused"] is False
        run_uid = started.body["data"]["run_uid"]

        with app_module.app.app_context():
            job = find_job_for_run(app_module, run_uid)
            assert job.max_attempts == 3
            worker = app_module.run_formal_worker_once(worker_id="formal-api-e2e-worker")
            assert worker.outcome == "completed"

        terminal = http_json(
            server.base_url,
            started.headers["Location"],
            token=teacher.token,
        )
        items = http_json(
            server.base_url,
            f"/api/document-alignment-runs/{run_uid}/items?page=1&page_size=20",
            token=teacher.token,
        )

        assert terminal.status == items.status == 200
        assert terminal.body["data"]["status"] == "ready_for_review"
        assert terminal.body["data"]["progress_percent"] == 100
        assert terminal.body["data"]["ready_for_review_items"] == 2
        assert [item["status"] for item in items.body["data"]["items"]] == [
            "needs_review",
            "needs_review",
        ]
        with app_module.app.app_context():
            assert find_job_for_run(app_module, run_uid).status == "completed"
            assert {
                "runs": app_module.AlignmentRun.query.count(),
                "cards": app_module.TerminologyCard.query.count(),
                "usage": app_module.UsageRecord.query.count(),
                "calls": app_module.AICallLog.query.count(),
            } == legacy_before


def test_api_e2e_artifact_contract_is_safe_and_structured():
    result = api_runner.build_api_result(
        verdict="PASS",
        scenarios=[{"name": "normal", "status": "PASS"}],
        production_contract={"workflow_version": "formal-document-alignment-v1"},
        external_requests=[],
    )

    assert result["verdict"] == "PASS"
    assert result["actual_external_dependency_requests"] == 0
    assert result["timeouts"] == []
    assert result["blocking_failures"] == []
    assert "token" not in str(result).casefold()


def test_recovery_artifact_requires_http_terminal_query_evidence():
    required = {
        "retryable_requeue",
        "claim_crash_stale_reclaim",
        "partial_checkpoint_resume",
        "terminal_before_job_complete",
        "retry_exhaustion",
    }
    scenarios = [
        {
            "name": name,
            "status": "PASS",
            "http_terminal_status": "failed" if name == "retry_exhaustion" else "ready_for_review",
            "http_item_count": 2,
        }
        for name in sorted(required)
    ]

    api_runner.assert_recovery_http_evidence(scenarios)

    del scenarios[0]["http_terminal_status"]
    with pytest.raises(AssertionError):
        api_runner.assert_recovery_http_evidence(scenarios)
