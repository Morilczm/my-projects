"""Legacy alignment admission, drain inspection, and shutdown safeguards."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


RUNTIME_STATE_ACTIVE = "active"
RUNTIME_STATE_FREEZE = "freeze"
RUNTIME_STATE_DRAINING = "draining"
RUNTIME_STATE_DISABLED = "disabled"
RUNTIME_STATES = (
    RUNTIME_STATE_ACTIVE,
    RUNTIME_STATE_FREEZE,
    RUNTIME_STATE_DRAINING,
    RUNTIME_STATE_DISABLED,
)
LEGACY_ALIGNMENT_JOB_TYPE = "alignment_run"
LEGACY_ALIGNMENT_ADMISSION_DISABLED = "LEGACY_ALIGNMENT_ADMISSION_DISABLED"
LEGACY_ALIGNMENT_SHUTDOWN_SAFE_FAILURE = "LEGACY_ALIGNMENT_SHUTDOWN_SAFE_FAILURE"
SAFE_FAILURE_MESSAGE = "Legacy alignment job was safely failed during controlled shutdown."
ACTIVE_JOB_STATUSES = ("queued", "running", "retrying")
OBSERVED_JOB_STATUSES = ("queued", "running", "retrying", "failed")


class LegacyAlignmentFreezeError(RuntimeError):
    """Base error for the legacy freeze boundary."""


class LegacyAlignmentAdmissionError(LegacyAlignmentFreezeError):
    """Raised when code attempts to create legacy state while admission is closed."""


class LegacyAlignmentSafeFailureError(LegacyAlignmentFreezeError):
    """Raised when a running job cannot be safely failed under the supplied fence."""


@dataclass(frozen=True)
class LegacyAlignmentRuntimeModels:
    background_job: Any
    alignment_run: Any
    background_job_event: Any
    audit_record: Any


def normalize_runtime_state(value: Any) -> str:
    state = str(value or RUNTIME_STATE_ACTIVE).strip().lower()
    if state not in RUNTIME_STATES:
        raise ValueError(f"Unsupported legacy alignment runtime state: {state}")
    return state


def creation_is_allowed(runtime_state: Any, route_admission_enabled: bool) -> bool:
    return bool(route_admission_enabled) and normalize_runtime_state(runtime_state) == RUNTIME_STATE_ACTIVE


def worker_claim_is_allowed(runtime_state: Any) -> bool:
    return normalize_runtime_state(runtime_state) in {
        RUNTIME_STATE_ACTIVE,
        RUNTIME_STATE_DRAINING,
    }


def require_creation_admission(runtime_state: Any, route_admission_enabled: bool) -> None:
    if not creation_is_allowed(runtime_state, route_admission_enabled):
        raise LegacyAlignmentAdmissionError(LEGACY_ALIGNMENT_ADMISSION_DISABLED)


def _job_summary(job: Any) -> dict[str, Any]:
    return {
        "job_id": int(job.id),
        "job_uid": str(getattr(job, "job_uid", "") or ""),
        "status": str(getattr(job, "status", "") or ""),
        "alignment_run_id": getattr(job, "alignment_run_id", None),
        "attempt_count": int(getattr(job, "attempt_count", 0) or 0),
        "max_attempts": int(getattr(job, "max_attempts", 0) or 0),
        "locked_by": str(getattr(job, "locked_by", "") or ""),
        "locked_at": str(getattr(job, "locked_at", "") or ""),
        "created_at": str(getattr(job, "created_at", "") or ""),
        "updated_at": str(getattr(job, "updated_at", "") or ""),
    }


def legacy_queue_snapshot(session: Any, models: LegacyAlignmentRuntimeModels, *, limit: int = 100) -> dict[str, Any]:
    query = models.background_job.query.filter_by(job_type=LEGACY_ALIGNMENT_JOB_TYPE)
    counts = {status: query.filter_by(status=status).count() for status in OBSERVED_JOB_STATUSES}
    active_jobs = (
        query.filter(models.background_job.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(models.background_job.priority.asc(), models.background_job.id.asc())
        .limit(max(1, min(int(limit or 100), 500)))
        .all()
    )
    return {
        "job_type": LEGACY_ALIGNMENT_JOB_TYPE,
        "counts": counts,
        "active_total": sum(counts[status] for status in ACTIVE_JOB_STATUSES),
        "active_jobs": [_job_summary(job) for job in active_jobs],
    }


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise LegacyAlignmentSafeFailureError(f"{field_name} is required")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError as exc:
        raise LegacyAlignmentSafeFailureError(f"{field_name} must be an ISO-8601 timestamp") from exc


def _safe_failure_preview(job: Any, run: Any, stale_before: str) -> dict[str, Any]:
    return {
        "job_id": int(job.id),
        "job_uid": str(getattr(job, "job_uid", "") or ""),
        "alignment_run_id": int(run.id),
        "job_status_before": str(job.status),
        "run_status_before": str(run.status),
        "locked_by": str(job.locked_by or ""),
        "locked_at": str(job.locked_at or ""),
        "stale_before": stale_before,
        "error_code": LEGACY_ALIGNMENT_SHUTDOWN_SAFE_FAILURE,
    }


def safe_fail_running_job(
    session: Any,
    models: LegacyAlignmentRuntimeModels,
    *,
    job_id: int,
    expected_locked_by: str,
    stale_before: str,
    actor_name: str,
    now_fn,
    apply: bool = False,
) -> dict[str, Any]:
    job = session.get(models.background_job, int(job_id))
    if job is None or job.job_type != LEGACY_ALIGNMENT_JOB_TYPE:
        raise LegacyAlignmentSafeFailureError("Legacy alignment job not found")
    if job.status != "running":
        raise LegacyAlignmentSafeFailureError("Only a running legacy alignment job can be safely failed")
    expected_owner = str(expected_locked_by or "").strip()
    if not expected_owner or str(job.locked_by or "") != expected_owner:
        raise LegacyAlignmentSafeFailureError("Legacy alignment job owner fence does not match")
    lock_time = _parse_timestamp(job.locked_at, "locked_at")
    cutoff = _parse_timestamp(stale_before, "stale_before")
    if lock_time > cutoff:
        raise LegacyAlignmentSafeFailureError("Legacy alignment job is newer than the stale cutoff")
    if not job.alignment_run_id:
        raise LegacyAlignmentSafeFailureError("Legacy alignment job has no linked AlignmentRun")
    run = session.get(models.alignment_run, int(job.alignment_run_id))
    if run is None:
        raise LegacyAlignmentSafeFailureError("Linked AlignmentRun not found")
    if run.status not in {"queued", "running"}:
        raise LegacyAlignmentSafeFailureError("Linked AlignmentRun is already terminal")

    preview = _safe_failure_preview(job, run, stale_before)
    if not apply:
        return {"status": "dry_run", **preview}

    now = now_fn()
    job.status = "failed"
    job.error_code = LEGACY_ALIGNMENT_SHUTDOWN_SAFE_FAILURE
    job.error_message = SAFE_FAILURE_MESSAGE
    job.progress_message = "Failed during controlled legacy shutdown"
    job.finished_at = now
    job.updated_at = now
    job.locked_by = ""
    job.locked_at = ""
    job.heartbeat_at = ""
    job.lease_expires_at = ""

    run.status = "failed"
    run.error_message = SAFE_FAILURE_MESSAGE
    run.finished_at = now

    event = models.background_job_event(
        job_id=job.id,
        event_type="shutdown_safe_failure",
        message=SAFE_FAILURE_MESSAGE,
        progress_current=int(job.progress_current or 0),
        progress_total=int(job.progress_total or 0),
        metadata_json=json.dumps(
            {"error_code": LEGACY_ALIGNMENT_SHUTDOWN_SAFE_FAILURE, "alignment_run_id": run.id},
            ensure_ascii=True,
            sort_keys=True,
        ),
        created_at=now,
    )
    audit = models.audit_record(
        event_identity=f"legacy-alignment-safe-failure:{job.job_uid or job.id}:{job.attempt_count or 0}",
        event_type="legacy_alignment_shutdown_safe_failure",
        target_type="background_job",
        target_uid=str(job.job_uid or job.id),
        actor_name=str(actor_name or "legacy-shutdown-operator")[:160],
        actor_role="operator",
        source="operator_tool",
        before_snapshot=json.dumps(preview, ensure_ascii=True, sort_keys=True),
        after_snapshot=json.dumps(
            {"job_status": "failed", "run_status": "failed", "error_code": job.error_code},
            ensure_ascii=True,
            sort_keys=True,
        ),
        input_payload=json.dumps(
            {"job_id": job.id, "expected_locked_by": expected_owner, "stale_before": stale_before},
            ensure_ascii=True,
            sort_keys=True,
        ),
        output_payload=json.dumps(
            {"alignment_run_id": run.id, "job_status": "failed", "run_status": "failed"},
            ensure_ascii=True,
            sort_keys=True,
        ),
        changed_fields=json.dumps(["error_code", "error_message", "finished_at", "status"]),
        result="success",
        error_code=LEGACY_ALIGNMENT_SHUTDOWN_SAFE_FAILURE,
        error_message=SAFE_FAILURE_MESSAGE,
        created_at=now,
    )
    session.add_all([event, audit])
    session.commit()
    return {"status": "applied", **preview, "job_status": "failed", "run_status": "failed"}
