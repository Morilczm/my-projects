"""Optional, consent-first Personal Workspace real-student pilot routes."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import current_app, request

from routes.shared import RouteCoreDependencies
from services import student_concept_queries
from services import student_pilot


@dataclass(frozen=True)
class StudentPilotModels:
    StudentPilotEnrollment: Any
    StudentPilotSession: Any
    StudentPilotSurvey: Any
    StudentConceptQuery: Any
    PersonalLearningRecord: Any


def register_student_pilot_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: StudentPilotModels,
) -> None:
    marker = "student_pilot_routes"
    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if marker in registered:
        return
    db = core.db

    def context_for(user=None):
        return core.get_route_audit_context(user)

    def error(reason, message, status, context):
        return core.api_error_with_audit_context(
            reason, message, status, context, {"audit_error_code": reason}
        )

    def require_role(roles):
        user, response = core.require_current_user(roles)
        context = context_for(user)
        if response:
            return None, core.attach_request_id_to_response(response, context), context
        return user, None, context

    def enabled():
        return bool(current_app.config.get("STUDENT_REAL_PILOT_ENABLED", False))

    def require_enabled(context):
        if enabled():
            return None
        return error(
            "STUDENT_PILOT_DISABLED",
            "The optional real-student pilot is not enabled.",
            403,
            context,
        )

    def enrollment_for(student_id):
        return models.StudentPilotEnrollment.query.filter_by(
            student_id=student_id, pilot_id=student_pilot.PILOT_ID
        ).first()

    def session_for(student_id, session_uid):
        return models.StudentPilotSession.query.filter_by(
            student_id=student_id,
            session_uid=session_uid,
            pilot_id=student_pilot.PILOT_ID,
        ).first()

    def idempotency():
        return student_pilot.require_idempotency_key(
            request.headers.get("Idempotency-Key")
        )

    def audit(event_type, *, user, target_uid, request_id, output):
        core.audit_record_service.create_audit_record(
            db.session,
            core.audit_record_model,
            {
                "event_type": event_type,
                "target_type": "student_pilot",
                "target_uid": target_uid,
                "input_payload": {"pilot_id": student_pilot.PILOT_ID},
                "output_payload": dict(output),
                "changed_fields": sorted(output),
                "result": "success",
            },
            audit_context={
                "actor_id": user.id,
                "actor_role": user.role,
                "request_id": request_id,
                "source": "api",
            },
            now_fn=core.current_time_text,
            commit=False,
        )

    def get_status():
        user, response, context = require_role({"student"})
        if response:
            return response
        enrollment = enrollment_for(user.id)
        latest = models.StudentPilotSession.query.filter_by(
            student_id=user.id,
            pilot_id=student_pilot.PILOT_ID,
        ).order_by(models.StudentPilotSession.id.desc()).first()
        survey = (
            models.StudentPilotSurvey.query.filter_by(session_uid=latest.session_uid).first()
            if latest is not None
            else None
        )
        return core.api_success_with_audit_context(
            {
                "contract_id": student_pilot.CONTRACT_VERSION,
                "pilot_id": student_pilot.PILOT_ID,
                "enabled": enabled(),
                "participation_required_for_product": False,
                "scope": "PERSONAL",
                "content_collected": False,
                "consent_version": student_pilot.CONSENT_VERSION,
                "enrollment": student_pilot.serialize_enrollment(enrollment),
                "latest_session": student_pilot.serialize_session(latest),
                "survey": student_pilot.serialize_survey(survey),
            },
            audit_context=context,
        )

    def enroll():
        user, response, context = require_role({"student"})
        if response:
            return response
        disabled = require_enabled(context)
        if disabled:
            return disabled
        try:
            key = idempotency()
            data = request.get_json(silent=True) or {}
            student_pilot.validate_enrollment(data)
        except student_pilot.StudentPilotError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        enrollment = enrollment_for(user.id)
        if enrollment is not None and enrollment.enrollment_request_id == key:
            return core.api_success_with_audit_context(
                {
                    "enrollment": student_pilot.serialize_enrollment(enrollment),
                    "idempotent_replay": True,
                },
                audit_context=context,
            )
        now = core.current_time_text()
        if enrollment is None:
            enrollment = models.StudentPilotEnrollment(
                enrollment_uid=str(uuid.uuid4()),
                student_id=user.id,
                pilot_id=student_pilot.PILOT_ID,
                consent_version=student_pilot.CONSENT_VERSION,
                consent_status="CONSENTED",
                eligibility_attested=True,
                enrollment_request_id=key,
                consented_at=now,
                version=1,
                created_at=now,
                updated_at=now,
            )
            db.session.add(enrollment)
        else:
            enrollment.consent_status = "CONSENTED"
            enrollment.consent_version = student_pilot.CONSENT_VERSION
            enrollment.eligibility_attested = True
            enrollment.enrollment_request_id = key
            enrollment.consented_at = now
            enrollment.withdrawn_at = ""
            enrollment.version = int(enrollment.version or 1) + 1
            enrollment.updated_at = now
        audit(
            "student_pilot_consent_recorded",
            user=user,
            target_uid=enrollment.enrollment_uid,
            request_id=key,
            output={"consent_status": "CONSENTED", "consent_version": student_pilot.CONSENT_VERSION},
        )
        db.session.commit()
        return core.api_success_with_audit_context(
            {
                "enrollment": student_pilot.serialize_enrollment(enrollment),
                "idempotent_replay": False,
            },
            audit_context=context,
        )

    def withdraw():
        user, response, context = require_role({"student"})
        if response:
            return response
        try:
            key = idempotency()
        except student_pilot.StudentPilotError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        enrollment = enrollment_for(user.id)
        if enrollment is None:
            return error("STUDENT_PILOT_ENROLLMENT_NOT_FOUND", "Enrollment was not found.", 404, context)
        if enrollment.consent_status == "WITHDRAWN" and enrollment.withdrawal_request_id == key:
            return core.api_success_with_audit_context(
                {"enrollment": student_pilot.serialize_enrollment(enrollment), "idempotent_replay": True},
                audit_context=context,
            )
        session_ids = [
            item.session_uid
            for item in models.StudentPilotSession.query.filter_by(student_id=user.id).all()
        ]
        if session_ids:
            models.StudentPilotSurvey.query.filter(
                models.StudentPilotSurvey.session_uid.in_(session_ids)
            ).delete(synchronize_session=False)
        models.StudentPilotSession.query.filter_by(student_id=user.id).delete(
            synchronize_session=False
        )
        now = core.current_time_text()
        enrollment.consent_status = "WITHDRAWN"
        enrollment.withdrawal_request_id = key
        enrollment.withdrawn_at = now
        enrollment.version = int(enrollment.version or 1) + 1
        enrollment.updated_at = now
        audit(
            "student_pilot_consent_withdrawn",
            user=user,
            target_uid=enrollment.enrollment_uid,
            request_id=key,
            output={"consent_status": "WITHDRAWN", "study_sessions_erased": True},
        )
        db.session.commit()
        return core.api_success_with_audit_context(
            {"enrollment": student_pilot.serialize_enrollment(enrollment), "idempotent_replay": False},
            audit_context=context,
        )

    def start_session():
        user, response, context = require_role({"student"})
        if response:
            return response
        disabled = require_enabled(context)
        if disabled:
            return disabled
        try:
            key = idempotency()
        except student_pilot.StudentPilotError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        data = request.get_json(silent=True) or {}
        if str(data.get("pilot_id") or "") != student_pilot.PILOT_ID:
            return error("STUDENT_PILOT_ID_INVALID", "Pilot ID is not active.", 400, context)
        enrollment = enrollment_for(user.id)
        if enrollment is None or enrollment.consent_status != "CONSENTED":
            return error("STUDENT_PILOT_CONSENT_REQUIRED", "Active consent is required.", 403, context)
        existing = models.StudentPilotSession.query.filter_by(
            student_id=user.id, start_request_id=key
        ).first()
        if existing is not None:
            return core.api_success_with_audit_context(
                {"session": student_pilot.serialize_session(existing), "idempotent_replay": True},
                audit_context=context,
            )
        active = models.StudentPilotSession.query.filter_by(
            student_id=user.id, pilot_id=student_pilot.PILOT_ID, status="STARTED"
        ).first()
        if active is not None:
            return error("STUDENT_PILOT_SESSION_ALREADY_ACTIVE", "A pilot session is already active.", 409, context)
        now = core.current_time_text()
        session = models.StudentPilotSession(
            session_uid=str(uuid.uuid4()),
            enrollment_uid=enrollment.enrollment_uid,
            student_id=user.id,
            pilot_id=student_pilot.PILOT_ID,
            status="STARTED",
            workspace_scope="PERSONAL",
            start_request_id=key,
            started_at=now,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.session.add(session)
        audit(
            "student_pilot_session_started",
            user=user,
            target_uid=session.session_uid,
            request_id=key,
            output={"status": "STARTED", "workspace_scope": "PERSONAL"},
        )
        db.session.commit()
        return core.api_success_with_audit_context(
            {"session": student_pilot.serialize_session(session), "idempotent_replay": False},
            audit_context=context,
        )

    def complete_session(session_uid):
        user, response, context = require_role({"student"})
        if response:
            return response
        try:
            key = idempotency()
        except student_pilot.StudentPilotError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        session = session_for(user.id, session_uid)
        if session is None:
            return error("STUDENT_PILOT_SESSION_NOT_FOUND", "Pilot session was not found.", 404, context)
        if session.status == "COMPLETED" and session.complete_request_id == key:
            return core.api_success_with_audit_context(
                {"session": student_pilot.serialize_session(session), "idempotent_replay": True},
                audit_context=context,
            )
        if session.status == "COMPLETED":
            return error(
                "STUDENT_PILOT_SESSION_ALREADY_COMPLETED",
                "A completed pilot session cannot be changed.",
                409,
                context,
            )
        data = request.get_json(silent=True) or {}
        if int(data.get("expected_version") or 0) != int(session.version or 1):
            return error("STUDENT_PILOT_SESSION_VERSION_CONFLICT", "Pilot session version is stale.", 409, context)
        query_uid = str(data.get("query_uid") or "").strip()
        query = models.StudentConceptQuery.query.filter_by(
            query_uid=query_uid, student_id=user.id
        ).first()
        if query is None:
            return error("STUDENT_PILOT_QUERY_NOT_FOUND", "Owned query was not found.", 404, context)
        if query.workspace_scope != "PERSONAL":
            return error(
                "STUDENT_PILOT_PERSONAL_QUERY_REQUIRED",
                "Only a Personal Workspace query may complete this pilot.",
                400,
                context,
            )
        if query.processing_status != "completed":
            return error("STUDENT_PILOT_QUERY_INCOMPLETE", "The query is not complete.", 400, context)
        try:
            raw = json.loads(query.result_json or "{}")
        except (TypeError, ValueError):
            raw = {}
        result = student_concept_queries.serialize_alignment_result(raw)
        record = models.PersonalLearningRecord.query.filter_by(
            student_id=user.id, result_uid=query.result_uid
        ).first()
        now = core.current_time_text()
        try:
            duration_ms = max(
                0,
                int(
                    (
                        datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
                        - datetime.strptime(session.started_at, "%Y-%m-%d %H:%M:%S")
                    ).total_seconds()
                    * 1000
                ),
            )
        except (TypeError, ValueError):
            duration_ms = 0
        session.status = "COMPLETED"
        session.query_uid_hash = student_pilot.hash_private_reference(
            str(current_app.config.get("SECRET_KEY") or ""), user.id, query_uid
        )
        session.alignment_status = str(result.get("alignment_status") or "NOT_READY")
        session.evidence_complete = bool(result.get("evidence_complete"))
        session.saved = bool(record and record.saved)
        session.note_present = bool(record and str(record.personal_note or "").strip())
        session.understanding_state = str(getattr(record, "understanding_state", "") or "")
        session.duration_ms = min(duration_ms, 86_400_000)
        session.complete_request_id = key
        session.completed_at = now
        session.version = int(session.version or 1) + 1
        session.updated_at = now
        audit(
            "student_pilot_session_completed",
            user=user,
            target_uid=session.session_uid,
            request_id=key,
            output={
                "status": "COMPLETED",
                "alignment_status": session.alignment_status,
                "evidence_complete": session.evidence_complete,
                "saved": session.saved,
                "note_present": session.note_present,
                "understanding_state": session.understanding_state,
            },
        )
        db.session.commit()
        return core.api_success_with_audit_context(
            {"session": student_pilot.serialize_session(session), "idempotent_replay": False},
            audit_context=context,
        )

    def submit_survey(session_uid):
        user, response, context = require_role({"student"})
        if response:
            return response
        try:
            key = idempotency()
            values = student_pilot.validate_survey(request.get_json(silent=True) or {})
        except student_pilot.StudentPilotError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        session = session_for(user.id, session_uid)
        if session is None or session.status != "COMPLETED":
            return error("STUDENT_PILOT_SESSION_NOT_COMPLETED", "Complete the session first.", 400, context)
        existing = models.StudentPilotSurvey.query.filter_by(session_uid=session_uid).first()
        if existing is not None:
            if existing.request_id == key:
                return core.api_success_with_audit_context(
                    {"survey": student_pilot.serialize_survey(existing), "idempotent_replay": True},
                    audit_context=context,
                )
            return error("STUDENT_PILOT_SURVEY_ALREADY_SUBMITTED", "Survey is already submitted.", 409, context)
        now = core.current_time_text()
        survey = models.StudentPilotSurvey(
            survey_uid=str(uuid.uuid4()),
            session_uid=session_uid,
            student_id=user.id,
            pilot_id=student_pilot.PILOT_ID,
            request_id=key,
            **values,
            submitted_at=now,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.session.add(survey)
        session.survey_submitted = True
        session.updated_at = now
        audit(
            "student_pilot_survey_submitted",
            user=user,
            target_uid=session.session_uid,
            request_id=key,
            output={"survey_submitted": True},
        )
        db.session.commit()
        return core.api_success_with_audit_context(
            {"survey": student_pilot.serialize_survey(survey), "idempotent_replay": False},
            audit_context=context,
        )

    def aggregate():
        user, response, context = require_role({"admin"})
        if response:
            return response
        payload = student_pilot.build_private_aggregate(
            models.StudentPilotEnrollment.query.filter_by(pilot_id=student_pilot.PILOT_ID).all(),
            models.StudentPilotSession.query.filter_by(pilot_id=student_pilot.PILOT_ID).all(),
            models.StudentPilotSurvey.query.filter_by(pilot_id=student_pilot.PILOT_ID).all(),
        )
        payload["enabled"] = enabled()
        return core.api_success_with_audit_context(payload, audit_context=context)

    app.add_url_rule("/api/student/pilot", view_func=get_status, methods=["GET"])
    app.add_url_rule("/api/student/pilot/enrollment", view_func=enroll, methods=["POST"])
    app.add_url_rule(
        "/api/student/pilot/enrollment",
        endpoint="withdraw_student_pilot_enrollment",
        view_func=withdraw,
        methods=["DELETE"],
    )
    app.add_url_rule("/api/student/pilot/sessions", view_func=start_session, methods=["POST"])
    app.add_url_rule(
        "/api/student/pilot/sessions/<session_uid>/complete",
        view_func=complete_session,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/student/pilot/sessions/<session_uid>/survey",
        view_func=submit_survey,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/admin/student-pilot/aggregate", view_func=aggregate, methods=["GET"]
    )
    registered.add(marker)
