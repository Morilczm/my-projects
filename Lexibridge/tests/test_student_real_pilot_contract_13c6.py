import json
import uuid
from types import SimpleNamespace

from services import student_pilot


PILOT_ID = "personal-workspace-one-concept@1.0.0"
CONSENT_VERSION = "student-pilot-consent-zh@1.0.0"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _student(app_module, *, suffix=""):
    user = app_module.User(
        username=f"pilot_student_{suffix}",
        email=f"pilot.student.{suffix}@lexibridge.local",
        password_hash=app_module.generate_password_hash(
            "Student1234", method="pbkdf2:sha256"
        ),
        role="student",
        is_verified=True,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(user)
    app_module.db.session.commit()
    return user, app_module.create_auth_token(user)


def _query(app_module, student, *, scope="PERSONAL", status="READY"):
    query_uid = f"pilot-query-{uuid.uuid4().hex}"
    result_uid = f"pilot-result-{uuid.uuid4().hex}"
    raw = {
        "query_uid": query_uid,
        "result_uid": result_uid,
        "workspace_scope": scope,
        "workspace_uid": f"personal:{student.id}" if scope == "PERSONAL" else "course:1",
        "visibility": "PRIVATE",
        "authority": "NON_OFFICIAL",
        "publication_status": "NOT_APPLICABLE",
        "alignment_status": status,
        "english_term": "electric potential",
        "selected_text": "electric potential",
        "bounded_context": "Electric potential is energy per unit charge.",
        "recommended_chinese_concept": {"text": "电势"} if status != "NOT_READY" else None,
        "selected_candidate": (
            {"candidate_uid": "candidate-1", "text": "电势"}
            if status != "NOT_READY"
            else None
        ),
        "qualification": {
            "decision": "QUALIFIED" if status == "READY" else status
        },
        "english_evidence": [{"source_uid": "private-en", "chunk_uid": "en-1", "snippet": "bounded"}],
        "chinese_evidence": [{"source_uid": "private-zh", "chunk_uid": "zh-1", "snippet": "bounded"}],
        "chinese_candidates": [],
        "generated_hints": [],
        "evidence_complete": True,
    }
    query = app_module.StudentConceptQuery(
        query_uid=query_uid,
        result_uid=result_uid,
        student_id=student.id,
        workspace_scope=scope,
        workspace_uid=raw["workspace_uid"],
        course_id=None if scope == "PERSONAL" else 1,
        source_uid="private-en",
        source_version="1",
        chunk_uid="en-1",
        selected_text="electric potential",
        selection_start=0,
        selection_end=18,
        query_fingerprint=uuid.uuid4().hex,
        result_json=json.dumps(raw, ensure_ascii=False),
        processing_status="completed",
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(query)
    app_module.db.session.commit()
    return query


def _enable(app_module):
    previous = app_module.app.config.get("STUDENT_REAL_PILOT_ENABLED")
    app_module.app.config["STUDENT_REAL_PILOT_ENABLED"] = True
    return previous


def _restore(app_module, previous):
    if previous is None:
        app_module.app.config.pop("STUDENT_REAL_PILOT_ENABLED", None)
    else:
        app_module.app.config["STUDENT_REAL_PILOT_ENABLED"] = previous


def _enroll(client, token, key="pilot-enroll"):
    return client.post(
        "/api/student/pilot/enrollment",
        headers={**bearer(token), "Idempotency-Key": key},
        json={
            "pilot_id": PILOT_ID,
            "consent_version": CONSENT_VERSION,
            "consent": True,
            "eligibility_attested": True,
        },
    )


def test_pilot_is_disabled_by_default_and_does_not_block_normal_student_use(
    app_module, client, student_token
):
    app_module.app.config["STUDENT_REAL_PILOT_ENABLED"] = False
    status = client.get("/api/student/pilot", headers=bearer(student_token))
    assert status.status_code == 200
    payload = status.get_json()["data"]
    assert payload["enabled"] is False
    assert payload["participation_required_for_product"] is False

    blocked = _enroll(client, student_token)
    assert blocked.status_code == 403
    assert blocked.get_json()["error_code"] == "STUDENT_PILOT_DISABLED"


def test_explicit_consent_is_versioned_idempotent_and_withdrawable(app_module, client):
    previous = _enable(app_module)
    try:
        with app_module.app.app_context():
            student, token = _student(app_module, suffix=uuid.uuid4().hex[:8])
        missing = client.post(
            "/api/student/pilot/enrollment",
            headers={**bearer(token), "Idempotency-Key": "missing-consent"},
            json={"pilot_id": PILOT_ID, "consent": False},
        )
        assert missing.status_code == 400
        assert missing.get_json()["error_code"] == "STUDENT_PILOT_CONSENT_REQUIRED"

        first = _enroll(client, token, "same-enrollment")
        replay = _enroll(client, token, "same-enrollment")
        assert first.status_code == replay.status_code == 200
        assert first.get_json()["data"]["enrollment"]["consent_status"] == "CONSENTED"
        assert replay.get_json()["data"]["idempotent_replay"] is True

        withdrawn = client.delete(
            "/api/student/pilot/enrollment",
            headers={**bearer(token), "Idempotency-Key": "withdraw-enrollment"},
        )
        assert withdrawn.status_code == 200
        assert withdrawn.get_json()["data"]["enrollment"]["consent_status"] == "WITHDRAWN"
    finally:
        _restore(app_module, previous)


def test_personal_session_derives_metrics_without_persisting_query_content(app_module, client):
    previous = _enable(app_module)
    try:
        with app_module.app.app_context():
            student, token = _student(app_module, suffix=uuid.uuid4().hex[:8])
            query = _query(app_module, student)
            record = app_module.PersonalLearningRecord(
                student_id=student.id,
                query_uid=query.query_uid,
                result_uid=query.result_uid,
                workspace_scope="PERSONAL",
                workspace_uid=f"personal:{student.id}",
                saved=True,
                personal_note="private note must never enter pilot metrics",
                understanding_state="UNDERSTOOD",
                version=1,
                created_at=app_module.current_time_text(),
                updated_at=app_module.current_time_text(),
            )
            app_module.db.session.add(record)
            app_module.db.session.commit()
            query_uid = query.query_uid
        assert _enroll(client, token).status_code == 200
        started = client.post(
            "/api/student/pilot/sessions",
            headers={**bearer(token), "Idempotency-Key": "start-session"},
            json={"pilot_id": PILOT_ID},
        )
        assert started.status_code == 200
        session_uid = started.get_json()["data"]["session"]["session_uid"]
        completed = client.put(
            f"/api/student/pilot/sessions/{session_uid}/complete",
            headers={**bearer(token), "Idempotency-Key": "complete-session"},
            json={"query_uid": query_uid, "expected_version": 1},
        )
        assert completed.status_code == 200
        session = completed.get_json()["data"]["session"]
        assert session["status"] == "COMPLETED"
        assert session["alignment_status"] == "READY"
        assert session["saved"] is True
        assert session["note_present"] is True
        assert session["understanding_state"] == "UNDERSTOOD"
        serialized = json.dumps(session, ensure_ascii=False)
        assert "electric potential" not in serialized
        assert "电势" not in serialized
        assert "private note" not in serialized
        changed = client.put(
            f"/api/student/pilot/sessions/{session_uid}/complete",
            headers={**bearer(token), "Idempotency-Key": "different-completion"},
            json={"query_uid": query_uid, "expected_version": 2},
        )
        assert changed.status_code == 409
        assert changed.get_json()["error_code"] == "STUDENT_PILOT_SESSION_ALREADY_COMPLETED"

        with app_module.app.app_context():
            stored = app_module.StudentPilotSession.query.filter_by(
                session_uid=session_uid
            ).one()
            stored_json = json.dumps(
                {column.name: getattr(stored, column.name) for column in stored.__table__.columns},
                ensure_ascii=False,
                default=str,
            )
            assert "electric potential" not in stored_json
            assert "电势" not in stored_json
            assert "private note" not in stored_json
            assert stored.query_uid_hash
            assert not hasattr(stored, "query_uid")
    finally:
        _restore(app_module, previous)


def test_managed_course_or_other_students_query_cannot_enter_personal_pilot(app_module, client):
    previous = _enable(app_module)
    try:
        with app_module.app.app_context():
            student, token = _student(app_module, suffix=uuid.uuid4().hex[:8])
            other, _ = _student(app_module, suffix=uuid.uuid4().hex[:8])
            managed = _query(app_module, student, scope="MANAGED_COURSE")
            other_query = _query(app_module, other)
            managed_uid, other_uid = managed.query_uid, other_query.query_uid
        assert _enroll(client, token).status_code == 200
        start = client.post(
            "/api/student/pilot/sessions",
            headers={**bearer(token), "Idempotency-Key": "start-boundary"},
            json={"pilot_id": PILOT_ID},
        ).get_json()["data"]["session"]
        managed_response = client.put(
            f"/api/student/pilot/sessions/{start['session_uid']}/complete",
            headers={**bearer(token), "Idempotency-Key": "managed-complete"},
            json={"query_uid": managed_uid, "expected_version": 1},
        )
        assert managed_response.status_code == 400
        assert managed_response.get_json()["error_code"] == "STUDENT_PILOT_PERSONAL_QUERY_REQUIRED"
        other_response = client.put(
            f"/api/student/pilot/sessions/{start['session_uid']}/complete",
            headers={**bearer(token), "Idempotency-Key": "other-complete"},
            json={"query_uid": other_uid, "expected_version": 1},
        )
        assert other_response.status_code == 404
        assert other_response.get_json()["error_code"] == "STUDENT_PILOT_QUERY_NOT_FOUND"
    finally:
        _restore(app_module, previous)


def test_survey_is_bounded_and_withdrawal_erases_study_sessions_not_product_data(app_module, client):
    previous = _enable(app_module)
    try:
        with app_module.app.app_context():
            student, token = _student(app_module, suffix=uuid.uuid4().hex[:8])
            query = _query(app_module, student)
            query_uid = query.query_uid
            student_id = student.id
        assert _enroll(client, token).status_code == 200
        session_uid = client.post(
            "/api/student/pilot/sessions",
            headers={**bearer(token), "Idempotency-Key": "survey-start"},
            json={"pilot_id": PILOT_ID},
        ).get_json()["data"]["session"]["session_uid"]
        assert client.put(
            f"/api/student/pilot/sessions/{session_uid}/complete",
            headers={**bearer(token), "Idempotency-Key": "survey-complete"},
            json={"query_uid": query_uid, "expected_version": 1},
        ).status_code == 200
        invalid = client.put(
            f"/api/student/pilot/sessions/{session_uid}/survey",
            headers={**bearer(token), "Idempotency-Key": "bad-survey"},
            json={"helpfulness": 6},
        )
        assert invalid.status_code == 400
        submitted = client.put(
            f"/api/student/pilot/sessions/{session_uid}/survey",
            headers={**bearer(token), "Idempotency-Key": "good-survey"},
            json={
                "helpfulness": 5,
                "evidence_helpfulness": 4,
                "uncertainty_understanding": 4,
                "task_difficulty": 2,
                "would_use_again": True,
                "comment": "This private comment must not enter aggregate output.",
            },
        )
        assert submitted.status_code == 200
        assert submitted.get_json()["data"]["survey"]["helpfulness"] == 5

        assert client.delete(
            "/api/student/pilot/enrollment",
            headers={**bearer(token), "Idempotency-Key": "withdraw-after-session"},
        ).status_code == 200
        with app_module.app.app_context():
            assert app_module.StudentPilotSession.query.filter_by(student_id=student_id).count() == 0
            assert app_module.StudentPilotSurvey.query.filter_by(student_id=student_id).count() == 0
            assert app_module.StudentConceptQuery.query.filter_by(query_uid=query_uid).count() == 1
    finally:
        _restore(app_module, previous)


def test_instructor_reviewer_denied_and_admin_receives_only_suppressed_aggregate(
    app_module, client, teacher_token, admin_token
):
    previous = _enable(app_module)
    try:
        with app_module.app.app_context():
            reviewer = app_module.User(
                username=f"pilot_reviewer_{uuid.uuid4().hex[:8]}",
                email=f"pilot.reviewer.{uuid.uuid4().hex[:8]}@lexibridge.local",
                password_hash=app_module.generate_password_hash(
                    "Reviewer1234", method="pbkdf2:sha256"
                ),
                role="reviewer",
                is_verified=True,
                created_at=app_module.current_time_text(),
            )
            app_module.db.session.add(reviewer)
            app_module.db.session.commit()
            reviewer_token = app_module.create_auth_token(reviewer)
        for token in (teacher_token, reviewer_token):
            assert client.get("/api/student/pilot", headers=bearer(token)).status_code == 403
            assert client.get("/api/admin/student-pilot/aggregate", headers=bearer(token)).status_code == 403

        aggregate = client.get(
            "/api/admin/student-pilot/aggregate", headers=bearer(admin_token)
        )
        assert aggregate.status_code == 200
        data = aggregate.get_json()["data"]
        assert data["privacy"]["small_cell_suppression_threshold"] == 3
        assert data["metrics_suppressed"] is True
        serialized = json.dumps(data, ensure_ascii=False)
        for forbidden in (
            "student_id", "query_uid", "source_uid", "selected_text",
            "personal_note", "comment", "english_term", "chinese_term",
        ):
            assert forbidden not in serialized
    finally:
        _restore(app_module, previous)


def test_three_completed_sessions_unlock_only_deidentified_aggregate_metrics():
    enrollments = [
        SimpleNamespace(consent_status="CONSENTED") for _ in range(3)
    ]
    sessions = [
        SimpleNamespace(
            status="COMPLETED",
            duration_ms=value,
            evidence_complete=True,
            saved=True,
            note_present=index != 0,
            alignment_status="READY" if index < 2 else "REVIEW_REQUIRED",
            understanding_state="UNDERSTOOD" if index < 2 else "STILL_CONFUSED",
        )
        for index, value in enumerate((120_000, 180_000, 240_000))
    ]
    surveys = [
        SimpleNamespace(
            helpfulness=5,
            evidence_helpfulness=4,
            uncertainty_understanding=4,
            task_difficulty=2,
            would_use_again=True,
            comment="must never be aggregated",
        )
        for _ in range(3)
    ]
    result = student_pilot.build_private_aggregate(enrollments, sessions, surveys)
    assert result["metrics_suppressed"] is False
    assert result["metrics"]["median_duration_ms"] == 180_000
    assert result["metrics"]["save_rate"] == 1.0
    assert result["metrics"]["survey_averages"]["helpfulness"] == 5.0
    serialized = json.dumps(result, ensure_ascii=False)
    assert "must never be aggregated" not in serialized
    assert "student_id" not in serialized
