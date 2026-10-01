#!/usr/bin/env python3
"""Run the formal document-alignment API through real loopback HTTP."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TESTS = ROOT / "tests"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from scripts import run_browser_e2e as base_e2e  # noqa: E402
from scripts.formal_document_alignment_api_e2e_support import (  # noqa: E402
    assert_safe_public_payload,
    block_external_network,
    create_formal_source,
    find_job_for_run,
    http_json,
    login,
    poll_until_terminal,
    run_quiet_e2e_setup,
    start_threaded_server,
)
from formal_document_alignment_retry_support import (  # noqa: E402
    claim,
    logical_counts,
    process_until_first_item_then_crash,
    reclaim_after_expiry,
    run_claimed_with_retryable_verification,
)
from services.document_alignment_processing_composition import (  # noqa: E402
    build_document_alignment_processing_dependencies,
)
from services.document_alignment_processing_orchestrator import (  # noqa: E402
    ProcessDocumentAlignmentWorkflowCommand,
    process_document_alignment_workflow,
)
from services.document_alignment_workflow_contract import (  # noqa: E402
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
)
from services.document_alignment_worker_handler import (  # noqa: E402
    run_claimed_formal_document_alignment_job,
)
from services.formal_background_job_execution import (  # noqa: E402
    complete_formal_background_job,
)


PAGINATION_TERMS = (
    "Abstraction", "Approximation", "Calibration", "Classification", "Computation",
    "Correlation", "Definition", "Demodulation", "Differentiation", "Estimation",
    "Formation", "Generation", "Integration", "Interpolation", "Modulation",
    "Normalization", "Optimization", "Prediction", "Quantization", "Regularization",
    "Representation", "Segmentation", "Simulation", "Synchronization", "Transformation",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_api_result(
    *,
    verdict: str,
    scenarios: list[dict[str, Any]],
    production_contract: dict[str, Any],
    external_requests: list[dict[str, str]],
    timeouts: list[str] | None = None,
    blocking_failures: list[str] | None = None,
    message: str = "",
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "message": message,
        "production_contract": production_contract,
        "scenarios": scenarios,
        "actual_external_dependency_requests": len(external_requests),
        "timeouts": list(timeouts or []),
        "blocking_failures": list(blocking_failures or []),
        "generated_at": utc_now(),
    }


def _post_run(base_url, auth, source_uid: str, key: str):
    return http_json(
        base_url,
        "/api/document-alignment-runs",
        method="POST",
        token=auth.token,
        opener=auth.opener,
        body={"source_uid": source_uid},
        headers={
            "Idempotency-Key": key,
            "X-Request-ID": f"formal-api-e2e-{key}",
        },
    )


def _source(runtime, suffix: str, terms: tuple[str, ...], bilingual_terms: dict[str, str]):
    module = runtime["app_module"]
    teacher_email = runtime["summary"]["users"]["teacher"]["email"]
    with module.app.app_context():
        return create_formal_source(
            module,
            suffix=suffix,
            terms=terms,
            bilingual_terms=bilingual_terms,
            owner_email=teacher_email,
            course_name=runtime["summary"]["course"],
        )


def _process_and_query(
    runtime,
    server,
    teacher,
    source,
    key,
    *,
    before_worker=None,
    timeout_seconds=10.0,
    poll_interval_seconds=0.05,
):
    module = runtime["app_module"]
    started = _post_run(server.base_url, teacher, source.source_uid, key)
    assert started.status == 202, started.body
    assert started.headers["Retry-After"] == "2"
    assert started.headers["Location"] == started.body["data"]["status_url"]
    run_uid = started.body["data"]["run_uid"]
    initial = http_json(server.base_url, started.headers["Location"], token=teacher.token)
    assert initial.status == 200
    if before_worker is not None:
        before_worker(run_uid)
    with module.app.app_context():
        worker = module.run_formal_worker_once(worker_id=f"formal-api-e2e-{key}")
        assert worker.outcome == "completed", worker
    polled = poll_until_terminal(
        lambda: http_json(
            server.base_url,
            started.headers["Location"],
            token=teacher.token,
        ).body,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    terminal = http_json(server.base_url, started.headers["Location"], token=teacher.token)
    items = http_json(
        server.base_url,
        started.body["data"]["items_url"],
        token=teacher.token,
    )
    assert terminal.status == items.status == 200
    assert_safe_public_payload(started.body)
    assert_safe_public_payload(terminal.body)
    assert_safe_public_payload(items.body)
    timeline = tuple(dict.fromkeys((initial.body["data"]["status"], *polled.timeline)))
    return started, terminal, items, timeline


def _start_recovery(runtime, server, teacher, suffix, terms):
    source = _source(
        runtime,
        f"script-recovery-{suffix}",
        terms,
        {term: f"恢复术语{index}" for index, term in enumerate(terms)},
    )
    response = _post_run(server.base_url, teacher, source.source_uid, f"recovery-{suffix}")
    assert response.status == 202
    run_uid = response.body["data"]["run_uid"]
    module = runtime["app_module"]
    with module.app.app_context():
        job_uid = find_job_for_run(module, run_uid).job_uid
    return run_uid, job_uid


def _query_recovery_state(server, teacher, run_uid: str, expected_status: str):
    run = http_json(
        server.base_url,
        f"/api/document-alignment-runs/{run_uid}",
        token=teacher.token,
        opener=teacher.opener,
    )
    items = http_json(
        server.base_url,
        f"/api/document-alignment-runs/{run_uid}/items",
        token=teacher.token,
        opener=teacher.opener,
    )
    assert run.status == items.status == 200
    assert run.body["data"]["status"] == expected_status
    assert_safe_public_payload(run.body)
    assert_safe_public_payload(items.body)
    return {
        "http_terminal_status": expected_status,
        "http_item_count": len(items.body["data"]["items"]),
    }


def assert_recovery_http_evidence(scenarios):
    required = {
        "retryable_requeue",
        "claim_crash_stale_reclaim",
        "partial_checkpoint_resume",
        "terminal_before_job_complete",
        "retry_exhaustion",
    }
    by_name = {scenario.get("name"): scenario for scenario in scenarios}
    assert required <= set(by_name)
    for name in required:
        scenario = by_name[name]
        assert "http_terminal_status" in scenario
        assert "http_item_count" in scenario
        assert scenario["http_terminal_status"] in {
            "ready_for_review",
            "completed_with_warnings",
            "blocked",
            "failed",
        }
        assert scenario["http_item_count"] >= 0


def _run_api_checks(
    *,
    database: Path,
    uploads: Path,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 1.0,
    external_requests: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime = run_quiet_e2e_setup(
        base_e2e,
        database,
        uploads,
        "formal_api_9c5g_v3",
    )
    module = runtime["app_module"]
    teacher_identity = runtime["summary"]["users"]["teacher"]
    student_identity = runtime["summary"]["users"]["student"]
    admin_identity = runtime["summary"]["users"]["admin"]
    scenarios: list[dict[str, Any]] = []
    recovery_scenarios: list[dict[str, Any]] = []
    production_contract: dict[str, Any] = {}
    external_requests = external_requests if external_requests is not None else []

    success = _source(
        runtime,
        "script-success",
        ("Abstraction", "Calibration"),
        {"Abstraction": "抽象", "Calibration": "校准"},
    )
    partial = _source(
        runtime,
        "script-partial",
        ("Computation", "Unmapped Course Term"),
        {"Computation": "计算"},
    )
    blocked = _source(
        runtime,
        "script-blocked",
        ("Unmapped Term Alpha", "Unmapped Term Beta"),
        {},
    )
    pagination = _source(
        runtime,
        "script-pagination",
        PAGINATION_TERMS,
        {term: f"分页术语{index:02d}" for index, term in enumerate(PAGINATION_TERMS)},
    )

    with start_threaded_server(module.app) as server, block_external_network(external_requests):
        teacher = login(server.base_url, teacher_identity["email"], teacher_identity["password"])
        student = login(server.base_url, student_identity["email"], student_identity["password"])
        admin = login(server.base_url, admin_identity["email"], admin_identity["password"])

        def audit_production_contract(run_uid):
            nonlocal production_contract
            with module.app.app_context():
                run = module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
                job = find_job_for_run(module, run_uid)
                payload = json.loads(job.input_json)
                assert run.workflow_version == "formal-document-alignment-v1"
                assert run.provider_preference == "mock-rule-v1"
                assert run.model_preference == "mock-rule-v1:v1"
                assert run.prompt_version == "alignment-v1"
                assert (run.status, run.stage) == ("queued", "queued")
                assert job.job_type == "formal_document_alignment_workflow_v1"
                assert (job.status, job.max_attempts) == ("queued", 3)
                assert (job.attempt_count, job.execution_attempt) == (0, 0)
                assert sorted(payload) == ["workflow_run_uid", "workflow_version"]
                production_contract = {
                    "workflow_version": run.workflow_version,
                    "provider_selection_frozen": True,
                    "background_job_type": job.job_type,
                    "retry_budget_policy": "three_execution_opportunities_two_requeues",
                    "initial_counters_verified": True,
                    "payload_identity_fields": sorted(payload),
                }

        started, terminal, items, timeline = _process_and_query(
            runtime,
            server,
            teacher,
            success,
            "normal",
            before_worker=audit_production_contract,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        run_uid = started.body["data"]["run_uid"]
        assert terminal.body["data"]["status"] == "ready_for_review"
        assert {item["status"] for item in items.body["data"]["items"]} == {"needs_review"}
        with module.app.app_context():
            job = find_job_for_run(module, run_uid)
            assert job.status == "completed"
        scenarios.append({
            "name": "normal_http_worker_polling",
            "status": "PASS",
            "run_uid": run_uid,
            "status_timeline": list(timeline),
            "terminal_status": terminal.body["data"]["status"],
            "item_count": len(items.body["data"]["items"]),
        })

        replay = _post_run(server.base_url, teacher, success.source_uid, "normal")
        assert replay.status == 202
        assert replay.body["data"]["reused"] is True
        assert replay.body["data"]["run_uid"] == run_uid
        scenarios.append({"name": "terminal_replay", "status": "PASS", "reused": True})

        _, partial_run, partial_items, partial_timeline = _process_and_query(
            runtime,
            server,
            teacher,
            partial,
            "partial",
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        assert partial_run.body["data"]["status"] == "completed_with_warnings"
        scenarios.append({
            "name": "partial_business_failure",
            "status": "PASS",
            "terminal_status": "completed_with_warnings",
            "status_timeline": list(partial_timeline),
            "item_count": len(partial_items.body["data"]["items"]),
        })

        _, blocked_run, blocked_items, _ = _process_and_query(
            runtime,
            server,
            teacher,
            blocked,
            "all-blocked",
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        assert blocked_run.body["data"]["status"] == "blocked"
        assert {item["status"] for item in blocked_items.body["data"]["items"]} == {"blocked"}
        scenarios.append({
            "name": "all_blocked",
            "status": "PASS",
            "terminal_status": "blocked",
            "item_count": len(blocked_items.body["data"]["items"]),
        })

        pagination_started, pagination_run, _, _ = _process_and_query(
            runtime,
            server,
            teacher,
            pagination,
            "pagination",
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        pagination_uid = pagination_started.body["data"]["run_uid"]
        page_one = http_json(
            server.base_url,
            f"/api/document-alignment-runs/{pagination_uid}/items?page=1&page_size=20",
            token=teacher.token,
        )
        page_two = http_json(
            server.base_url,
            f"/api/document-alignment-runs/{pagination_uid}/items?page=2&page_size=20",
            token=teacher.token,
        )
        assert pagination_run.body["data"]["total_items"] == 25
        assert len(page_one.body["data"]["items"]) == 20
        assert len(page_two.body["data"]["items"]) == 5
        scenarios.append({"name": "pagination", "status": "PASS", "total_items": 25})

        assert http_json(
            server.base_url,
            f"/api/document-alignment-runs/{run_uid}",
            token=admin.token,
        ).status == 200
        assert http_json(
            server.base_url,
            "/api/document-alignment-runs",
            method="POST",
            token=student.token,
            body={"source_uid": success.source_uid},
            headers={"Idempotency-Key": "student-denied"},
        ).status == 403
        assert http_json(
            server.base_url,
            f"/api/document-alignment-runs/{run_uid}",
            token=student.token,
        ).status == 403
        assert http_json(
            server.base_url,
            f"/api/document-alignment-runs/{run_uid}/items",
            token=student.token,
        ).status == 403
        scenarios.append({"name": "permissions", "status": "PASS", "student_denied": True})

        retry_uid, retry_job_uid = _start_recovery(
            runtime,
            server,
            teacher,
            "retryable",
            ("Validation", "Reconstruction"),
        )
        with module.app.app_context():
            first_lease = claim(module, "script-retry-a", expected_job_uid=retry_job_uid)
            first_result = run_claimed_with_retryable_verification(module, first_lease)
            second_lease = claim(module, "script-retry-b", expected_job_uid=retry_job_uid)
            second_result = run_claimed_formal_document_alignment_job(
                second_lease,
                module._formal_worker_handler_dependencies(second_lease),
            )
            retry_job = find_job_for_run(module, retry_uid)
            assert first_result.outcome == "requeued"
            assert second_result.outcome == "completed"
            assert retry_job.status == "completed"
            assert retry_job.attempt_count == 1
        retry_http = _query_recovery_state(server, teacher, retry_uid, "ready_for_review")
        recovery_scenarios.append({
            "name": "retryable_requeue",
            "status": "PASS",
            "failure_budget_consumed": 1,
            **retry_http,
        })

        stale_uid, stale_job_uid = _start_recovery(
            runtime,
            server,
            teacher,
            "stale",
            ("Compression", "Decomposition"),
        )
        with module.app.app_context():
            old_lease = claim(module, "script-stale-a", expected_job_uid=stale_job_uid)
            new_lease = reclaim_after_expiry(module, old_lease, "script-stale-b")
            assert complete_formal_background_job(
                old_lease,
                module._formal_job_execution_dependencies(),
            ).outcome == "stale_attempt"
            stale_result = run_claimed_formal_document_alignment_job(
                new_lease,
                module._formal_worker_handler_dependencies(new_lease),
            )
            stale_job = find_job_for_run(module, stale_uid)
            assert stale_result.outcome == "completed"
            assert stale_job.status == "completed"
            assert stale_job.attempt_count == 0
        stale_http = _query_recovery_state(server, teacher, stale_uid, "ready_for_review")
        recovery_scenarios.append({
            "name": "claim_crash_stale_reclaim",
            "status": "PASS",
            "failure_budget_consumed": 0,
            "old_owner_fenced": True,
            **stale_http,
        })

        partial_uid, partial_job_uid = _start_recovery(
            runtime,
            server,
            teacher,
            "partial",
            ("Detection", "Identification"),
        )
        with module.app.app_context():
            partial_old = claim(module, "script-partial-a", expected_job_uid=partial_job_uid)
            interrupted = process_until_first_item_then_crash(module, partial_old)
            before_counts = logical_counts(module, partial_uid)
            partial_new = reclaim_after_expiry(module, partial_old, "script-partial-b")
            resumed = run_claimed_formal_document_alignment_job(
                partial_new,
                module._formal_worker_handler_dependencies(partial_new),
            )
            after_counts = logical_counts(module, partial_uid)
            assert interrupted.outcome == "retryable_interruption"
            assert resumed.outcome == "completed"
            assert before_counts["needs_review"] == before_counts["usage"] == 1
            assert after_counts["needs_review"] == after_counts["usage"] == 2
            assert find_job_for_run(module, partial_uid).attempt_count == 0
        partial_http = _query_recovery_state(server, teacher, partial_uid, "ready_for_review")
        recovery_scenarios.append({
            "name": "partial_checkpoint_resume",
            "status": "PASS",
            "completed_items_before_crash": 1,
            "completed_items_after_resume": 2,
            **partial_http,
        })

        terminal_uid, terminal_job_uid = _start_recovery(
            runtime,
            server,
            teacher,
            "terminal",
            ("Convolution", "Distribution"),
        )
        with module.app.app_context():
            terminal_old = claim(module, "script-terminal-a", expected_job_uid=terminal_job_uid)
            dependencies = build_document_alignment_processing_dependencies(
                session=module.db.session,
                models=module._formal_processing_composition_models(),
                lease=terminal_old,
                term_extractor=module.extract_terms_from_text,
                current_time_factory=datetime.utcnow,
            )
            processed = process_document_alignment_workflow(
                ProcessDocumentAlignmentWorkflowCommand(
                    workflow_run_uid=terminal_uid,
                    job_uid=terminal_old.job_uid,
                    worker_id=terminal_old.worker_id,
                    execution_attempt=terminal_old.execution_attempt,
                    lease_token=terminal_old.lease_token,
                ),
                dependencies,
            )
            terminal_before = logical_counts(module, terminal_uid)
            assert processed.outcome == "ready_for_review"
            assert find_job_for_run(module, terminal_uid).status == "running"
            terminal_new = reclaim_after_expiry(module, terminal_old, "script-terminal-b")
            recovered = run_claimed_formal_document_alignment_job(
                terminal_new,
                module._formal_worker_handler_dependencies(terminal_new),
            )
            assert recovered.outcome == "completed"
            assert logical_counts(module, terminal_uid) == terminal_before
            assert find_job_for_run(module, terminal_uid).status == "completed"
        terminal_http = _query_recovery_state(server, teacher, terminal_uid, "ready_for_review")
        recovery_scenarios.append({
            "name": "terminal_before_job_complete",
            "status": "PASS",
            "business_records_reused": True,
            **terminal_http,
        })

        exhausted_uid, exhausted_job_uid = _start_recovery(
            runtime,
            server,
            teacher,
            "exhaustion",
            ("Adaptation", "Aggregation"),
        )
        with module.app.app_context():
            exhaustion_outcomes = []
            for index in range(3):
                lease = claim(
                    module,
                    f"script-exhaustion-{index}",
                    expected_job_uid=exhausted_job_uid,
                )
                exhaustion_outcomes.append(
                    run_claimed_with_retryable_verification(module, lease).outcome
                )
            run = module.DocumentAlignmentWorkflowRun.query.filter_by(
                run_uid=exhausted_uid
            ).one()
            job = find_job_for_run(module, exhausted_uid)
            assert exhaustion_outcomes == ["requeued", "requeued", "retry_exhausted"]
            assert (run.status, job.status, job.attempt_count) == ("failed", "failed", 3)
        exhausted_http = _query_recovery_state(server, teacher, exhausted_uid, "failed")
        recovery_scenarios.append({
            "name": "retry_exhaustion",
            "status": "PASS",
            "failure_budget_consumed": 3,
            "root_before_job": True,
            **exhausted_http,
        })

        concurrency_rounds = []
        for round_index in range(5):
            source = _source(
                runtime,
                f"script-concurrent-{round_index}",
                ("Quantization",),
                {"Quantization": "量化"},
            )
            first = login(server.base_url, teacher_identity["email"], teacher_identity["password"])
            second = login(server.base_url, teacher_identity["email"], teacher_identity["password"])
            barrier = threading.Barrier(2)

            def submit(auth):
                barrier.wait(timeout=5)
                return _post_run(
                    server.base_url,
                    auth,
                    source.source_uid,
                    f"concurrent-{round_index}",
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(submit, (first, second)))
            assert [response.status for response in responses] == [202, 202]
            run_uids = {response.body["data"]["run_uid"] for response in responses}
            assert len(run_uids) == 1
            assert sorted(response.body["data"]["reused"] for response in responses) == [
                False,
                True,
            ]
            concurrent_run_uid = next(iter(run_uids))
            with module.app.app_context():
                assert module.DocumentAlignmentWorkflowRun.query.filter_by(
                    source_uid=source.source_uid
                ).count() == 1
                assert module.BackgroundJob.query.filter(
                    module.BackgroundJob.job_type
                    == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
                    module.BackgroundJob.input_json.like(f"%{concurrent_run_uid}%"),
                ).count() == 1
                assert module.AuditRecord.query.filter_by(
                    target_uid=concurrent_run_uid,
                    event_type="document_alignment_requested",
                ).count() == 1
            concurrency_rounds.append({"round": round_index + 1, "status": "PASS"})
        scenarios.append({"name": "concurrent_replay", "status": "PASS", "rounds": concurrency_rounds})

        second_source = _source(
            runtime,
            "script-different-source",
            ("Interpretation",),
            {"Interpretation": "解释"},
        )
        other = _post_run(server.base_url, teacher, second_source.source_uid, "normal")
        assert other.status == 202
        assert other.body["data"]["reused"] is False
        assert other.body["data"]["run_uid"] != run_uid
        with module.app.app_context():
            stored_source = module.KnowledgeSource.query.filter_by(
                source_uid=success.source_uid
            ).one()
            stored_source.version = 2
            module.db.session.commit()
        conflict = _post_run(server.base_url, teacher, success.source_uid, "normal")
        assert conflict.status == 409
        scenarios.append({
            "name": "source_scoped_idempotency",
            "status": "PASS",
            "different_source_created_independent_run": True,
            "canonical_drift_conflict": True,
        })

    assert_recovery_http_evidence(recovery_scenarios)
    result = build_api_result(
        verdict="PASS",
        scenarios=scenarios,
        production_contract=production_contract,
        external_requests=external_requests,
    )
    recovery = {
        "verdict": "PASS",
        "scenarios": recovery_scenarios,
        "actual_external_dependency_requests": len(external_requests),
        "timeouts": [],
        "blocking_failures": [],
        "generated_at": utc_now(),
    }
    assert_safe_public_payload(result)
    assert_safe_public_payload(recovery)
    return result, recovery


def run_api_checks(
    *,
    database: Path,
    uploads: Path,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 1.0,
    external_requests: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    external_requests = external_requests if external_requests is not None else []
    with block_external_network(external_requests):
        return _run_api_checks(
            database=database,
            uploads=uploads,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            external_requests=external_requests,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True)
    parser.add_argument(
        "--recovery-json-output",
        default="/private/tmp/lexibridge-9c5g-v3-recovery.json",
    )
    parser.add_argument("--database-path")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)
    base_dir = Path(tempfile.mkdtemp(prefix="lexibridge-formal-api-e2e-"))
    database = Path(args.database_path).resolve() if args.database_path else base_dir / "formal-api.db"
    uploads = base_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    try:
        external_requests: list[dict[str, str]] = []
        try:
            result, recovery = run_api_checks(
                database=database,
                uploads=uploads,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
                external_requests=external_requests,
            )
            exit_code = 0
        except Exception as exc:
            result = build_api_result(
                verdict="FAIL",
                scenarios=[],
                production_contract={},
                external_requests=external_requests,
                blocking_failures=[type(exc).__name__],
                message="Formal document alignment API E2E failed.",
            )
            recovery = {
                "verdict": "FAIL",
                "message": "Formal document alignment recovery E2E failed.",
                "scenarios": [],
                "actual_external_dependency_requests": len(external_requests),
                "timeouts": [],
                "blocking_failures": [type(exc).__name__],
                "generated_at": utc_now(),
            }
            exit_code = 1
        assert_safe_public_payload(result)
        assert_safe_public_payload(recovery)
        Path(args.json_output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        Path(args.recovery_json_output).write_text(
            json.dumps(recovery, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    finally:
        if not args.database_path:
            shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
