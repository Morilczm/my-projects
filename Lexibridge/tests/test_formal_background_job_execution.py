import inspect
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
from services.formal_background_job_execution import (
    CLAIM_OUTCOME_CLAIMED,
    CLAIM_OUTCOME_NO_JOB_AVAILABLE,
    FORMAL_JOB_DEFAULT_LEASE_SECONDS,
    LEASE_OUTCOME_ACCEPTED,
    LEASE_OUTCOME_LEASE_EXPIRED,
    LEASE_OUTCOME_LEASE_NOT_OWNED,
    LEASE_OUTCOME_STALE_ATTEMPT,
    LEASE_OUTCOME_TERMINAL_IMMUTABLE,
    ClaimFormalJobResult,
    FormalBackgroundJobExecutionDependencies,
    FormalJobExecutionFence,
    FormalJobExecutionLease,
    FormalJobLeaseOperationResult,
    claim_next_formal_background_job,
    complete_formal_background_job,
    fail_formal_background_job,
    fence_active_formal_job_lease_in_transaction,
    heartbeat_formal_background_job,
    requeue_formal_background_job,
    validate_active_formal_job_lease,
)


NOW = datetime(2026, 7, 18, 8, 0, 0)
ROOT = Path(__file__).resolve().parents[1]


class _FailCommitOnce:
    def __init__(self, session):
        self._session = session
        self.failed = False
        self.rollback_count = 0

    def __getattr__(self, name):
        return getattr(self._session, name)

    def commit(self):
        if not self.failed:
            self.failed = True
            raise RuntimeError("commit unavailable")
        return self._session.commit()

    def rollback(self):
        self.rollback_count += 1
        return self._session.rollback()


def _formal_job(app_module, **overrides):
    values = {
        "job_type": FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        "status": "queued",
        "priority": 100,
        "created_by": 1,
        "input_json": "{}",
        "result_json": "{}",
        "progress_current": 0,
        "progress_total": 100,
        "progress_message": "Queued",
        "attempt_count": 0,
        "max_attempts": 3,
        "created_at": "2026-07-18 07:59:00",
        "updated_at": "2026-07-18 07:59:00",
    }
    values.update(overrides)
    return app_module.BackgroundJob(**values)


def _dependencies(app_module, *, now=NOW, token="lease-token-9c4z", session=None):
    return FormalBackgroundJobExecutionDependencies(
        session=session or app_module.db.session,
        job_model=app_module.BackgroundJob,
        current_time_factory=lambda: now,
        lease_token_factory=lambda: token,
    )


def _cleanup(app_module):
    app_module.db.session.rollback()
    app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete()
    app_module.db.session.commit()
    app_module.db.session.expunge_all()


