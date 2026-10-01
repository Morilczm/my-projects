"""Content-minimized summaries for the controlled multi-student pilot.

This module deliberately does not run alignment or collect telemetry.  It
consumes server-derived, already-redacted outcomes from the existing
Personal Workspace pilot contract and produces a bounded aggregate suitable
for a local controlled rehearsal or a separately consented student study.
"""

from __future__ import annotations

from statistics import median
from typing import Any, Iterable


MIN_COMPLETED_SESSIONS = 5
SMALL_CELL_SUPPRESSION_THRESHOLD = 3
MAX_TASK_DURATION_MS = 10 * 60 * 1000
PARTICIPANT_MODES = frozenset({"self_simulated", "real_consenting"})


class MultiStudentPilotError(ValueError):
    """Raised when a pilot summary cannot be safely or honestly produced."""


def _outcomes(outcomes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in outcomes]
    persona_uids = [str(item.get("persona_uid") or "").strip() for item in rows]
    if not rows or any(not value for value in persona_uids):
        raise MultiStudentPilotError("Every pilot outcome needs an opaque persona UID.")
    if len(set(persona_uids)) != len(persona_uids):
        raise MultiStudentPilotError("Pilot outcomes must have unique participant identities.")
    return rows


def sanitize_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    """Return only bounded, content-free fields from one pilot outcome."""

    allowed = {
        "persona_uid",
        "consent_recorded",
        "session_started",
        "session_completed",
        "duration_ms",
        "alignment_status",
        "evidence_complete",
        "saved",
        "note_present",
        "understanding_state",
        "survey",
        "cross_account_access_blocked",
        "external_requests",
        "real_provider_requests",
    }
    result = {key: outcome[key] for key in allowed if key in outcome}
    survey = result.get("survey")
    if isinstance(survey, dict):
        survey_fields = {
            "helpfulness",
            "evidence_helpfulness",
            "uncertainty_understanding",
            "task_difficulty",
            "would_use_again",
        }
        result["survey"] = {
            key: survey[key] for key in survey_fields if key in survey
        }
    else:
        result.pop("survey", None)
    return result


def build_isolation_audit(outcomes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = _outcomes(outcomes)
    external_requests = sum(int(item.get("external_requests") or 0) for item in rows)
    real_provider_requests = sum(int(item.get("real_provider_requests") or 0) for item in rows)
    blocked = all(bool(item.get("cross_account_access_blocked")) for item in rows)
    incident_count = int(not blocked) + int(external_requests > 0) + int(real_provider_requests > 0)
    return {
        "unique_personas": len(rows),
        "cross_account_access_blocked": blocked,
        "external_requests": external_requests,
        "real_provider_requests": real_provider_requests,
        "incident_count": incident_count,
    }


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _survey_average(rows: list[dict[str, Any]], field: str) -> float | None:
    values: list[float] = []
    for row in rows:
        survey = row.get("survey")
        if isinstance(survey, dict) and isinstance(survey.get(field), (int, float)):
            values.append(float(survey[field]))
    return _average(values)


def summarize_controlled_run(
    outcomes: Iterable[dict[str, Any]],
    *,
    participant_mode: str,
    real_participant_attestation: bool = False,
) -> dict[str, Any]:
    """Build a truthful aggregate; never emit per-person or content fields."""

    if participant_mode not in PARTICIPANT_MODES:
        raise MultiStudentPilotError("Unknown participant mode.")
    if participant_mode == "real_consenting" and not real_participant_attestation:
        raise MultiStudentPilotError(
            "Real-participant reporting requires an explicit study attestation."
        )

    rows = _outcomes(outcomes)
    completed = [row for row in rows if bool(row.get("session_completed"))]
    consented = [row for row in rows if bool(row.get("consent_recorded"))]
    started = [row for row in rows if bool(row.get("session_started"))]
    isolation = build_isolation_audit(rows)
    metrics_suppressed = len(completed) < SMALL_CELL_SUPPRESSION_THRESHOLD
    durations = [max(0, int(row.get("duration_ms") or 0)) for row in completed]
    completion_rate = round(len(completed) / len(rows), 4) if rows else 0.0
    evidence_helpfulness = _survey_average(completed, "evidence_helpfulness")
    uncertainty_understanding = _survey_average(completed, "uncertainty_understanding")

    quality_checks = {
        "completion_rate_target": completion_rate >= 0.80,
        "median_duration_target": bool(durations) and median(durations) <= MAX_TASK_DURATION_MS,
        "evidence_helpfulness_target": (evidence_helpfulness or 0) >= 4.0,
        "uncertainty_understanding_target": (uncertainty_understanding or 0) >= 4.0,
        "privacy_target": isolation["incident_count"] == 0,
        "external_requests_target": isolation["external_requests"] == 0,
        "real_provider_requests_target": isolation["real_provider_requests"] == 0,
    }
    conclusion_gate_open = (
        len(completed) >= MIN_COMPLETED_SESSIONS and all(quality_checks.values())
    )
    if conclusion_gate_open and participant_mode == "self_simulated":
        quality_status = "SELF_SIMULATED_MULTI_STUDENT_BASELINE_ESTABLISHED"
    elif conclusion_gate_open:
        quality_status = "REAL_STUDENT_PILOT_BASELINE_ESTABLISHED"
    else:
        quality_status = "REAL_STUDENT_PILOT_NOT_ESTABLISHED"

    metrics = None
    if not metrics_suppressed:
        metrics = {
            "completion_rate": completion_rate,
            "median_duration_ms": int(median(durations)) if durations else None,
            "evidence_complete_rate": round(
                sum(bool(row.get("evidence_complete")) for row in completed) / len(completed),
                4,
            ) if completed else 0.0,
            "save_rate": round(
                sum(bool(row.get("saved")) for row in completed) / len(completed), 4
            ) if completed else 0.0,
            "note_presence_rate": round(
                sum(bool(row.get("note_present")) for row in completed) / len(completed), 4
            ) if completed else 0.0,
            "survey_averages": {
                field: _survey_average(completed, field)
                for field in (
                    "helpfulness",
                    "evidence_helpfulness",
                    "uncertainty_understanding",
                    "task_difficulty",
                )
            },
            "would_use_again_rate": (
                round(
                    sum(
                        bool(row.get("survey", {}).get("would_use_again"))
                        for row in completed
                        if isinstance(row.get("survey"), dict)
                    ) / sum(
                        isinstance(row.get("survey"), dict) for row in completed
                    ),
                    4,
                )
                if any(isinstance(row.get("survey"), dict) for row in completed)
                else None
            ),
        }

    return {
        "contract_id": "controlled-multi-student-pilot@1.0.0",
        "participant_mode": participant_mode,
        "real_participants_claimed": participant_mode == "real_consenting",
        "counts": {
            "personas": len(rows),
            "consented": len(consented),
            "sessions_started": len(started),
            "completed": len(completed),
        },
        "privacy": {
            "content_collected": False,
            "individual_rows_returned": False,
            "metrics_suppressed": metrics_suppressed,
            "isolation_audit": isolation,
        },
        "quality_gate": {
            "minimum_completed_sessions": MIN_COMPLETED_SESSIONS,
            "conclusion_gate_open": conclusion_gate_open,
            "checks": quality_checks,
        },
        "metrics": metrics,
        "quality_status": quality_status,
    }
