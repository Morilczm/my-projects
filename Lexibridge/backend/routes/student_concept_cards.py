"""Student Concept Card route registration.

This module is a staged extraction from ``backend/app.py``. It keeps the
student-facing Concept Card route handlers thin and delegates approved-only,
course-visible learning behavior to ``services.student_concept_cards``. It does
not import ``backend.app`` or create application/database objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Response, request

from services import student_concept_cards as student_concept_card_service
from routes.shared import RouteCoreDependencies


ROUTE_MARKER = "student_concept_card_routes"
TARGET_ROUTES = {
    "/api/student/concept-cards": "list_student_concept_cards_api",
    "/api/student/concept-cards/export": "export_student_concept_cards_api",
    "/api/student/concept-cards/<card_uid>": "get_student_concept_card_api",
    "/api/student/concept-cards/<card_uid>/state": "update_student_concept_card_state_api",
    "/api/student/concept-cards/<card_uid>/feedback": "student_concept_card_feedback_api",
}


@dataclass(frozen=True)
class StudentConceptCardModels:
    """Domain model dependencies for student Concept Card routes."""

    ConceptAlignmentCard: Any
    StudentConceptCardState: Any
    Feedback: Any
    StudentCourseMembership: Any
    CourseStudentVisibilityPolicy: Any
    KnowledgeSource: Any | None = None
    KnowledgeChunk: Any | None = None
    DocumentParseRecord: Any | None = None


def register_student_concept_card_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: StudentConceptCardModels,
    student_visible_course_names,
    student_course_access_service,
    record_student_course_access_audit,
) -> None:
    """Register student Concept Card learning routes on an existing Flask app."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    db = core.db
    card_model = models.ConceptAlignmentCard
    state_model = models.StudentConceptCardState
    feedback_model = models.Feedback
    membership_model = models.StudentCourseMembership
    visibility_policy_model = models.CourseStudentVisibilityPolicy

    def student_concept_card_error_response(exc, audit_context):
        reason = getattr(exc, "reason", "student_concept_card_error")
        if reason in {"concept_card_not_available", "missing_card_uid", "concept_card_source_unavailable"}:
            return core.api_error_with_audit_context(
                "RESOURCE_NOT_FOUND",
                str(exc),
                404,
                audit_context,
                {"audit_error_code": reason},
            )
        return core.api_error_with_audit_context(
            "VALIDATION_ERROR",
            str(exc),
            400,
            audit_context,
            {"audit_error_code": reason},
        )

    def record_student_concept_card_audit(event_type, *, card=None, feedback=None, state=None, audit_context=None, extra=None):
        core.audit_record_service.create_audit_record(
            db.session,
            core.audit_record_model,
            {
                "event_type": event_type,
                "target_type": "student_concept_card",
                "target_uid": getattr(card, "card_uid", "") or getattr(feedback, "actual_result", "") or getattr(state, "card_uid", ""),
                "result": "success",
                "input_payload": {
                    "card_uid": getattr(card, "card_uid", "") or getattr(feedback, "actual_result", "") or getattr(state, "card_uid", ""),
                    "course": getattr(card, "course", "") or getattr(state, "course", ""),
                    "feedback_id": getattr(feedback, "id", None),
                    "state_uid": getattr(state, "state_uid", ""),
                    **(extra or {}),
                },
                "output_payload": {},
                "changed_fields": [],
            },
            audit_context=audit_context,
            now_fn=core.current_time_text,
            commit=False,
        )

    def require_student_card_visibility(card, user, audit_context, *, commit_on_denied=True):
        decision = student_course_access_service.can_student_view_concept_card(
            db.session,
            membership_model,
            visibility_policy_model,
            user,
            card,
        )
        if decision.allowed:
            return None
        policy = student_course_access_service.get_course_student_visibility_policy(
            db.session,
            visibility_policy_model,
            getattr(card, "course", ""),
        )
        record_student_course_access_audit(
            "student_concept_card_access_denied",
            course=getattr(card, "course", ""),
            card=card,
            policy=policy,
            user_id=getattr(user, "id", None),
            denied_reason=decision.reason,
            audit_context=audit_context,
            result="blocked",
        )
        if commit_on_denied:
            db.session.commit()
        return core.api_error_with_audit_context(
            "RESOURCE_NOT_FOUND",
            "Concept card is not available for student learning.",
            404,
            audit_context,
            {
                "audit_error_code": "student_concept_card_access_denied",
                "denied_reason": decision.reason,
            },
        )

    def list_student_concept_cards_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"student", "teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        try:
            filters = request.args.to_dict()
            filters["allowed_courses"] = student_visible_course_names(user)
            result = student_concept_card_service.list_student_concept_cards(
                db.session,
                card_model,
                state_model,
                feedback_model,
                user=user,
                filters=filters,
                source_model=models.KnowledgeSource,
                chunk_model=models.KnowledgeChunk,
            )
            card_uids = [card.card_uid for card in result.items]
            states = student_concept_card_service.get_states_by_card_uid(
                db.session,
                state_model,
                user.id,
                card_uids,
            )
            feedback_counts = student_concept_card_service._feedback_counts(feedback_model, user.id)
            items = [
                student_concept_card_service.serialize_student_card_summary(
                    card,
                    state=states.get(card.card_uid),
                    feedback_count=feedback_counts.get(card.card_uid, 0),
                    session=db.session,
                    source_model=models.KnowledgeSource,
                    chunk_model=models.KnowledgeChunk,
                    parse_model=models.DocumentParseRecord,
                )
                for card in result.items
            ]
        except student_concept_card_service.StudentConceptCardError as exc:
            return student_concept_card_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "items": items,
                "pagination": result.pagination,
                "approved_only": True,
            },
            audit_context=audit_context,
        )

    def export_student_concept_cards_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"student", "teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        filters = request.args.to_dict()
        filters["page"] = 1
        filters["per_page"] = 100
        filters["allowed_courses"] = student_visible_course_names(user)
        export_format = str(filters.get("format") or "json").strip().lower()
        try:
            result = student_concept_card_service.list_student_concept_cards(
                db.session,
                card_model,
                state_model,
                feedback_model,
                user=user,
                filters=filters,
                source_model=models.KnowledgeSource,
                chunk_model=models.KnowledgeChunk,
            )
            card_uids = [card.card_uid for card in result.items]
            states = student_concept_card_service.get_states_by_card_uid(
                db.session,
                state_model,
                user.id,
                card_uids,
            )
            rows = student_concept_card_service.export_rows(result.items, states)
        except student_concept_card_service.StudentConceptCardError as exc:
            return student_concept_card_error_response(exc, audit_context)
        if export_format == "csv":
            csv_text = student_concept_card_service.rows_to_csv(rows)
            if not csv_text:
                csv_text = "english_term,chinese_term,course,chapter,concept_scope,english_explanation,chinese_explanation,source_summary,mastered,favorited\n"
            response = Response(csv_text, mimetype="text/csv")
            response.headers["Content-Disposition"] = "attachment; filename=student_concept_cards.csv"
            response.headers["X-Request-ID"] = audit_context.get("request_id", "")
            return response
        return core.api_success_with_audit_context(
            {
                "items": rows,
                "count": len(rows),
                "approved_only": True,
            },
            audit_context=audit_context,
        )

    def get_student_concept_card_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"student", "teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        try:
            card = student_concept_card_service.get_publishable_approved_card(
                db.session,
                card_model,
                card_uid,
                source_model=models.KnowledgeSource,
                chunk_model=models.KnowledgeChunk,
            )
            denied_response = require_student_card_visibility(card, user, audit_context)
            if denied_response:
                return denied_response
            state = student_concept_card_service.record_card_view(
                db.session,
                state_model,
                card,
                user_id=user.id,
                now_fn=core.current_time_text,
                commit=True,
            )
            feedback_counts = student_concept_card_service._feedback_counts(feedback_model, user.id)
        except student_concept_card_service.StudentConceptCardError as exc:
            db.session.rollback()
            return student_concept_card_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "card": student_concept_card_service.serialize_student_card_detail(
                    card,
                    state=state,
                    feedback_count=feedback_counts.get(card.card_uid, 0),
                    session=db.session,
                    source_model=models.KnowledgeSource,
                    chunk_model=models.KnowledgeChunk,
                    parse_model=models.DocumentParseRecord,
                ),
                "approved_only": True,
            },
            audit_context=audit_context,
        )

    def update_student_concept_card_state_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"student", "teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}
        try:
            card = student_concept_card_service.get_publishable_approved_card(
                db.session,
                card_model,
                card_uid,
                source_model=models.KnowledgeSource,
                chunk_model=models.KnowledgeChunk,
            )
            denied_response = require_student_card_visibility(card, user, audit_context)
            if denied_response:
                return denied_response
            state = student_concept_card_service.update_student_state(
                db.session,
                state_model,
                card,
                user,
                data,
                now_fn=core.current_time_text,
                commit=False,
            )
            record_student_concept_card_audit(
                "student_concept_card_state_updated",
                card=card,
                state=state,
                audit_context=audit_context,
                extra={"favorited": state.favorited, "mastered": state.mastered},
            )
            db.session.commit()
        except student_concept_card_service.StudentConceptCardError as exc:
            db.session.rollback()
            return student_concept_card_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "state": student_concept_card_service._state_dict(state),
                "card": student_concept_card_service.serialize_student_card_summary(card, state=state),
                "approved_only": True,
            },
            "Student concept card state updated.",
            audit_context,
        )

    def student_concept_card_feedback_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"student", "teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}
        try:
            card = student_concept_card_service.get_publishable_approved_card(
                db.session,
                card_model,
                card_uid,
                source_model=models.KnowledgeSource,
                chunk_model=models.KnowledgeChunk,
            )
            denied_response = require_student_card_visibility(card, user, audit_context)
            if denied_response:
                return denied_response
            feedback = student_concept_card_service.create_student_feedback(
                db.session,
                feedback_model,
                card,
                user,
                data,
                now_fn=core.current_time_text,
                commit=False,
            )
            record_student_concept_card_audit(
                "student_concept_card_feedback_submitted",
                card=card,
                feedback=feedback,
                audit_context=audit_context,
                extra={"feedback_type": feedback.feedback_type},
            )
            db.session.commit()
        except student_concept_card_service.StudentConceptCardError as exc:
            db.session.rollback()
            return student_concept_card_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "feedback": student_concept_card_service.serialize_feedback_result(feedback),
                "approved_only": True,
            },
            "Student concept card feedback submitted.",
            audit_context,
        )

    app.add_url_rule(
        "/api/student/concept-cards",
        view_func=list_student_concept_cards_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/student/concept-cards/export",
        view_func=export_student_concept_cards_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/student/concept-cards/<card_uid>",
        view_func=get_student_concept_card_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/student/concept-cards/<card_uid>/state",
        view_func=update_student_concept_card_state_api,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/student/concept-cards/<card_uid>/feedback",
        view_func=student_concept_card_feedback_api,
        methods=["POST"],
    )
    registered.add(ROUTE_MARKER)


def _assert_no_duplicate_target_routes(app) -> None:
    for path, endpoint in TARGET_ROUTES.items():
        for rule in app.url_map.iter_rules():
            if rule.rule == path and _target_method_for_path(path) in rule.methods:
                raise RuntimeError(
                    f"Cannot register {endpoint}: {_target_method_for_path(path)} {path} is already registered as {rule.endpoint}."
                )


def _target_method_for_path(path: str) -> str:
    if path.endswith("/state") or path.endswith("/feedback"):
        return "POST"
    return "GET"
