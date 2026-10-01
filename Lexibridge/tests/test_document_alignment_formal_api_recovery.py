from datetime import datetime

import pytest

from formal_document_alignment_retry_support import (
    claim,
    logical_counts,
    process_until_first_item_then_crash,
    reclaim_after_expiry,
    run_claimed_with_retryable_verification,
)
from scripts.formal_document_alignment_api_e2e_support import (
    cleanup_formal_api_state,
    create_formal_source,
    find_job_for_run,
    http_json,
    login,
    start_threaded_server,
)
from services.document_alignment_processing_composition import (
    build_document_alignment_processing_dependencies,
)
from services.document_alignment_processing_orchestrator import (
    ProcessDocumentAlignmentWorkflowCommand,
    process_document_alignment_workflow,
)
from services.document_alignment_worker_handler import (
    run_claimed_formal_document_alignment_job,
)
from services.formal_background_job_execution import (
    complete_formal_background_job,
    fail_formal_background_job,
    requeue_formal_background_job,
)


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)


_RECOVERY_TERMS = {
    "retry-0": ("Abstraction", "Approximation"),
    "retry-1": ("Calibration", "Classification"),
    "retry-2": ("Computation", "Correlation"),
    "retry-3": ("Definition", "Demodulation"),
    "retry-4": ("Differentiation", "Estimation"),
    "claim-crash": ("Formation", "Generation"),
    "partial-crash": ("Integration", "Interpolation"),
    "terminal-crash": ("Modulation", "Normalization"),
    "exhaustion": ("Optimization", "Prediction"),
}


def _start(server, app_module, teacher, suffix):
    terms = _RECOVERY_TERMS[suffix]
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix=suffix,
            terms=terms,
            bilingual_terms={term: f"恢复术语{index}" for index, term in enumerate(terms)},
        )
    response = http_json(
        server.base_url,
        "/api/document-alignment-runs",
        method="POST",
        token=teacher.token,
        body={"source_uid": source.source_uid},
        headers={"Idempotency-Key": f"recovery-{suffix}"},
    )
    assert response.status == 202
    run_uid = response.body["data"]["run_uid"]
    with app_module.app.app_context():
        job_uid = find_job_for_run(app_module, run_uid).job_uid
    return run_uid, job_uid


def test_real_http_retryable_requeue_and_next_claim_recovers_five_rounds(app_module):
    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        for round_index in range(5):
            run_uid, job_uid = _start(server, app_module, teacher, f"retry-{round_index}")
            with app_module.app.app_context():
                first_lease = claim(
                    app_module,
                    f"retry-worker-a-{round_index}",
                    expected_job_uid=job_uid,
                )
                first = run_claimed_with_retryable_verification(app_module, first_lease)
                app_module.db.session.expire_all()
                job = find_job_for_run(app_module, run_uid)
                assert first.outcome == "requeued"
                assert job.status == "retrying"
                assert job.attempt_count == 1
                assert job.execution_attempt == 1

                second_lease = claim(
                    app_module,
                    f"retry-worker-b-{round_index}",
                    expected_job_uid=job_uid,
                )
                second = run_claimed_formal_document_alignment_job(
                    second_lease,
                    app_module._formal_worker_handler_dependencies(second_lease),
                )
                app_module.db.session.expire_all()
                job = find_job_for_run(app_module, run_uid)
                assert second.outcome == "completed"
                assert second_lease.execution_attempt == 2
                assert job.status == "completed"
                assert job.attempt_count == 1
                # Legacy inline bilingual evidence is held for review before
                # Provider execution by the Task 12H readiness gate.
                assert logical_counts(app_module, run_uid)["usage"] == 0


def test_claim_crash_stale_reclaim_fences_every_old_attempt_finalizer(app_module):
    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        run_uid, job_uid = _start(server, app_module, teacher, "claim-crash")
        with app_module.app.app_context():
            old_lease = claim(app_module, "claim-crash-worker-a", expected_job_uid=job_uid)
            new_lease = reclaim_after_expiry(
                app_module,
                old_lease,
                "claim-crash-worker-b",
            )
            dependencies = app_module._formal_job_execution_dependencies()
            assert complete_formal_background_job(old_lease, dependencies).outcome == "stale_attempt"
            assert fail_formal_background_job(
                old_lease,
                dependencies,
                "STALE_TEST",
                "Safe stale test.",
            ).outcome == "stale_attempt"
            assert requeue_formal_background_job(
                old_lease,
                dependencies,
                "STALE_TEST",
                "Safe stale test.",
            ).outcome == "stale_attempt"

            result = run_claimed_formal_document_alignment_job(
                new_lease,
                app_module._formal_worker_handler_dependencies(new_lease),
            )
            app_module.db.session.expire_all()
            job = find_job_for_run(app_module, run_uid)
            assert result.outcome == "completed"
            assert new_lease.execution_attempt == 2
            assert job.attempt_count == 0
            assert job.status == "completed"
            assert logical_counts(app_module, run_uid)["usage"] == 0


