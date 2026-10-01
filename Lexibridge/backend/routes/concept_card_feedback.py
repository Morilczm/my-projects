"""Teacher-facing Concept Card feedback route registration.

This module is a staged extraction from ``backend/app.py``. It keeps the
teacher/admin student-feedback queue and triage route handlers thin while the
existing service layer owns feedback state transitions, review-workflow links,
ReviewRecord creation, triage records, and AuditRecord creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import request

from routes.shared import RouteCoreDependencies
from services import concept_alignment_cards as concept_card_service
from services import concept_card_feedback as concept_card_feedback_service
from services import concept_card_review as concept_card_review_service


ROUTE_MARKER = "concept_card_feedback_routes"
TARGET_ROUTES = {
    "/api/concept-cards/student-feedback-queue": {
        "endpoint": "concept_card_student_feedback_queue_api",
        "method": "GET",
    },
    "/api/concept-cards/<card_uid>/student-feedback": {
        "endpoint": "concept_card_student_feedback_for_card_api",
        "method": "GET",
    },
    "/api/concept-cards/student-feedback/<feedback_uid>/triage": {
        "endpoint": "triage_concept_card_student_feedback_api",
        "method": "POST",
    },
}


@dataclass(frozen=True)
class ConceptCardFeedbackModels:
    """Domain model dependencies for Concept Card feedback routes."""

    Feedback: Any
    ConceptAlignmentCard: Any
    ConceptCardReviewRecord: Any
    ConceptCardFeedbackTriageRecord: Any
    CourseReviewPermission: Any
    CourseReviewPolicy: Any


def register_concept_card_feedback_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: ConceptCardFeedbackModels,
) -> None:
    """Register teacher/admin Concept Card feedback queue and triage routes."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    db = core.db

    def concept_card_feedback_error_response(exc, audit_context):
        reason = getattr(exc, "reason", "concept_card_feedback_error")
        if reason in {"feedback_not_found", "card_not_found"}:
            return core.api_error_with_audit_context(
                "RESOURCE_NOT_FOUND",
                str(exc),
                404,
                audit_context,
                {"audit_error_code": reason},
            )
        if "permission" in reason or reason in {
            "student_cannot_review",
            "course_review_permission_missing",
            "course_review_permission_denied",
        }:
            return core.api_error_with_audit_context(
                "PERMISSION_DENIED",
                str(exc),
                403,
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

    def record_concept_card_feedback_queue_audit(
        event_type,
        *,
        user=None,
        feedback=None,
        card=None,
        action="",
        previous_status="",
        new_status="",
        audit_context=None,
    ):
        core.audit_record_service.create_audit_record(
            db.session,
            core.audit_record_model,
            {
                "event_type": event_type,
                "target_type": "concept_card_feedback",
                "target_uid": getattr(feedback, "feedback_uid", "") or str(getattr(feedback, "id", "")) or getattr(card, "card_uid", ""),
                "result": "success",
                "input_payload": {
                    "user_id": getattr(user, "id", None),
                    "feedback_uid": getattr(feedback, "feedback_uid", ""),
                    "card_uid": getattr(card, "card_uid", "") or getattr(feedback, "card_uid", ""),
                    "course": getattr(card, "course", "") or getattr(feedback, "course", ""),
                    "action": action,
                    "previous_status": previous_status,
                    "new_status": new_status,
                },
                "output_payload": {},
                "changed_fields": ["status"] if previous_status != new_status else [],
            },
            audit_context=audit_context,
            now_fn=core.current_time_text,
            commit=False,
        )

    def concept_card_student_feedback_queue_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        try:
            result = concept_card_feedback_service.get_concept_card_feedback_queue(
                db.session,
                models.Feedback,
                models.ConceptAlignmentCard,
                models.ConceptCardReviewRecord,
                models.CourseReviewPermission,
                user,
                request.args.to_dict(),
            )
            items = [
                concept_card_feedback_service.serialize_feedback_queue_item(
                    db.session,
                    feedback,
                    models.ConceptAlignmentCard,
                    models.ConceptCardReviewRecord,
                )
                for feedback in result.items
            ]
            record_concept_card_feedback_queue_audit(
                "concept_card_feedback_queue_viewed",
                user=user,
                audit_context=audit_context,
            )
            db.session.commit()
        except concept_card_feedback_service.ConceptCardFeedbackError as exc:
            db.session.rollback()
            return concept_card_feedback_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "items": items,
                "pagination": result.pagination,
            },
            audit_context=audit_context,
        )

    def concept_card_student_feedback_for_card_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        try:
            feedback_rows = concept_card_feedback_service.get_feedback_for_card(
                db.session,
                models.Feedback,
                models.ConceptAlignmentCard,
                models.CourseReviewPermission,
                card_uid,
                user,
            )
            items = [
                concept_card_feedback_service.serialize_feedback_queue_item(
                    db.session,
                    feedback,
                    models.ConceptAlignmentCard,
                    models.ConceptCardReviewRecord,
                )
                for feedback in feedback_rows
            ]
        except concept_card_feedback_service.ConceptCardFeedbackError as exc:
            return concept_card_feedback_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "items": items,
                "count": len(items),
            },
            audit_context=audit_context,
        )

    def triage_concept_card_student_feedback_api(feedback_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}
        action = str(data.get("action") or "").strip()
        try:
            feedback, triage_record, linked_review = concept_card_feedback_service.triage_concept_card_feedback(
                db.session,
                models.Feedback,
                models.ConceptAlignmentCard,
                models.ConceptCardReviewRecord,
                models.ConceptCardFeedbackTriageRecord,
                models.CourseReviewPermission,
                feedback_uid,
                user,
                action,
                data,
                audit_model=core.audit_record_model,
                audit_context=audit_context,
                policy_model=models.CourseReviewPolicy,
                now_fn=core.current_time_text,
                commit=True,
            )
        except (concept_card_feedback_service.ConceptCardFeedbackError, concept_card_review_service.ConceptCardReviewError) as exc:
            db.session.rollback()
            return concept_card_feedback_error_response(exc, audit_context)
        card = models.ConceptAlignmentCard.query.filter_by(
            card_uid=concept_card_feedback_service.feedback_card_uid(feedback)
        ).first()
        return core.api_success_with_audit_context(
            {
                "feedback": concept_card_feedback_service.serialize_feedback_queue_item(
                    db.session,
                    feedback,
                    models.ConceptAlignmentCard,
                    models.ConceptCardReviewRecord,
                ),
                "triage": concept_card_feedback_service.serialize_feedback_triage_record(triage_record),
                "review": concept_card_review_service.serialize_review_record(linked_review) if linked_review else None,
                "card": concept_card_service.serialize_concept_card(card) if card else None,
            },
            audit_context=audit_context,
        )

    app.add_url_rule(
        "/api/concept-cards/student-feedback-queue",
        view_func=concept_card_student_feedback_queue_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/concept-cards/<card_uid>/student-feedback",
        view_func=concept_card_student_feedback_for_card_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/concept-cards/student-feedback/<feedback_uid>/triage",
        view_func=triage_concept_card_student_feedback_api,
        methods=["POST"],
    )
    registered.add(ROUTE_MARKER)


def _assert_no_duplicate_target_routes(app) -> None:
    for path, route in TARGET_ROUTES.items():
        method = route["method"]
        endpoint = route["endpoint"]
        for rule in app.url_map.iter_rules():
            if rule.rule == path and method in rule.methods:
                raise RuntimeError(
                    f"Cannot register {endpoint}: {method} {path} is already registered as {rule.endpoint}."
                )
