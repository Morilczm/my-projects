"""Concept Card Reviewer Console route registration.

This module is a staged extraction from ``backend/app.py``. It keeps the
Reviewer/Admin route handlers thin and delegates review status changes,
policy gates, risk overrides, ReviewRecord creation, and AuditRecord creation
to the existing service layer. It does not import ``backend.app`` or create
application/database objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import request

from routes.shared import RouteCoreDependencies
from services import alignment_verification as alignment_verification_service
from services import concept_alignment_cards as concept_card_service
from services import concept_card_review as concept_card_review_service
from services import course_review_policy as course_review_policy_service
from services import teacher_alignment_review as teacher_alignment_review_service


ROUTE_MARKER = "concept_card_review_routes"
# ``teacher`` is retained only as transitional compatibility for existing
# course-review permissions. New product navigation exposes this workflow to
# the bilingual Reviewer role, not to the English-side Instructor experience.
REVIEW_ROUTE_ROLES = {"reviewer", "teacher", "admin"}
TARGET_ROUTES = {
    "/api/concept-cards/review-queue": {
        "endpoint": "concept_card_review_queue_api",
        "method": "GET",
    },
    "/api/concept-cards/<card_uid>/reviews": {
        "endpoint": "concept_card_reviews_api",
        "method": "GET",
    },
    "/api/concept-cards/<card_uid>/review": {
        "endpoint": "concept_card_review_action_api",
        "method": "POST",
    },
    "/api/concept-cards/<card_uid>/assign-reviewer": {
        "endpoint": "concept_card_assign_reviewer_api",
        "method": "POST",
    },
    "/api/concept-cards/<card_uid>/review-case": {
        "endpoint": "teacher_alignment_review_case_api",
        "method": "GET",
    },
    "/api/concept-cards/<card_uid>/generate-draft": {
        "endpoint": "teacher_alignment_generate_draft_api",
        "method": "POST",
    },
    "/api/concept-cards/<card_uid>/draft": {
        "endpoint": "teacher_alignment_draft_api",
        "method": "GET",
    },
}


@dataclass(frozen=True)
class ConceptCardReviewModels:
    """Domain model dependencies for Concept Card review routes."""

    ConceptAlignmentCard: Any
    ConceptCardReviewRecord: Any
    ConceptCardReviewAssignment: Any
    CourseReviewPolicy: Any
    CourseReviewPermission: Any
    AlignmentVerificationRun: Any
    KnowledgeSource: Any | None = None
    KnowledgeChunk: Any | None = None
    DocumentParseRecord: Any | None = None
    DocumentAlignmentWorkflowItem: Any | None = None
    DocumentAlignmentWorkflowRun: Any | None = None


def register_concept_card_review_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: ConceptCardReviewModels,
) -> None:
    """Register Reviewer Console routes on an existing Flask app."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    db = core.db

    def concept_card_review_error_response(exc, audit_context=None):
        if isinstance(exc, concept_card_service.ConceptCardNotFoundError):
            return core.api_error_with_audit_context(
                "RESOURCE_NOT_FOUND",
                str(exc),
                404,
                audit_context,
                {"audit_error_code": "concept_card_not_found"},
            )
        if isinstance(exc, concept_card_service.ConceptCardStaleReviewError):
            return core.api_error_with_audit_context(
                "CONCEPT_CARD_STALE_REVIEW",
                str(exc),
                409,
                audit_context,
                {"audit_error_code": "concept_card_stale_review"},
            )
        if isinstance(exc, concept_card_review_service.ConceptCardSourceUnavailableError):
            details = {
                "audit_error_code": "concept_card_source_unavailable",
                "source_availability": getattr(exc, "details", {}),
            }
            return core.api_error_with_audit_context(
                "CONCEPT_CARD_SOURCE_UNAVAILABLE",
                str(exc),
                422,
                audit_context,
                details,
            )
        if isinstance(exc, teacher_alignment_review_service.TeacherAlignmentReviewError):
            return core.api_error_with_audit_context(
                "TEACHER_ALIGNMENT_REVIEW_INVALID",
                str(exc),
                400,
                audit_context,
                {"audit_error_code": "teacher_alignment_review_invalid"},
            )
        return core.api_error_with_audit_context(
            "VALIDATION_ERROR",
            str(exc),
            400,
            audit_context,
            {"audit_error_code": "concept_card_review_validation_error"},
        )

    def reviewer_allowed_courses(user):
        if getattr(user, "role", "") == "admin":
            return None
        permissions = course_review_policy_service.get_reviewer_permissions(
            db.session,
            models.CourseReviewPermission,
            reviewer_id=getattr(user, "id", None),
            course=None,
        )
        return sorted({item.course for item in permissions if item.status == "active" and item.can_review})

    def concept_card_review_ui_summary(card):
        latest_review = (
            models.ConceptCardReviewRecord.query.filter_by(card_uid=card.card_uid)
            .order_by(models.ConceptCardReviewRecord.id.desc())
            .first()
        )
        assignment = (
            models.ConceptCardReviewAssignment.query.filter_by(card_uid=card.card_uid, assignment_status="active")
            .order_by(models.ConceptCardReviewAssignment.id.desc())
            .first()
        )
        verification_run = (
            models.AlignmentVerificationRun.query.filter_by(card_uid=card.card_uid)
            .order_by(models.AlignmentVerificationRun.id.desc())
            .first()
        )
        return {
            "latest_review_summary": concept_card_review_service.serialize_review_record(latest_review) if latest_review else None,
            "assignment_summary": concept_card_review_service.serialize_assignment(assignment) if assignment else None,
            "verification_summary": alignment_verification_service.serialize_alignment_verification_run(verification_run) if verification_run else None,
        }

    def permitted_card(card_uid, user, audit_context, purpose):
        try:
            card = concept_card_service.get_concept_card(
                db.session, models.ConceptAlignmentCard, card_uid
            )
        except concept_card_service.ConceptCardError as exc:
            return None, concept_card_review_error_response(exc, audit_context)
        if user.role != "admin":
            can_review, _, reason = course_review_policy_service.can_reviewer_review_card(
                db.session,
                models.CourseReviewPermission,
                card,
                user,
            )
            if not can_review:
                return None, core.api_error_with_audit_context(
                    "FORBIDDEN",
                    f"Reviewer is not permitted to {purpose} for this course.",
                    403,
                    audit_context,
                    {"audit_error_code": reason or "course_review_permission_denied"},
                )
        return card, None

    def concept_card_review_queue_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user(REVIEW_ROUTE_ROLES)
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        filters = request.args.to_dict()
        allowed_courses = reviewer_allowed_courses(user)
        if allowed_courses is not None:
            requested_course = str(filters.get("course") or "").strip()
            if requested_course and requested_course not in allowed_courses:
                filters["courses"] = ["__no_course_review_permission__"]
            else:
                filters["courses"] = allowed_courses or ["__no_course_review_permission__"]
        result = concept_card_review_service.get_review_queue(
            db.session,
            models.ConceptAlignmentCard,
            filters,
            review_model=models.ConceptCardReviewRecord,
        )
        items = []
        for card in result.items:
            data = concept_card_review_service.serialize_review_queue_item(
                card,
                session=db.session,
                source_model=models.KnowledgeSource,
                chunk_model=models.KnowledgeChunk,
                parse_model=models.DocumentParseRecord,
            )
            data.update(concept_card_review_ui_summary(card))
            items.append(data)
        return core.api_success_with_audit_context(
            {
                "items": items,
                "pagination": result.pagination,
            },
            audit_context=audit_context,
        )

    def concept_card_reviews_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user(REVIEW_ROUTE_ROLES)
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        try:
            card = concept_card_service.get_concept_card(db.session, models.ConceptAlignmentCard, card_uid)
        except concept_card_service.ConceptCardError as exc:
            return concept_card_review_error_response(exc, audit_context)
        if user.role != "admin":
            can_review, _, reason = course_review_policy_service.can_reviewer_review_card(
                db.session,
                models.CourseReviewPermission,
                card,
                user,
            )
            if not can_review:
                return core.api_error_with_audit_context(
                    "FORBIDDEN",
                    "Reviewer is not permitted to view reviews for this course.",
                    403,
                    audit_context,
                    {"audit_error_code": reason or "course_review_permission_denied"},
                )
        result = concept_card_review_service.get_card_review_history(
            db.session,
            models.ConceptCardReviewRecord,
            card_uid,
            request.args.to_dict(),
        )
        return core.api_success_with_audit_context(
            {
                "items": [concept_card_review_service.serialize_review_record(item) for item in result.items],
                "pagination": result.pagination,
            },
            audit_context=audit_context,
        )

    def concept_card_review_action_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user(REVIEW_ROUTE_ROLES)
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        raw_data = request.get_json(silent=True) or {}
        data = dict(raw_data) if isinstance(raw_data, dict) else {}
        action = str(data.get("action") or "").strip()
        data["idempotency_key"] = str(
            request.headers.get("Idempotency-Key")
            or data.get("idempotency_key")
            or ""
        ).strip()
        try:
            if action in {
                "accept_recommendation",
                "select_alternative_candidate",
                "defer_review",
            } or (action == "reject" and data["idempotency_key"]):
                card, review_record, reused = (
                    teacher_alignment_review_service.apply_human_decision(
                        db.session,
                        models.ConceptAlignmentCard,
                        models.ConceptCardReviewRecord,
                        card_uid,
                        action,
                        user,
                        data,
                        audit_model=core.audit_record_model,
                        audit_context=audit_context,
                        policy_model=models.CourseReviewPolicy,
                        permission_model=models.CourseReviewPermission,
                        source_model=models.KnowledgeSource,
                        chunk_model=models.KnowledgeChunk,
                        require_concurrency_token=True,
                        now_fn=core.current_time_text,
                        commit=True,
                    )
                )
            else:
                card, review_record = concept_card_review_service.dispatch_review_action(
                    db.session,
                    models.ConceptAlignmentCard,
                    models.ConceptCardReviewRecord,
                    card_uid,
                    action,
                    user,
                    data,
                    audit_model=core.audit_record_model,
                    audit_context=audit_context,
                    policy_model=models.CourseReviewPolicy,
                    permission_model=models.CourseReviewPermission,
                    source_model=models.KnowledgeSource,
                    chunk_model=models.KnowledgeChunk,
                    require_concurrency_token=True,
                    now_fn=core.current_time_text,
                    commit=True,
                )
                reused = False
        except (
            concept_card_service.ConceptCardError,
            concept_card_review_service.ConceptCardReviewError,
            teacher_alignment_review_service.TeacherAlignmentReviewError,
            ValueError,
        ) as exc:
            db.session.rollback()
            return concept_card_review_error_response(exc, audit_context)
        review_case = teacher_alignment_review_service.serialize_review_case(
            db.session,
            card,
            review_model=models.ConceptCardReviewRecord,
            workflow_item_model=models.DocumentAlignmentWorkflowItem,
            workflow_run_model=models.DocumentAlignmentWorkflowRun,
        )
        return core.api_success_with_audit_context(
            {
                "card": concept_card_review_service.serialize_review_queue_item(
                    card,
                    session=db.session,
                    source_model=models.KnowledgeSource,
                    chunk_model=models.KnowledgeChunk,
                    parse_model=models.DocumentParseRecord,
                ),
                "review": concept_card_review_service.serialize_review_record(review_record),
                "case": review_case,
                "reused": reused,
            },
            "Concept card review recorded.",
            audit_context,
        )

    def teacher_alignment_review_case_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user(REVIEW_ROUTE_ROLES)
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        card, error_response = permitted_card(
            card_uid, user, audit_context, "view this alignment case"
        )
        if error_response:
            return error_response
        return core.api_success_with_audit_context(
            {
                "case": teacher_alignment_review_service.serialize_review_case(
                    db.session,
                    card,
                    review_model=models.ConceptCardReviewRecord,
                    workflow_item_model=models.DocumentAlignmentWorkflowItem,
                    workflow_run_model=models.DocumentAlignmentWorkflowRun,
                )
            },
            audit_context=audit_context,
        )

    def teacher_alignment_generate_draft_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user(REVIEW_ROUTE_ROLES)
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        _, error_response = permitted_card(
            card_uid, user, audit_context, "generate a governed draft"
        )
        if error_response:
            return error_response
        raw_data = request.get_json(silent=True) or {}
        data = dict(raw_data) if isinstance(raw_data, dict) else {}
        data["idempotency_key"] = str(
            request.headers.get("Idempotency-Key") or ""
        ).strip()
        try:
            result = teacher_alignment_review_service.generate_fake_draft(
                db.session,
                models.ConceptAlignmentCard,
                models.ConceptCardReviewRecord,
                card_uid,
                user,
                data,
                audit_model=core.audit_record_model,
                audit_context=audit_context,
                policy_model=models.CourseReviewPolicy,
                permission_model=models.CourseReviewPermission,
                source_model=models.KnowledgeSource,
                chunk_model=models.KnowledgeChunk,
                require_concurrency_token=True,
                now_fn=core.current_time_text,
                commit=True,
            )
        except (
            concept_card_service.ConceptCardError,
            concept_card_review_service.ConceptCardReviewError,
            teacher_alignment_review_service.TeacherAlignmentReviewError,
            ValueError,
        ) as exc:
            db.session.rollback()
            return concept_card_review_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            result, "Governed fake Provider draft generated.", audit_context
        )

    def teacher_alignment_draft_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user(REVIEW_ROUTE_ROLES)
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        card, error_response = permitted_card(
            card_uid, user, audit_context, "view or edit this draft"
        )
        if error_response:
            return error_response
        if request.method == "GET":
            try:
                teacher_alignment_review_service.require_generated_draft(
                    db.session, models.ConceptCardReviewRecord, card_uid
                )
            except teacher_alignment_review_service.TeacherAlignmentReviewError as exc:
                return concept_card_review_error_response(exc, audit_context)
            return core.api_success_with_audit_context(
                {"draft": teacher_alignment_review_service.serialize_draft(card)},
                audit_context=audit_context,
            )
        raw_data = request.get_json(silent=True) or {}
        data = dict(raw_data) if isinstance(raw_data, dict) else {}
        try:
            card = teacher_alignment_review_service.update_draft(
                db.session,
                models.ConceptAlignmentCard,
                models.ConceptCardReviewRecord,
                card_uid,
                data,
                audit_model=core.audit_record_model,
                actor=user,
                audit_context=audit_context,
                source="teacher_review_api",
                now_fn=core.current_time_text,
                commit=True,
            )
        except (
            concept_card_service.ConceptCardError,
            teacher_alignment_review_service.TeacherAlignmentReviewError,
            ValueError,
        ) as exc:
            db.session.rollback()
            return concept_card_review_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {"draft": teacher_alignment_review_service.serialize_draft(card)},
            "Teacher draft saved.",
            audit_context,
        )

    def concept_card_assign_reviewer_api(card_uid):
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user(REVIEW_ROUTE_ROLES)
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        raw_data = request.get_json(silent=True) or {}
        data = dict(raw_data) if isinstance(raw_data, dict) else {}
        try:
            card, review_record, assignment = concept_card_review_service.assign_card_reviewer(
                db.session,
                models.ConceptAlignmentCard,
                models.ConceptCardReviewRecord,
                models.ConceptCardReviewAssignment,
                card_uid,
                user,
                data,
                audit_model=core.audit_record_model,
                audit_context=audit_context,
                policy_model=models.CourseReviewPolicy,
                permission_model=models.CourseReviewPermission,
                now_fn=core.current_time_text,
                commit=True,
            )
        except (concept_card_service.ConceptCardError, concept_card_review_service.ConceptCardReviewError, ValueError) as exc:
            db.session.rollback()
            return concept_card_review_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "card": concept_card_service.serialize_concept_card(card),
                "review": concept_card_review_service.serialize_review_record(review_record),
                "assignment": concept_card_review_service.serialize_assignment(assignment),
            },
            "Concept card reviewer assigned.",
            audit_context,
        )

    app.add_url_rule(
        "/api/concept-cards/review-queue",
        view_func=concept_card_review_queue_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/concept-cards/<card_uid>/reviews",
        view_func=concept_card_reviews_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/concept-cards/<card_uid>/review",
        view_func=concept_card_review_action_api,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/concept-cards/<card_uid>/assign-reviewer",
        view_func=concept_card_assign_reviewer_api,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/concept-cards/<card_uid>/review-case",
        view_func=teacher_alignment_review_case_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/concept-cards/<card_uid>/generate-draft",
        view_func=teacher_alignment_generate_draft_api,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/concept-cards/<card_uid>/draft",
        view_func=teacher_alignment_draft_api,
        methods=["GET", "PUT"],
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