def test_partial_checkpoint_crash_resumes_without_duplicate_logical_records(app_module):
    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        run_uid, job_uid = _start(server, app_module, teacher, "partial-crash")
        with app_module.app.app_context():
            old_lease = claim(app_module, "partial-crash-worker-a", expected_job_uid=job_uid)
            interrupted = process_until_first_item_then_crash(app_module, old_lease)
            before = logical_counts(app_module, run_uid)
            assert interrupted.outcome == "retryable_interruption"
            assert before["needs_review"] == 1
            assert before["usage"] == 0
            assert find_job_for_run(app_module, run_uid).attempt_count == 0

            new_lease = reclaim_after_expiry(
                app_module,
                old_lease,
                "partial-crash-worker-b",
            )
            result = run_claimed_formal_document_alignment_job(
                new_lease,
                app_module._formal_worker_handler_dependencies(new_lease),
            )
            after = logical_counts(app_module, run_uid)
            assert result.outcome == "completed"
            assert after["items"] == after["needs_review"] == 2
            assert after["preflights"] == after["verifications"] == after["usage"] == 0
            assert find_job_for_run(app_module, run_uid).attempt_count == 0


def test_terminal_root_before_job_complete_is_recovered_by_new_owner(app_module):
    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        run_uid, job_uid = _start(server, app_module, teacher, "terminal-crash")
        with app_module.app.app_context():
            old_lease = claim(app_module, "terminal-crash-worker-a", expected_job_uid=job_uid)
            processing_dependencies = build_document_alignment_processing_dependencies(
                session=app_module.db.session,
                models=app_module._formal_processing_composition_models(),
                lease=old_lease,
                term_extractor=app_module.extract_terms_from_text,
                current_time_factory=datetime.utcnow,
            )
            command = ProcessDocumentAlignmentWorkflowCommand(
                workflow_run_uid=run_uid,
                job_uid=old_lease.job_uid,
                worker_id=old_lease.worker_id,
                execution_attempt=old_lease.execution_attempt,
                lease_token=old_lease.lease_token,
            )
            processed = process_document_alignment_workflow(command, processing_dependencies)
            before = logical_counts(app_module, run_uid)
            assert processed.outcome == "ready_for_review"
            assert find_job_for_run(app_module, run_uid).status == "running"

            new_lease = reclaim_after_expiry(
                app_module,
                old_lease,
                "terminal-crash-worker-b",
            )
            result = run_claimed_formal_document_alignment_job(
                new_lease,
                app_module._formal_worker_handler_dependencies(new_lease),
            )
            after = logical_counts(app_module, run_uid)
            assert result.outcome == "completed"
            assert before == after
            assert find_job_for_run(app_module, run_uid).status == "completed"


def test_real_admission_retry_exhaustion_is_root_first_and_terminal(app_module):
    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        run_uid, job_uid = _start(server, app_module, teacher, "exhaustion")
        with app_module.app.app_context():
            leases = []
            outcomes = []
            for index in range(3):
                lease = claim(
                    app_module,
                    f"exhaustion-worker-{index}",
                    expected_job_uid=job_uid,
                )
                leases.append(lease)
                outcomes.append(run_claimed_with_retryable_verification(app_module, lease))
            app_module.db.session.expire_all()
            run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
            job = find_job_for_run(app_module, run_uid)
            assert [result.outcome for result in outcomes] == [
                "requeued",
                "requeued",
                "retry_exhausted",
            ]
            assert (run.status, run.stage) == ("failed", "terminal")
            assert (job.status, job.attempt_count, job.execution_attempt) == ("failed", 3, 3)
            assert complete_formal_background_job(
                leases[-1],
                app_module._formal_job_execution_dependencies(),
            ).outcome == "terminal_immutable"
