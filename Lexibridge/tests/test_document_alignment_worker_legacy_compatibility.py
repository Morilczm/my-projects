from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.document_alignment_worker_handler import (
    OUTCOME_COMPLETED,
    OUTCOME_NO_JOB_AVAILABLE,
    RunFormalDocumentAlignmentJobResult,
)
from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
from services.formal_background_job_dispatch import (
    FormalBackgroundJobDispatchDependencies,
    run_one_formal_document_alignment_job,
)
from services.formal_background_job_execution import (
    CLAIM_OUTCOME_CLAIMED,
    CLAIM_OUTCOME_NO_JOB_AVAILABLE,
    ClaimFormalJobResult,
    FormalJobExecutionLease,
)


NOW = datetime(2026, 7, 19, 10, 0, 0)


def _lease():
    return FormalJobExecutionLease(
        job_uid="dispatch-formal-job",
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        worker_id="dispatch-worker",
        execution_attempt=1,
        lease_token="dispatch-secret-token",
        claimed_at=NOW,
        heartbeat_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
        status="running",
    )


def test_dispatch_dependencies_are_frozen_and_no_job_does_not_call_handler():
    dependencies = FormalBackgroundJobDispatchDependencies(
        claim=lambda worker_id: ClaimFormalJobResult(outcome=CLAIM_OUTCOME_NO_JOB_AVAILABLE),
        handle=lambda lease: pytest.fail("handler must not run without a claimed lease"),
    )
    with pytest.raises(FrozenInstanceError):
        dependencies.claim = None

    result = run_one_formal_document_alignment_job("dispatch-worker", dependencies)

    assert result.outcome == OUTCOME_NO_JOB_AVAILABLE
    assert result.job_uid == ""


def test_dispatch_passes_one_cas_claimed_lease_to_handler():
    calls = []
    lease = _lease()
    dependencies = FormalBackgroundJobDispatchDependencies(
        claim=lambda worker_id: calls.append(("claim", worker_id)) or ClaimFormalJobResult(
            outcome=CLAIM_OUTCOME_CLAIMED,
            lease=lease,
        ),
        handle=lambda received: calls.append(("handle", received.execution_attempt))
        or RunFormalDocumentAlignmentJobResult(
            outcome=OUTCOME_COMPLETED,
            job_uid=received.job_uid,
            workflow_run_uid="dispatch-run",
            job_status="completed",
            run_status="ready_for_review",
            run_stage="terminal",
            execution_attempt=received.execution_attempt,
            completed=True,
        ),
    )

    result = run_one_formal_document_alignment_job("dispatch-worker", dependencies)

    assert result.outcome == OUTCOME_COMPLETED
    assert calls == [("claim", "dispatch-worker"), ("handle", 1)]


def test_formal_dispatch_has_no_processing_or_legacy_worker_logic():
    source = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "services"
        / "formal_background_job_dispatch.py"
    ).read_text(encoding="utf-8")
    assert "claim_next_background_job" not in source
    assert "process_document_alignment_workflow" not in source
    assert "run_background_job" not in source
    assert "legacy" not in source.lower()


def test_formal_and_generic_claims_exclude_the_other_job_family(app_module):
    with app_module.app.app_context():
        app_module.db.session.rollback()
        formal = app_module.BackgroundJob(
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            status="queued",
            priority=1,
            created_by=1,
            input_json='{"workflow_run_uid":"legacy-compat-formal","workflow_version":"formal-document-alignment-v1"}',
            result_json="{}",
            attempt_count=0,
            max_attempts=2,
            created_at="2026-07-19 10:59:00",
            updated_at="2026-07-19 10:59:00",
        )
        legacy = app_module.BackgroundJob(
            job_type="unknown-legacy-9c5d",
            status="queued",
            priority=2,
            created_by=1,
            input_json='{"marker":"legacy-compat-9c5d"}',
            result_json="{}",
            attempt_count=0,
            max_attempts=2,
            created_at="2026-07-19 10:59:00",
            updated_at="2026-07-19 10:59:00",
        )
        app_module.db.session.add_all([formal, legacy])
        app_module.db.session.commit()

        claimed_legacy = app_module.claim_next_background_job("legacy-compat-worker")
        app_module.db.session.expire_all()
        stored_formal = app_module.db.session.get(app_module.BackgroundJob, formal.id)
        assert claimed_legacy.id == legacy.id
        assert stored_formal.status == "queued"

        claimed_legacy.status = "queued"
        claimed_legacy.locked_by = ""
        app_module.db.session.commit()
        formal_result = app_module.run_formal_worker_once("formal-compat-worker")
        app_module.db.session.expire_all()
        stored_legacy = app_module.db.session.get(app_module.BackgroundJob, legacy.id)
        assert formal_result.job_uid == stored_formal.job_uid
        assert stored_legacy.status == "queued"

        job_ids = [formal.id, legacy.id]
        app_module.BackgroundJobEvent.query.filter(
            app_module.BackgroundJobEvent.job_id.in_(job_ids)
        ).delete(synchronize_session=False)
        app_module.BackgroundJob.query.filter(app_module.BackgroundJob.id.in_(job_ids)).delete(
            synchronize_session=False
        )
        app_module.db.session.commit()


def test_local_worker_loop_uses_explicit_queue_family_modes():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "run_worker.py").read_text(
        encoding="utf-8"
    )
    assert "prefer_formal = True" in source
    assert "run_formal_worker_once" in source
    assert "run_generic_background_worker_once" in source
    assert "run_legacy_alignment_worker_once" in source
    assert 'mode == "standard"' in source
    assert 'mode == "legacy-alignment"' in source
    assert "app_module.run_worker_once" not in source
