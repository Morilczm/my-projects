import json

import pytest

from services import multi_student_pilot


def _outcome(persona_uid, *, completed=True, duration_ms=120000, ratings=None):
    return {
        "persona_uid": persona_uid,
        "consent_recorded": True,
        "session_started": True,
        "session_completed": completed,
        "duration_ms": duration_ms,
        "alignment_status": "READY",
        "evidence_complete": True,
        "saved": True,
        "note_present": True,
        "understanding_state": "UNDERSTOOD",
        "survey": {
            "helpfulness": 5,
            "evidence_helpfulness": 4,
            "uncertainty_understanding": 4,
            "task_difficulty": 2,
            "would_use_again": True,
        } if ratings is None else ratings,
        "cross_account_access_blocked": True,
        "external_requests": 0,
        "real_provider_requests": 0,
    }


def test_summary_keeps_five_participant_gate_separate_from_small_cell_suppression():
    summary = multi_student_pilot.summarize_controlled_run(
        [_outcome(f"persona-{i}") for i in range(3)],
        participant_mode="self_simulated",
    )

    assert summary["counts"]["completed"] == 3
    assert summary["privacy"]["metrics_suppressed"] is False
    assert summary["quality_gate"]["minimum_completed_sessions"] == 5
    assert summary["quality_gate"]["conclusion_gate_open"] is False
    assert summary["quality_status"] == "REAL_STUDENT_PILOT_NOT_ESTABLISHED"


def test_summary_opens_controlled_baseline_only_after_five_completed_personas():
    summary = multi_student_pilot.summarize_controlled_run(
        [_outcome(f"persona-{i}") for i in range(5)],
        participant_mode="self_simulated",
    )

    assert summary["counts"]["completed"] == 5
    assert summary["quality_gate"]["conclusion_gate_open"] is True
    assert summary["quality_status"] == "SELF_SIMULATED_MULTI_STUDENT_BASELINE_ESTABLISHED"
    assert summary["metrics"]["completion_rate"] == 1.0
    assert summary["metrics"]["survey_averages"]["evidence_helpfulness"] == 4.0


def test_real_participant_claim_requires_explicit_real_mode():
    with pytest.raises(multi_student_pilot.MultiStudentPilotError):
        multi_student_pilot.summarize_controlled_run(
            [_outcome(f"persona-{i}") for i in range(5)],
            participant_mode="real",
            real_participant_attestation=False,
        )


def test_sanitized_outcome_and_summary_cannot_contain_private_content():
    raw = _outcome("persona-1")
    raw.update({
        "query_uid": "private-query-uid",
        "source_uid": "private-source-uid",
        "selected_text": "electric potential",
        "note": "private note",
        "evidence": "private evidence text",
    })

    sanitized = multi_student_pilot.sanitize_outcome(raw)
    serialized = json.dumps(sanitized, ensure_ascii=False)
    assert "private-query-uid" not in serialized
    assert "private-source-uid" not in serialized
    assert "electric potential" not in serialized
    assert "private note" not in serialized
    assert "private evidence text" not in serialized


def test_isolation_audit_requires_unique_personas_and_zero_incidents():
    outcomes = [_outcome(f"persona-{i}") for i in range(5)]
    audit = multi_student_pilot.build_isolation_audit(outcomes)
    assert audit == {
        "unique_personas": 5,
        "cross_account_access_blocked": True,
        "external_requests": 0,
        "real_provider_requests": 0,
        "incident_count": 0,
    }

    with pytest.raises(multi_student_pilot.MultiStudentPilotError):
        multi_student_pilot.build_isolation_audit(
            outcomes[:-1] + [_outcome("persona-0", completed=True)]
        )
