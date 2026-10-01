"""Attempt-fenced execution ownership for formal BackgroundJob records.

The service owns short claim, heartbeat, requeue, and finalization
transactions. It deliberately has no processing or HTTP responsibilities.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import and_, case, func, or_, update

from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE


FORMAL_JOB_DEFAULT_LEASE_SECONDS = 30
FORMAL_JOB_CANDIDATE_SCAN_LIMIT = 20
FORMAL_JOB_TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})

CLAIM_OUTCOME_CLAIMED = "claimed"
CLAIM_OUTCOME_NO_JOB_AVAILABLE = "no_job_available"
CLAIM_OUTCOME_CLAIM_CONFLICT = "claim_conflict"
CLAIM_OUTCOME_PERSISTENCE_ERROR = "persistence_error"

LEASE_OUTCOME_ACCEPTED = "accepted"
LEASE_OUTCOME_LEASE_NOT_OWNED = "lease_not_owned"
LEASE_OUTCOME_LEASE_EXPIRED = "lease_expired"
LEASE_OUTCOME_STALE_ATTEMPT = "stale_attempt"
LEASE_OUTCOME_TERMINAL_IMMUTABLE = "terminal_immutable"
LEASE_OUTCOME_INVALID_STATE = "invalid_state"
LEASE_OUTCOME_RETRY_EXHAUSTED = "retry_exhausted"
LEASE_OUTCOME_PERSISTENCE_ERROR = "persistence_error"

ERROR_CLAIM_CONFLICT = "FORMAL_JOB_WORKER_CLAIM_CONFLICT"
ERROR_STALE_ATTEMPT = "FORMAL_JOB_STALE_EXECUTION_ATTEMPT"
ERROR_LEASE_NOT_OWNED = "FORMAL_JOB_LEASE_NOT_OWNED"
ERROR_LEASE_EXPIRED = "FORMAL_JOB_LEASE_EXPIRED"
ERROR_TERMINAL_IMMUTABLE = "FORMAL_JOB_TERMINAL_IMMUTABLE"
ERROR_INVALID_STATE = "FORMAL_JOB_INVALID_STATE"
ERROR_RETRY_EXHAUSTED = "FORMAL_JOB_RETRY_EXHAUSTED"
ERROR_PERSISTENCE = "FORMAL_JOB_EXECUTION_OWNERSHIP_PERSISTENCE_FAILED"

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _utc_now() -> datetime:
    return datetime.utcnow()


def _lease_token() -> str:
    return secrets.token_urlsafe(32)


def _job_uid() -> str:
    return uuid.uuid4().hex


def _required_text(value: Any, field_name: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.strptime(str(value), _TIME_FORMAT)


def _time_text(value: datetime) -> str:
    return _as_utc(value).strftime(_TIME_FORMAT)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, _TIME_FORMAT)
    except ValueError:
        return None


def _safe_error_code(value: Any, fallback: str = ERROR_PERSISTENCE) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text[:80]


def _safe_error_message(value: Any, fallback: str = "Formal job ownership operation failed.") -> str:
    text = str(value or fallback).strip() or fallback
    forbidden = (
        "LEXIBRIDGE_SENTINEL_SECRET",
        "Authorization:",
        "Cookie:",
        "Bearer ",
        "sk-",
    )
    if any(marker in text for marker in forbidden):
        return fallback
    return text[:500]


@dataclass(frozen=True)
class FormalJobExecutionLease:
    job_uid: str
    job_type: str
    worker_id: str
    execution_attempt: int
    lease_token: str = field(repr=False)
    claimed_at: datetime
    heartbeat_at: datetime
    lease_expires_at: datetime
    status: str

    def __post_init__(self):
        object.__setattr__(self, "job_uid", _required_text(self.job_uid, "job_uid", 64))
        object.__setattr__(self, "job_type", _required_text(self.job_type, "job_type", 80))
        object.__setattr__(self, "worker_id", _required_text(self.worker_id, "worker_id", 120))
        object.__setattr__(self, "lease_token", _required_text(self.lease_token, "lease_token", 128))
        attempt = int(self.execution_attempt or 0)
        if attempt <= 0:
            raise ValueError("execution_attempt must be positive.")
        object.__setattr__(self, "execution_attempt", attempt)
        object.__setattr__(self, "claimed_at", _as_utc(self.claimed_at))
        object.__setattr__(self, "heartbeat_at", _as_utc(self.heartbeat_at))
        object.__setattr__(self, "lease_expires_at", _as_utc(self.lease_expires_at))


@dataclass(frozen=True)
class FormalJobExecutionFence:
    """Minimal attempt identity used to fence a caller-owned transaction."""

    job_uid: str
    worker_id: str
    execution_attempt: int
    lease_token: str = field(repr=False)
    job_type: str = FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE

    def __post_init__(self):
        object.__setattr__(self, "job_uid", _required_text(self.job_uid, "job_uid", 64))
        object.__setattr__(self, "worker_id", _required_text(self.worker_id, "worker_id", 120))
        object.__setattr__(self, "lease_token", _required_text(self.lease_token, "lease_token", 128))
        object.__setattr__(self, "job_type", _required_text(self.job_type, "job_type", 80))
        attempt = int(self.execution_attempt or 0)
        if attempt <= 0:
            raise ValueError("execution_attempt must be positive.")
        object.__setattr__(self, "execution_attempt", attempt)


@dataclass(frozen=True)
class ClaimFormalJobResult:
    outcome: str
    lease: FormalJobExecutionLease | None = None
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class FormalJobLeaseOperationResult:
    outcome: str
    job_uid: str = ""
    execution_attempt: int = 0
    status: str = ""
    lease_expires_at: datetime | None = None
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class FormalBackgroundJobExecutionDependencies:
    session: Any
    job_model: Any
    current_time_factory: Callable[[], datetime] = _utc_now
    lease_token_factory: Callable[[], str] = _lease_token
    job_uid_factory: Callable[[], str] = _job_uid
    lease_seconds: int = FORMAL_JOB_DEFAULT_LEASE_SECONDS
    candidate_scan_limit: int = FORMAL_JOB_CANDIDATE_SCAN_LIMIT

    def __post_init__(self):
        lease_seconds = int(self.lease_seconds)
        scan_limit = int(self.candidate_scan_limit)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive.")
        if scan_limit <= 0:
            raise ValueError("candidate_scan_limit must be positive.")
        object.__setattr__(self, "lease_seconds", lease_seconds)
        object.__setattr__(self, "candidate_scan_limit", scan_limit)


def _candidate_rows(dependencies: FormalBackgroundJobExecutionDependencies, now_text: str):
    model = dependencies.job_model
    return (
        dependencies.session.query(
            model.id,
            model.job_uid,
            model.status,
            model.execution_attempt,
            model.lease_token,
            model.lease_expires_at,
        )
        .filter(
            model.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            or_(
                model.status.in_(("queued", "retrying")),
                and_(
                    model.status == "running",
                    model.lease_expires_at.isnot(None),
                    model.lease_expires_at != "",
                    model.lease_expires_at <= now_text,
                ),
            ),
        )
        .order_by(model.priority.asc(), model.id.asc())
        .limit(dependencies.candidate_scan_limit)
        .all()
    )


def _claim_predicate(model: Any, candidate: Any, now_text: str):
    common = (
        model.id == candidate.id,
        model.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        func.coalesce(model.execution_attempt, 0) == int(candidate.execution_attempt or 0),
    )
    if candidate.status in {"queued", "retrying"}:
        return and_(
            *common,
            model.status == candidate.status,
            or_(model.lease_token.is_(None), model.lease_token == ""),
        )
    return and_(
        *common,
        model.status == "running",
        func.coalesce(model.lease_token, "") == str(candidate.lease_token or ""),
        model.lease_expires_at.isnot(None),
        model.lease_expires_at != "",
        model.lease_expires_at <= now_text,
    )


def claim_next_formal_background_job(
    worker_id: str,
    dependencies: FormalBackgroundJobExecutionDependencies,
) -> ClaimFormalJobResult:
    worker = _required_text(worker_id, "worker_id", 120)
    now = _as_utc(dependencies.current_time_factory())
    now_text = _time_text(now)
    expiry = now + timedelta(seconds=dependencies.lease_seconds)
    expiry_text = _time_text(expiry)

    try:
        candidates = _candidate_rows(dependencies, now_text)
    except Exception:
        dependencies.session.rollback()
        return ClaimFormalJobResult(
            outcome=CLAIM_OUTCOME_PERSISTENCE_ERROR,
            error_code=ERROR_PERSISTENCE,
            error_message="Formal job could not be claimed.",
        )
    if not candidates:
        dependencies.session.rollback()
        return ClaimFormalJobResult(outcome=CLAIM_OUTCOME_NO_JOB_AVAILABLE)

    conflict_seen = False
    for candidate in candidates:
        token = _required_text(dependencies.lease_token_factory(), "lease_token", 128)
        stable_uid = str(candidate.job_uid or "").strip() or _required_text(
            dependencies.job_uid_factory(), "job_uid", 64
        )
        next_attempt = int(candidate.execution_attempt or 0) + 1
        model = dependencies.job_model
        values = {
            "job_uid": stable_uid,
            "status": "running",
            "locked_by": worker,
            "locked_at": now_text,
            "execution_attempt": next_attempt,
            "lease_token": token,
            "heartbeat_at": now_text,
            "lease_expires_at": expiry_text,
            "started_at": case(
                (or_(model.started_at.is_(None), model.started_at == ""), now_text),
                else_=model.started_at,
            ),
            "updated_at": now_text,
        }
        try:
            result = dependencies.session.execute(
                update(model).where(_claim_predicate(model, candidate, now_text)).values(**values)
            )
            if result.rowcount != 1:
                dependencies.session.rollback()
                conflict_seen = True
                continue
            dependencies.session.commit()
        except Exception:
            dependencies.session.rollback()
            return ClaimFormalJobResult(
                outcome=CLAIM_OUTCOME_PERSISTENCE_ERROR,
                error_code=ERROR_PERSISTENCE,
                error_message="Formal job could not be claimed.",
            )
        return ClaimFormalJobResult(
            outcome=CLAIM_OUTCOME_CLAIMED,
            lease=FormalJobExecutionLease(
                job_uid=stable_uid,
                job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
                worker_id=worker,
                execution_attempt=next_attempt,
                lease_token=token,
                claimed_at=now,
                heartbeat_at=now,
                lease_expires_at=expiry,
                status="running",
            ),
        )

    return ClaimFormalJobResult(
        outcome=CLAIM_OUTCOME_CLAIM_CONFLICT if conflict_seen else CLAIM_OUTCOME_NO_JOB_AVAILABLE,
        error_code=ERROR_CLAIM_CONFLICT if conflict_seen else "",
        error_message="Formal job claim was won by another worker." if conflict_seen else "",
    )


def _active_predicate(model: Any, lease: FormalJobExecutionLease, now_text: str):
    return and_(
        model.job_uid == lease.job_uid,
        model.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        model.status == "running",
        model.locked_by == lease.worker_id,
        model.execution_attempt == lease.execution_attempt,
        model.lease_token == lease.lease_token,
        model.lease_expires_at.isnot(None),
        model.lease_expires_at != "",
        model.lease_expires_at > now_text,
    )


def _rejection_result(
    lease: FormalJobExecutionLease,
    dependencies: FormalBackgroundJobExecutionDependencies,
    now: datetime,
) -> FormalJobLeaseOperationResult:
    model = dependencies.job_model
    row = (
        dependencies.session.query(
            model.job_type,
            model.status,
            model.locked_by,
            model.execution_attempt,
            model.lease_token,
            model.lease_expires_at,
        )
        .filter(model.job_uid == lease.job_uid)
        .first()
    )
    if row is None or row.job_type != FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_INVALID_STATE,
            job_uid=lease.job_uid,
            execution_attempt=lease.execution_attempt,
            error_code=ERROR_INVALID_STATE,
            error_message="Formal job is not available for this operation.",
        )
    expiry = _parse_time(row.lease_expires_at)
    common = {
        "job_uid": lease.job_uid,
        "execution_attempt": lease.execution_attempt,
        "status": row.status,
        "lease_expires_at": expiry,
    }
    if row.status in FORMAL_JOB_TERMINAL_STATUSES:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_TERMINAL_IMMUTABLE,
            error_code=ERROR_TERMINAL_IMMUTABLE,
            error_message="Terminal formal job is immutable.",
            **common,
        )
    if int(row.execution_attempt or 0) != lease.execution_attempt:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_STALE_ATTEMPT,
            error_code=ERROR_STALE_ATTEMPT,
            error_message="Formal job execution attempt is stale.",
            **common,
        )
    if row.locked_by != lease.worker_id or row.lease_token != lease.lease_token:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_LEASE_NOT_OWNED,
            error_code=ERROR_LEASE_NOT_OWNED,
            error_message="Formal job lease is not owned by this worker.",
            **common,
        )
    if expiry is None or expiry <= now:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_LEASE_EXPIRED,
            error_code=ERROR_LEASE_EXPIRED,
            error_message="Formal job lease has expired.",
            **common,
        )
    return FormalJobLeaseOperationResult(
        outcome=LEASE_OUTCOME_INVALID_STATE,
        error_code=ERROR_INVALID_STATE,
        error_message="Formal job is not in a valid ownership state.",
        **common,
    )


def _rejection_after_rollback(lease, dependencies, now):
    dependencies.session.rollback()
    try:
        result = _rejection_result(lease, dependencies, now)
    finally:
        dependencies.session.rollback()
    return result


def validate_active_formal_job_lease(
    lease: FormalJobExecutionLease,
    dependencies: FormalBackgroundJobExecutionDependencies,
) -> FormalJobLeaseOperationResult:
    now = _as_utc(dependencies.current_time_factory())
    model = dependencies.job_model
    active = (
        dependencies.session.query(model.job_uid)
        .filter(_active_predicate(model, lease, _time_text(now)))
        .first()
    )
    if active is not None:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_ACCEPTED,
            job_uid=lease.job_uid,
            execution_attempt=lease.execution_attempt,
            status="running",
            lease_expires_at=lease.lease_expires_at,
        )
    return _rejection_result(lease, dependencies, now)


def fence_active_formal_job_lease_in_transaction(
    lease: FormalJobExecutionLease,
    dependencies: FormalBackgroundJobExecutionDependencies,
    *,
    lease_extension_seconds: int | None = None,
) -> FormalJobLeaseOperationResult:
    """Fence business writes without owning the surrounding transaction."""

    now = _as_utc(dependencies.current_time_factory())
    extension = dependencies.lease_seconds if lease_extension_seconds is None else int(lease_extension_seconds)
    if extension <= 0:
        raise ValueError("lease_extension_seconds must be positive.")
    expiry = now + timedelta(seconds=extension)
    model = dependencies.job_model
    try:
        result = dependencies.session.execute(
            update(model)
            .where(_active_predicate(model, lease, _time_text(now)))
            .values(
                heartbeat_at=_time_text(now),
                lease_expires_at=_time_text(expiry),
                updated_at=_time_text(now),
            )
        )
        if result.rowcount != 1:
            return _rejection_result(lease, dependencies, now)
    except Exception:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_PERSISTENCE_ERROR,
            job_uid=lease.job_uid,
            execution_attempt=lease.execution_attempt,
            error_code=ERROR_PERSISTENCE,
            error_message="Formal job transaction fence could not be acquired.",
        )
    return FormalJobLeaseOperationResult(
        outcome=LEASE_OUTCOME_ACCEPTED,
        job_uid=lease.job_uid,
        execution_attempt=lease.execution_attempt,
        status="running",
        lease_expires_at=expiry,
    )


def heartbeat_formal_background_job(
    lease: FormalJobExecutionLease,
    dependencies: FormalBackgroundJobExecutionDependencies,
) -> FormalJobLeaseOperationResult:
    now = _as_utc(dependencies.current_time_factory())
    expiry = now + timedelta(seconds=dependencies.lease_seconds)
    model = dependencies.job_model
    try:
        result = dependencies.session.execute(
            update(model)
            .where(_active_predicate(model, lease, _time_text(now)))
            .values(heartbeat_at=_time_text(now), lease_expires_at=_time_text(expiry), updated_at=_time_text(now))
        )
        if result.rowcount != 1:
            return _rejection_after_rollback(lease, dependencies, now)
        dependencies.session.commit()
    except Exception:
        dependencies.session.rollback()
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_PERSISTENCE_ERROR,
            job_uid=lease.job_uid,
            execution_attempt=lease.execution_attempt,
            error_code=ERROR_PERSISTENCE,
            error_message="Formal job heartbeat could not be saved.",
        )
    return FormalJobLeaseOperationResult(
        outcome=LEASE_OUTCOME_ACCEPTED,
        job_uid=lease.job_uid,
        execution_attempt=lease.execution_attempt,
        status="running",
        lease_expires_at=expiry,
    )


def _fenced_status_update(
    lease: FormalJobExecutionLease,
    dependencies: FormalBackgroundJobExecutionDependencies,
    *,
    status: str,
    error_code: str = "",
    error_message: str = "",
    progress_message: str,
    increment_attempt_count: bool = False,
) -> FormalJobLeaseOperationResult:
    now = _as_utc(dependencies.current_time_factory())
    now_text = _time_text(now)
    model = dependencies.job_model
    values = {
        "status": status,
        "error_code": _safe_error_code(error_code, "") if error_code else "",
        "error_message": _safe_error_message(error_message) if error_message else "",
        "progress_message": progress_message,
        "updated_at": now_text,
        "locked_by": "",
        "lease_token": "",
        "lease_expires_at": "",
    }
    if status in FORMAL_JOB_TERMINAL_STATUSES:
        values["finished_at"] = now_text
    if increment_attempt_count:
        values["attempt_count"] = func.coalesce(model.attempt_count, 0) + 1
    try:
        result = dependencies.session.execute(
            update(model).where(_active_predicate(model, lease, now_text)).values(**values)
        )
        if result.rowcount != 1:
            return _rejection_after_rollback(lease, dependencies, now)
        dependencies.session.commit()
    except Exception:
        dependencies.session.rollback()
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_PERSISTENCE_ERROR,
            job_uid=lease.job_uid,
            execution_attempt=lease.execution_attempt,
            error_code=ERROR_PERSISTENCE,
            error_message="Formal job ownership operation could not be saved.",
        )
    return FormalJobLeaseOperationResult(
        outcome=LEASE_OUTCOME_ACCEPTED,
        job_uid=lease.job_uid,
        execution_attempt=lease.execution_attempt,
        status=status,
    )


def complete_formal_background_job(lease, dependencies):
    return _fenced_status_update(
        lease,
        dependencies,
        status="completed",
        progress_message="Completed",
    )


def fail_formal_background_job(lease, dependencies, error_code, error_message):
    return _fenced_status_update(
        lease,
        dependencies,
        status="failed",
        error_code=error_code,
        error_message=error_message,
        progress_message="Failed",
        increment_attempt_count=True,
    )


def requeue_formal_background_job(lease, dependencies, error_code, error_message):
    now = _as_utc(dependencies.current_time_factory())
    now_text = _time_text(now)
    model = dependencies.job_model
    safe_code = _safe_error_code(error_code)
    safe_message = _safe_error_message(error_message)
    try:
        result = dependencies.session.execute(
            update(model)
            .where(
                _active_predicate(model, lease, now_text),
                func.coalesce(model.attempt_count, 0) + 1 < func.coalesce(model.max_attempts, 1),
            )
            .values(
                status="retrying",
                attempt_count=func.coalesce(model.attempt_count, 0) + 1,
                error_code=safe_code,
                error_message=safe_message,
                progress_message="Retry scheduled",
                updated_at=now_text,
                locked_by="",
                lease_token="",
                heartbeat_at="",
                lease_expires_at="",
            )
        )
        if result.rowcount != 1:
            dependencies.session.rollback()
            rejection = _rejection_result(lease, dependencies, now)
            if rejection.outcome == LEASE_OUTCOME_INVALID_STATE:
                budget = (
                    dependencies.session.query(model.attempt_count, model.max_attempts)
                    .filter(model.job_uid == lease.job_uid)
                    .first()
                )
                dependencies.session.rollback()
                if budget is not None and int(budget.attempt_count or 0) + 1 >= int(budget.max_attempts or 1):
                    return FormalJobLeaseOperationResult(
                        outcome=LEASE_OUTCOME_RETRY_EXHAUSTED,
                        job_uid=lease.job_uid,
                        execution_attempt=lease.execution_attempt,
                        status="running",
                        error_code=ERROR_RETRY_EXHAUSTED,
                        error_message="Formal job retry budget is exhausted.",
                    )
            else:
                dependencies.session.rollback()
            return rejection
        dependencies.session.commit()
    except Exception:
        dependencies.session.rollback()
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_PERSISTENCE_ERROR,
            job_uid=lease.job_uid,
            execution_attempt=lease.execution_attempt,
            error_code=ERROR_PERSISTENCE,
            error_message="Formal job retry state could not be saved.",
        )
    return FormalJobLeaseOperationResult(
        outcome=LEASE_OUTCOME_ACCEPTED,
        job_uid=lease.job_uid,
        execution_attempt=lease.execution_attempt,
        status="retrying",
        error_code=safe_code,
        error_message=safe_message,
    )
