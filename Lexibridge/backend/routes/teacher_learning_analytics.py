"""Teacher learning analytics route registration.

This module is a staged extraction from ``backend/app.py``. It intentionally
keeps the route handlers thin and delegates analytics behavior to
``services.teacher_learning_analytics``. It does not import ``backend.app`` or
create application/database objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Response, request

from services import teacher_learning_analytics as teacher_learning_analytics_service
from routes.shared import RouteCoreDependencies


ROUTE_MARKER = "teacher_learning_analytics_routes"
TARGET_ROUTES = {
    "/api/teacher/learning-analytics": "teacher_learning_analytics_api",
    "/api/teacher/learning-analytics/cards": "teacher_learning_analytics_cards_api",
    "/api/teacher/learning-analytics/export": "teacher_learning_analytics_export_api",
}


@dataclass(frozen=True)
class TeacherLearningAnalyticsModels:
    """Domain model dependencies for teacher learning analytics routes."""

    ConceptAlignmentCard: Any
    StudentConceptCardState: Any
    Feedback: Any
    StudentCourseMembership: Any
    CourseReviewPermission: Any
    CourseStudentVisibilityPolicy: Any


def register_teacher_learning_analytics_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: TeacherLearningAnalyticsModels,
) -> None:
    """Register teacher learning analytics routes on an existing Flask app."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    db = core.db

    def teacher_learning_analytics_error_response(exc, audit_context):
        reason = getattr(exc, "reason", "teacher_learning_analytics_error")
        if "permission" in reason or reason in {"teacher_analytics_permission_denied"}:
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

    def record_teacher_learning_analytics_audit(
        event_type,
        *,
        user=None,
        course="",
        chapter="",
        result_count=0,
        export_format="",
        audit_context=None,
    ):
        core.audit_record_service.create_audit_record(
            db.session,
            core.audit_record_model,
            {
                "event_type": event_type,
                "target_type": "teacher_learning_analytics",
                "target_uid": str(course or ""),
                "result": "success",
                "input_payload": {
                    "reviewer_id": getattr(user, "id", None),
                    "reviewer_role": getattr(user, "role", ""),
                    "course": course,
                    "chapter": chapter,
                },
                "output_payload": {
                    "result_count": result_count,
                    "export_format": export_format,
                },
                "changed_fields": [],
            },
            audit_context=audit_context,
            now_fn=core.current_time_text,
            commit=False,
        )

    def teacher_analytics_models():
        return (
            models.ConceptAlignmentCard,
            models.StudentConceptCardState,
            models.Feedback,
            models.StudentCourseMembership,
            models.CourseReviewPermission,
            models.CourseStudentVisibilityPolicy,
        )

    def teacher_learning_analytics_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        args = request.args.to_dict()
        include_cards = str(args.get("include_cards", "false")).strip().lower() in {"1", "true", "yes", "on"}
        include_feedback_hotspots = str(args.get("include_feedback_hotspots", "true")).strip().lower() not in {"0", "false", "no", "off"}
        try:
            limit = min(100, max(1, int(args.get("limit") or 20)))
        except (TypeError, ValueError):
            return core.api_error_with_audit_context(
                "VALIDATION_ERROR",
                "limit must be an integer.",
                400,
                audit_context,
                {"audit_error_code": "invalid_limit"},
            )
        try:
            result = teacher_learning_analytics_service.get_teacher_course_analytics(
                db.session,
                *teacher_analytics_models(),
                user,
                course=str(args.get("course") or "").strip(),
                chapter=str(args.get("chapter") or "").strip(),
                include_cards=include_cards,
                include_feedback_hotspots=include_feedback_hotspots,
                limit=limit,
            )
            summary = result.get("course_summary", {})
            record_teacher_learning_analytics_audit(
                "teacher_learning_analytics_viewed",
                user=user,
                course=str(args.get("course") or "").strip(),
                chapter=str(args.get("chapter") or "").strip(),
                result_count=summary.get("approved_card_count", 0),
                audit_context=audit_context,
            )
            db.session.commit()
        except teacher_learning_analytics_service.TeacherLearningAnalyticsError as exc:
            db.session.rollback()
            return teacher_learning_analytics_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            teacher_learning_analytics_service.serialize_course_analytics(result),
            audit_context=audit_context,
        )

    def teacher_learning_analytics_cards_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        args = request.args.to_dict()
        try:
            page = max(1, int(args.get("page") or 1))
            per_page = min(100, max(1, int(args.get("per_page") or 20)))
        except (TypeError, ValueError):
            return core.api_error_with_audit_context(
                "VALIDATION_ERROR",
                "page and per_page must be integers.",
                400,
                audit_context,
                {"audit_error_code": "invalid_pagination"},
            )
        try:
            result = teacher_learning_analytics_service.get_card_learning_analytics(
                db.session,
                *teacher_analytics_models(),
                user,
                course=str(args.get("course") or "").strip(),
                chapter=str(args.get("chapter") or "").strip(),
                q=str(args.get("q") or "").strip(),
                sort=str(args.get("sort") or "feedback_count").strip(),
                page=page,
                per_page=per_page,
            )
            record_teacher_learning_analytics_audit(
                "teacher_learning_analytics_cards_viewed",
                user=user,
                course=str(args.get("course") or "").strip(),
                chapter=str(args.get("chapter") or "").strip(),
                result_count=result.total,
                audit_context=audit_context,
            )
            db.session.commit()
        except teacher_learning_analytics_service.TeacherLearningAnalyticsError as exc:
            db.session.rollback()
            return teacher_learning_analytics_error_response(exc, audit_context)
        return core.api_success_with_audit_context(
            {
                "items": [teacher_learning_analytics_service.serialize_card_analytics(item) for item in result.items],
                "pagination": result.pagination,
            },
            audit_context=audit_context,
        )

    def teacher_learning_analytics_export_api():
        audit_context = core.get_route_audit_context()
        user, error_response = core.require_current_user({"teacher", "admin"})
        if error_response:
            return core.attach_request_id_to_response(error_response, audit_context)
        audit_context = core.get_route_audit_context(user)
        args = request.args.to_dict()
        export_format = str(args.get("format") or "csv").strip().lower()
        if export_format not in {"csv", "json"}:
            return core.api_error_with_audit_context(
                "VALIDATION_ERROR",
                "format must be csv or json.",
                400,
                audit_context,
                {"audit_error_code": "invalid_export_format"},
            )
        try:
            report = teacher_learning_analytics_service.export_teacher_learning_report(
                db.session,
                *teacher_analytics_models(),
                user,
                {
                    "course": args.get("course", ""),
                    "chapter": args.get("chapter", ""),
                    "q": args.get("q", ""),
                    "sort": args.get("sort", "feedback_count"),
                    "per_page": args.get("per_page", 100),
                },
                format=export_format,
            )
            record_teacher_learning_analytics_audit(
                "teacher_learning_report_exported",
                user=user,
                course=str(args.get("course") or "").strip(),
                chapter=str(args.get("chapter") or "").strip(),
                result_count=report.get("count", 0),
                export_format=export_format,
                audit_context=audit_context,
            )
            db.session.commit()
        except teacher_learning_analytics_service.TeacherLearningAnalyticsError as exc:
            db.session.rollback()
            return teacher_learning_analytics_error_response(exc, audit_context)
        if export_format == "json":
            return core.api_success_with_audit_context(report, audit_context=audit_context)
        csv_text = teacher_learning_analytics_service.rows_to_csv(report.get("items", []))
        response = Response(csv_text, mimetype="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=teacher_learning_analytics.csv"
        response.headers["X-Request-ID"] = audit_context.get("request_id", "")
        return response

    app.add_url_rule(
        "/api/teacher/learning-analytics",
        view_func=teacher_learning_analytics_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/teacher/learning-analytics/cards",
        view_func=teacher_learning_analytics_cards_api,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/teacher/learning-analytics/export",
        view_func=teacher_learning_analytics_export_api,
        methods=["GET"],
    )
    registered.add(ROUTE_MARKER)


def _assert_no_duplicate_target_routes(app) -> None:
    for path, endpoint in TARGET_ROUTES.items():
        for rule in app.url_map.iter_rules():
            if rule.rule == path and "GET" in rule.methods:
                raise RuntimeError(
                    f"Cannot register {endpoint}: GET {path} is already registered as {rule.endpoint}."
                )
