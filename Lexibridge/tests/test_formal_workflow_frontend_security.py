import json

from scripts import run_formal_workflow_frontend_e2e as ui_runner
from scripts import run_formal_workflow_frontend_resume_e2e as resume_runner


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5H"


def test_formal_ui_artifact_is_bounded_and_secret_free():
    result = ui_runner.build_result(
        verdict="PASS",
        scenarios=[{"name": "ready", "status": "PASS", "run_uid": "run-safe"}],
        console_errors=[],
        page_errors=[],
        external_requests=[],
        formal_posts=3,
        legacy_requests=0,
        duplicate_posts=0,
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["verdict"] == "PASS"
    assert result["actual_external_dependency_requests"] == 0
    assert result["legacy_alignment_requests"] == 0
    assert result["duplicate_formal_posts"] == 0
    assert SENTINEL not in serialized
    assert "token" not in serialized.casefold()


def test_resume_artifact_excludes_persisted_idempotency_key():
    result = resume_runner.build_result(
        verdict="PASS",
        run_uid="run-safe",
        formal_posts_before_reload=1,
        formal_posts_after_reload=1,
        storage_fields=["source_uid", "idempotency_key", "run_uid"],
        console_errors=[],
        page_errors=[],
        external_requests=[],
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["same_run_restored"] is True
    assert result["duplicate_formal_posts"] == 0
    assert "idempotency_key" not in serialized
    assert SENTINEL not in serialized