def test_module_boundary_dtos_and_lease_policy_are_explicit():
    import services.formal_background_job_execution as service

    source = inspect.getsource(service)
    assert "flask" not in source.lower()
    assert "backend.app" not in source
    for forbidden in ("urllib", "requests", "httpx", "socket", "credential", "provider"):
        assert forbidden not in source.lower()
    assert FORMAL_JOB_DEFAULT_LEASE_SECONDS == 30

    lease = FormalJobExecutionLease(
        job_uid="job-repr",
        job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        worker_id="worker-a",
        execution_attempt=1,
        lease_token="LEXIBRIDGE_SENTINEL_SECRET_9C5A",
        claimed_at=NOW,
        heartbeat_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
        status="running",
    )
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5A" not in repr(lease)
    fence = FormalJobExecutionFence(
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5A" not in repr(fence)

    for value in (
        FormalJobExecutionLease(
            job_uid="job-1",
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            worker_id="worker-a",
            execution_attempt=1,
            lease_token="opaque-token",
            claimed_at=NOW,
            heartbeat_at=NOW,
            lease_expires_at=NOW + timedelta(seconds=30),
            status="running",
        ),
        ClaimFormalJobResult(outcome="no_job_available"),
        FormalJobLeaseOperationResult(outcome="accepted", job_uid="job-1"),
        FormalBackgroundJobExecutionDependencies(
            session=object(),
            job_model=object(),
            current_time_factory=lambda: NOW,
            lease_token_factory=lambda: "token",
        ),
    ):
        with pytest.raises(FrozenInstanceError):
            value.outcome = "changed" if hasattr(value, "outcome") else "changed"


def test_formal_job_schema_has_stable_uid_and_attempt_owned_lease_fields(app_module):
    columns = app_module.BackgroundJob.__table__.columns
    assert {"job_uid", "execution_attempt", "lease_token", "heartbeat_at", "lease_expires_at"} <= set(columns.keys())
    assert columns.job_uid.unique is True
    assert columns.job_uid.index is True
    assert "locked_by" in columns
    assert "locked_at" in columns


def test_claim_is_formal_only_and_populates_attempt_owned_lease(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        formal = _formal_job(app_module)
        legacy = _formal_job(app_module, job_type="document_ingestion")
        app_module.db.session.add_all([formal, legacy])
        app_module.db.session.commit()

        result = claim_next_formal_background_job("worker-a", _dependencies(app_module))
        app_module.db.session.expire_all()
        claimed = app_module.db.session.get(app_module.BackgroundJob, formal.id)
        untouched = app_module.db.session.get(app_module.BackgroundJob, legacy.id)

        assert result.outcome == CLAIM_OUTCOME_CLAIMED
        assert result.lease is not None
        assert result.lease.job_uid == claimed.job_uid
        assert result.lease.worker_id == "worker-a"
        assert result.lease.execution_attempt == 1
        assert result.lease.lease_token == "lease-token-9c4z"
        assert result.lease.claimed_at == NOW
        assert result.lease.heartbeat_at == NOW
        assert result.lease.lease_expires_at == NOW + timedelta(seconds=30)
        assert claimed.status == "running"
        assert claimed.locked_by == "worker-a"
        assert claimed.execution_attempt == 1
        assert claimed.attempt_count == 0
        assert claimed.lease_token == "lease-token-9c4z"
        assert untouched.status == "queued"

        none_left = claim_next_formal_background_job("worker-b", _dependencies(app_module, token="other"))
        assert none_left.outcome == CLAIM_OUTCOME_NO_JOB_AVAILABLE
        _cleanup(app_module)


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "canceled"])
def test_terminal_formal_job_is_never_claimed_or_mutated(app_module, terminal_status):
    with app_module.app.app_context():
        _cleanup(app_module)
        job = _formal_job(
            app_module,
            status=terminal_status,
            execution_attempt=4,
            attempt_count=4,
            finished_at="2026-07-18 07:59:30",
        )
        app_module.db.session.add(job)
        app_module.db.session.commit()

        result = claim_next_formal_background_job("worker-a", _dependencies(app_module))
        app_module.db.session.expire_all()
        stored = app_module.db.session.get(app_module.BackgroundJob, job.id)

        assert result.outcome == CLAIM_OUTCOME_NO_JOB_AVAILABLE
        assert stored.status == terminal_status
        assert stored.execution_attempt == 4
        assert stored.attempt_count == 4
        _cleanup(app_module)


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "canceled"])
@pytest.mark.parametrize("operation", ["heartbeat", "complete", "fail", "requeue"])
def test_every_terminal_status_rejects_every_ownership_operation(app_module, terminal_status, operation):
    with app_module.app.app_context():
        _cleanup(app_module)
        job = _formal_job(app_module)
        app_module.db.session.add(job)
        app_module.db.session.commit()
        lease = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease
        job.status = terminal_status
        job.finished_at = "2026-07-18 08:00:01"
        app_module.db.session.commit()

        operations = {
            "heartbeat": lambda: heartbeat_formal_background_job(lease, _dependencies(app_module)),
            "complete": lambda: complete_formal_background_job(lease, _dependencies(app_module)),
            "fail": lambda: fail_formal_background_job(lease, _dependencies(app_module), "SAFE", "safe"),
            "requeue": lambda: requeue_formal_background_job(lease, _dependencies(app_module), "SAFE", "safe"),
        }
        result = operations[operation]()
        app_module.db.session.expire_all()
        stored = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()
        assert result.outcome == LEASE_OUTCOME_TERMINAL_IMMUTABLE
        assert stored.status == terminal_status
        _cleanup(app_module)


