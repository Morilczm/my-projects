"""Privacy-minimized contracts for the optional Personal Workspace student pilot.

This module measures whether a student can complete the existing product flow. It
does not execute alignment, inspect evidence text, or expose private learning
content to staff.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from statistics import median
from typing import Any


PILOT_ID = "personal-workspace-one-concept@1.0.0"
CONTRACT_VERSION = "student-real-pilot@1.0.0"
CONSENT_VERSION = "student-pilot-consent-zh@1.0.0"
AGGREGATE_POLICY_VERSION = "student-pilot-private-aggregate@1.0.0"
SMALL_CELL_SUPPRESSION_THRESHOLD = 3
ENROLLMENT_STATUSES = frozenset({"CONSENTED", "WITHDRAWN"})
SESSION_STATUSES = frozenset({"STARTED", "COMPLETED"})
RATING_FIELDS = (
    "helpfulness",
    "evidence_helpfulness",
    "uncertainty_understanding",
    "task_difficulty",
)


class StudentPilotError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def require_idempotency_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key or len(key) > 120 or any(ord(char) < 32 for char in key):
        raise StudentPilotError(
            "STUDENT_PILOT_IDEMPOTENCY_KEY_INVALID",
            "A bounded Idempotency-Key is required.",
        )
    return key


def validate_enrollment(data: dict[str, Any]) -> None:
    if str(data.get("pilot_id") or "") != PILOT_ID:
        raise StudentPilotError("STUDENT_PILOT_ID_INVALID", "Pilot ID is not active.")
    if data.get("consent") is not True or data.get("eligibility_attested") is not True:
        raise StudentPilotError(
            "STUDENT_PILOT_CONSENT_REQUIRED",
            "Explicit consent and eligibility attestation are required.",
        )
    if str(data.get("consent_version") or "") != CONSENT_VERSION:
        raise StudentPilotError(
            "STUDENT_PILOT_CONSENT_VERSION_INVALID",
            "The active consent version must be acknowledged.",
        )


def hash_private_reference(secret: str, *parts: Any) -> str:
    payload = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(f"{secret}\x1e{payload}".encode("utf-8")).hexdigest()


def serialize_enrollment(enrollment: Any | None) -> dict[str, Any] | None:
    if enrollment is None:
        return None
    return {
        "enrollment_uid": enrollment.enrollment_uid,
        "pilot_id": enrollment.pilot_id,
        "consent_version": enrollment.consent_version,
        "consent_status": enrollment.consent_status,
        "eligibility_attested": bool(enrollment.eligibility_attested),
        "consented_at": enrollment.consented_at,
        "withdrawn_at": enrollment.withdrawn_at,
        "version": int(enrollment.version or 1),
    }


def serialize_session(session: Any | None) -> dict[str, Any] | None:
    if session is None:
        return None
    return {
        "session_uid": session.session_uid,
        "pilot_id": session.pilot_id,
        "status": session.status,
        "workspace_scope": "PERSONAL",
        "alignment_status": session.alignment_status or "",
        "evidence_complete": bool(session.evidence_complete),
        "saved": bool(session.saved),
        "note_present": bool(session.note_present),
        "understanding_state": session.understanding_state or "",
        "duration_ms": int(session.duration_ms or 0),
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "survey_submitted": bool(getattr(session, "survey_submitted", False)),
        "version": int(session.version or 1),
    }


def validate_survey(data: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in RATING_FIELDS:
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise StudentPilotError(
                "STUDENT_PILOT_SURVEY_INVALID",
                f"{field} must be an integer from 1 to 5.",
            )
        normalized[field] = value
    if not isinstance(data.get("would_use_again"), bool):
        raise StudentPilotError(
            "STUDENT_PILOT_SURVEY_INVALID",
            "would_use_again must be a boolean.",
        )
    normalized["would_use_again"] = data["would_use_again"]
    comment = str(data.get("comment") or "").strip()
    if len(comment) > 500:
        raise StudentPilotError(
            "STUDENT_PILOT_SURVEY_INVALID", "Survey comment is too long."
        )
    normalized["comment"] = comment
    return normalized


def serialize_survey(survey: Any | None) -> dict[str, Any] | None:
    if survey is None:
        return None
    # Free text is deliberately not returned from this metrics serializer.
    return {
        "survey_uid": survey.survey_uid,
        **{field: int(getattr(survey, field) or 0) for field in RATING_FIELDS},
        "would_use_again": bool(survey.would_use_again),
        "submitted_at": survey.submitted_at,
        "version": int(survey.version or 1),
    }


def _average(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def build_private_aggregate(enrollments: list[Any], sessions: list[Any], surveys: list[Any]) -> dict[str, Any]:
    consented = [item for item in enrollments if item.consent_status == "CONSENTED"]
    completed = [item for item in sessions if item.status == "COMPLETED"]
    suppressed = len(completed) < SMALL_CELL_SUPPRESSION_THRESHOLD
    base = {
        "contract_id": CONTRACT_VERSION,
        "pilot_id": PILOT_ID,
        "aggregate_policy_id": AGGREGATE_POLICY_VERSION,
        "metrics_suppressed": suppressed,
        "privacy": {
            "content_collected": False,
            "individual_rows_returned": False,
            "small_cell_suppression_threshold": SMALL_CELL_SUPPRESSION_THRESHOLD,
        },
        "counts": {
            "currently_consented": len(consented),
            "withdrawn": len([item for item in enrollments if item.consent_status == "WITHDRAWN"]),
            "sessions_started": len(sessions),
            "sessions_completed": len(completed),
            "surveys_submitted": len(surveys),
        },
        "metrics": None,
    }
    if suppressed:
        return base
    alignment_distribution: dict[str, int] = {}
    understanding_distribution: dict[str, int] = {}
    for session in completed:
        alignment = str(session.alignment_status or "UNKNOWN")
        alignment_distribution[alignment] = alignment_distribution.get(alignment, 0) + 1
        understanding = str(session.understanding_state or "UNSET")
        understanding_distribution[understanding] = understanding_distribution.get(understanding, 0) + 1
    base["metrics"] = {
        "completion_rate": round(len(completed) / len(sessions), 4) if sessions else 0.0,
        "median_duration_ms": int(median([int(item.duration_ms or 0) for item in completed])),
        "evidence_complete_rate": round(
            sum(bool(item.evidence_complete) for item in completed) / len(completed), 4
        ),
        "save_rate": round(sum(bool(item.saved) for item in completed) / len(completed), 4),
        "note_presence_rate": round(
            sum(bool(item.note_present) for item in completed) / len(completed), 4
        ),
        "alignment_status_distribution": alignment_distribution,
        "understanding_state_distribution": understanding_distribution,
        "survey_averages": {
            field: _average([int(getattr(item, field)) for item in surveys])
            for field in RATING_FIELDS
        },
        "would_use_again_rate": (
            round(sum(bool(item.would_use_again) for item in surveys) / len(surveys), 4)
            if surveys else None
        ),
    }
    # A JSON round-trip makes accidental ORM/private attributes impossible.
    return json.loads(json.dumps(base, ensure_ascii=False, sort_keys=True))