def test_transaction_fence_is_conditional_and_transaction_neutral(app_module):
    class CountTransactions:
        def __init__(self, session):
            self._session = session
            self.commit_count = 0
            self.rollback_count = 0

        def __getattr__(self, name):
            return getattr(self._session, name)

        def commit(self):
            self.commit_count += 1
            return self._session.commit()

        def rollback(self):
            self.rollback_count += 1
            return self._session.rollback()

    with app_module.app.app_context():
        _cleanup(app_module)
        app_module.db.session.add(_formal_job(app_module))
        app_module.db.session.commit()
        lease = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease
        wrapped = CountTransactions(app_module.db.session)

        result = fence_active_formal_job_lease_in_transaction(
            lease,
            _dependencies(app_module, now=NOW + timedelta(seconds=5), session=wrapped),
            lease_extension_seconds=30,
        )

        assert result.outcome == LEASE_OUTCOME_ACCEPTED
        assert wrapped.commit_count == 0
        assert wrapped.rollback_count == 0
        app_module.db.session.rollback()
        _cleanup(app_module)


def test_heartbeat_guard_and_wrong_owner_rejections(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        job = _formal_job(app_module)
        app_module.db.session.add(job)
        app_module.db.session.commit()
        lease = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease

        heartbeat_time = NOW + timedelta(seconds=10)
        heartbeat = heartbeat_formal_background_job(lease, _dependencies(app_module, now=heartbeat_time))
        app_module.db.session.expire_all()
        stored = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()

        assert heartbeat.outcome == LEASE_OUTCOME_ACCEPTED
        assert heartbeat.execution_attempt == 1
        assert heartbeat.lease_expires_at == heartbeat_time + timedelta(seconds=30)
        assert stored.execution_attempt == 1
        assert stored.lease_token == lease.lease_token

        active = validate_active_formal_job_lease(lease, _dependencies(app_module, now=heartbeat_time))
        wrong_worker = FormalJobExecutionLease(**{**lease.__dict__, "worker_id": "worker-b"})
        wrong_token = FormalJobExecutionLease(**{**lease.__dict__, "lease_token": "wrong"})
        assert active.outcome == LEASE_OUTCOME_ACCEPTED
        assert heartbeat_formal_background_job(wrong_worker, _dependencies(app_module, now=heartbeat_time)).outcome == LEASE_OUTCOME_LEASE_NOT_OWNED
        assert heartbeat_formal_background_job(wrong_token, _dependencies(app_module, now=heartbeat_time)).outcome == LEASE_OUTCOME_LEASE_NOT_OWNED
        _cleanup(app_module)


def test_expired_lease_reclaim_fences_every_old_attempt_operation(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        app_module.db.session.add(_formal_job(app_module))
        app_module.db.session.commit()
        old_lease = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease
        expiry = old_lease.lease_expires_at

        assert heartbeat_formal_background_job(old_lease, _dependencies(app_module, now=expiry)).outcome == LEASE_OUTCOME_LEASE_EXPIRED

        new_lease = claim_next_formal_background_job(
            "worker-b",
            _dependencies(app_module, now=expiry, token="new-token-9c4z"),
        ).lease
        assert new_lease.execution_attempt == 2
        assert new_lease.lease_token == "new-token-9c4z"
        app_module.db.session.expire_all()
        reclaimed = app_module.BackgroundJob.query.filter_by(job_uid=new_lease.job_uid).one()
        assert reclaimed.attempt_count == 0

        for operation in (
            heartbeat_formal_background_job,
            complete_formal_background_job,
            lambda lease, deps: fail_formal_background_job(lease, deps, "SAFE_FAILURE", "safe failure"),
            lambda lease, deps: requeue_formal_background_job(lease, deps, "SAFE_RETRY", "safe retry"),
        ):
            result = operation(old_lease, _dependencies(app_module, now=expiry + timedelta(seconds=1)))
            assert result.outcome == LEASE_OUTCOME_STALE_ATTEMPT
            assert result.error_code == "FORMAL_JOB_STALE_EXECUTION_ATTEMPT"

        accepted = complete_formal_background_job(
            new_lease,
            _dependencies(app_module, now=expiry + timedelta(seconds=1)),
        )
        assert accepted.outcome == LEASE_OUTCOME_ACCEPTED
        assert accepted.status == "completed"
        terminal = heartbeat_formal_background_job(
            new_lease,
            _dependencies(app_module, now=expiry + timedelta(seconds=2)),
        )
        assert terminal.outcome == LEASE_OUTCOME_TERMINAL_IMMUTABLE
        _cleanup(app_module)


def test_fail_retry_max_attempts_and_safe_error_boundary(app_module):
    sentinel = "LEXIBRIDGE_SENTINEL_SECRET_9C4Z"
    with app_module.app.app_context():
        _cleanup(app_module)
        app_module.db.session.add(_formal_job(app_module, max_attempts=2))
        app_module.db.session.commit()
        first = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease

        retry = requeue_formal_background_job(
            first,
            _dependencies(app_module, now=NOW + timedelta(seconds=1)),
            "TRANSIENT",
            f"Authorization: Bearer {sentinel}",
        )
        assert retry.outcome == LEASE_OUTCOME_ACCEPTED
        assert retry.status == "retrying"

        second = claim_next_formal_background_job(
            "worker-b",
            _dependencies(app_module, now=NOW + timedelta(seconds=2), token="second-token"),
        ).lease
        exhausted = requeue_formal_background_job(
            second,
            _dependencies(app_module, now=NOW + timedelta(seconds=3)),
            "TRANSIENT",
            f"Cookie: {sentinel}",
        )
        app_module.db.session.expire_all()
        stored = app_module.BackgroundJob.query.filter_by(job_uid=second.job_uid).one()

        assert exhausted.outcome == "retry_exhausted"
        assert exhausted.status == "running"
        assert stored.status == "running"
        assert stored.attempt_count == 1
        assert sentinel not in stored.error_message
        assert sentinel not in exhausted.error_message
        _cleanup(app_module)


def test_permanent_failure_consumes_one_business_attempt(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        app_module.db.session.add(_formal_job(app_module, max_attempts=3))
        app_module.db.session.commit()
        lease = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease

        failed = fail_formal_background_job(
            lease,
            _dependencies(app_module, now=NOW + timedelta(seconds=1)),
            "SAFE_FAILURE",
            "safe failure",
        )
        app_module.db.session.expire_all()
        stored = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()

        assert failed.outcome == LEASE_OUTCOME_ACCEPTED
        assert stored.status == "failed"
        assert stored.attempt_count == 1
        _cleanup(app_module)


def test_formal_ownership_operations_do_not_write_business_records(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        before = {
            "workflow_runs": app_module.DocumentAlignmentWorkflowRun.query.count(),
            "workflow_items": app_module.DocumentAlignmentWorkflowItem.query.count(),
            "cards": app_module.ConceptAlignmentCard.query.count(),
            "verification": app_module.AlignmentVerificationRun.query.count(),
            "usage": app_module.UsageRecord.query.count(),
            "legacy_runs": app_module.AlignmentRun.query.count(),
            "legacy_cards": app_module.TerminologyCard.query.count(),
            "calls": app_module.AICallLog.query.count(),
            "audits": app_module.AuditRecord.query.count(),
        }
        app_module.db.session.add(_formal_job(app_module))
        app_module.db.session.commit()
        lease = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease
        failed = fail_formal_background_job(
            lease,
            _dependencies(app_module, now=NOW + timedelta(seconds=1)),
            "SAFE",
            "safe",
        )
        after = {
            "workflow_runs": app_module.DocumentAlignmentWorkflowRun.query.count(),
            "workflow_items": app_module.DocumentAlignmentWorkflowItem.query.count(),
            "cards": app_module.ConceptAlignmentCard.query.count(),
            "verification": app_module.AlignmentVerificationRun.query.count(),
            "usage": app_module.UsageRecord.query.count(),
            "legacy_runs": app_module.AlignmentRun.query.count(),
            "legacy_cards": app_module.TerminologyCard.query.count(),
            "calls": app_module.AICallLog.query.count(),
            "audits": app_module.AuditRecord.query.count(),
        }
        assert failed.outcome == LEASE_OUTCOME_ACCEPTED
        assert after == before
        _cleanup(app_module)


def test_claim_commit_failure_rolls_back_and_session_remains_reusable(app_module):
    with app_module.app.app_context():
        _cleanup(app_module)
        job = _formal_job(app_module)
        app_module.db.session.add(job)
        app_module.db.session.commit()
        wrapped = _FailCommitOnce(app_module.db.session)

        result = claim_next_formal_background_job(
            "worker-a",
            _dependencies(app_module, session=wrapped),
        )

        assert result.outcome == "persistence_error"
        assert wrapped.rollback_count == 1
        app_module.db.session.expire_all()
        stored = app_module.db.session.get(app_module.BackgroundJob, job.id)
        assert stored.status == "queued"
        assert stored.execution_attempt == 0
        assert app_module.BackgroundJob.query.count() >= 1
        _cleanup(app_module)


@pytest.mark.parametrize("operation", ["heartbeat", "complete", "requeue"])
def test_lease_mutation_commit_failure_rolls_back_and_session_remains_reusable(app_module, operation):
    with app_module.app.app_context():
        _cleanup(app_module)
        app_module.db.session.add(_formal_job(app_module))
        app_module.db.session.commit()
        lease = claim_next_formal_background_job("worker-a", _dependencies(app_module)).lease
        wrapped = _FailCommitOnce(app_module.db.session)
        dependencies = _dependencies(
            app_module,
            now=NOW + timedelta(seconds=1),
            session=wrapped,
        )
        operations = {
            "heartbeat": lambda: heartbeat_formal_background_job(lease, dependencies),
            "complete": lambda: complete_formal_background_job(lease, dependencies),
            "requeue": lambda: requeue_formal_background_job(lease, dependencies, "TRANSIENT", "safe retry"),
        }

        result = operations[operation]()
        app_module.db.session.expire_all()
        stored = app_module.BackgroundJob.query.filter_by(job_uid=lease.job_uid).one()

        assert result.outcome == "persistence_error"
        assert wrapped.rollback_count == 1
        assert stored.status == "running"
        assert stored.execution_attempt == lease.execution_attempt
        assert stored.lease_token == lease.lease_token
        assert app_module.BackgroundJob.query.count() >= 1
        _cleanup(app_module)


def test_execution_ownership_docs_freeze_guarantees_limits_and_next_blocker():
    paths = (
        ROOT / "docs" / "formal_background_job_execution_ownership.md",
        ROOT / "docs" / "formal_document_alignment_workflow_boundary.md",
        ROOT / "docs" / "adr" / "ADR-formal-document-alignment-workflow.md",
        ROOT / "docs" / "technical_debt_register.md",
        ROOT / "README.md",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for term in (
        "FORMAL_BACKGROUND_JOB_EXECUTION_OWNERSHIP_ESTABLISHED_FOR_LOCAL_PILOT",
        "FORMAL_JOB_EXECUTION_OWNERSHIP_ESTABLISHED",
        "AT_LEAST_ONCE_TRANSPORT",
        "ATTEMPT_FENCED_OWNERSHIP",
        "FORMAL_JOB_DEFAULT_LEASE_SECONDS = 30",
        "lease_expires_at <= now",
        "SINGLE_NODE_CLOCK_TRUSTED_FOR_PILOT",
        "DATABASE_TIME_REQUIRED_FOR_DISTRIBUTED_PRODUCTION",
        "PILOT_CREATE_ALL_ONLY",
        "FORMAL_MIGRATION_REQUIRED_BEFORE_PRODUCTION",
        "CANCELLATION_OUT_OF_SCOPE_FOR_9C4Z",
        "POSTGRESQL_LEASE_SEMANTICS_NOT_VERIFIED",
        "FORMAL_CHUNK_SCOPED_ITEM_BOOTSTRAP_ESTABLISHED",
        "NEXT_FORMAL_VERIFICATION_TRANSACTION_ADAPTER",
    ):
        assert term in combined
    assert "exactly-once execution is guaranteed" not in combined.lower()
    assert "TBD" not in (ROOT / "docs" / "formal_background_job_execution_ownership.md").read_text(encoding="utf-8")
