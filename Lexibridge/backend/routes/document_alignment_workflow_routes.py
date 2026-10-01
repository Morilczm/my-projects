"""Thin HTTP adapters for the formal document-alignment workflow API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import make_response, request
from werkzeug.exceptions import BadRequest

from routes.shared import RouteCoreDependencies
from services.document_alignment_workflow_application import (
    OUTCOME_CREATED,
    OUTCOME_IDEMPOTENCY_CONFLICT,
    OUTCOME_INVALID_REQUEST,
    OUTCOME_NO_USABLE_CHUNKS,
    OUTCOME_PARSE_BLOCKED,
    OUTCOME_PERSISTENCE_ERROR,
    OUTCOME_REUSED,
    OUTCOME_SOURCE_NOT_AVAILABLE,
    OUTCOME_SOURCE_NOT_GOVERNED,
    StartDocumentAlignmentWorkflowCommand,
    start_document_alignment_workflow,
)
from services.document_alignment_workflow_queries import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    QUERY_OUTCOME_FORBIDDEN,
    QUERY_OUTCOME_FOUND,
    QUERY_OUTCOME_INVALID_REQUEST,
    QUERY_OUTCOME_NOT_FOUND,
    QUERY_OUTCOME_PERSISTENCE_ERROR,
    DocumentAlignmentQueryActor,
    GetDocumentAlignmentWorkflowRunCommand,
    ListDocumentAlignmentWorkflowItemsCommand,
    get_document_alignment_workflow_run,
    list_document_alignment_workflow_items,
)


ROUTE_MARKER = "document_alignment_workflow_routes"
MAX_IDEMPOTENCY_KEY_LENGTH = 128
MAX_SAFE_ERROR_MESSAGE_LENGTH = 500
RETRY_AFTER_SECONDS = 2
ADMISSION_OUTCOME_HTTP_STATUS = {
    OUTCOME_INVALID_REQUEST: 400,
    OUTCOME_SOURCE_NOT_AVAILABLE: 404,
    OUTCOME_SOURCE_NOT_GOVERNED: 422,
    OUTCOME_PARSE_BLOCKED: 422,
    OUTCOME_NO_USABLE_CHUNKS: 422,
    OUTCOME_IDEMPOTENCY_CONFLICT: 409,
    OUTCOME_PERSISTENCE_ERROR: 500,
}
QUERY_OUTCOME_HTTP_STATUS = {
    QUERY_OUTCOME_NOT_FOUND: 404,
    QUERY_OUTCOME_FORBIDDEN: 404,
    QUERY_OUTCOME_INVALID_REQUEST: 400,
    QUERY_OUTCOME_PERSISTENCE_ERROR: 500,
}


@dataclass(frozen=True)
class DocumentAlignmentWorkflowRouteDependencies:
    admission_dependencies_factory: Callable[[Any], Any]
    query_dependencies_factory: Callable[[], Any]
    start_service: Callable[..., Any] = start_document_alignment_workflow
    get_run_service: Callable[..., Any] = get_document_alignment_workflow_run
    list_items_service: Callable[..., Any] = list_document_alignment_workflow_items


def _actor_from_user(user: Any) -> DocumentAlignmentQueryActor:
    return DocumentAlignmentQueryActor(
        actor_uid=str(getattr(user, "id", "") or ""),
        role=str(getattr(user, "role", "") or ""),
    )


def _safe_error_message(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip() or fallback
    folded = text.casefold()
    forbidden = (
        "lexibridge_sentinel_secret",
        "authorization:",
        "bearer ",
        "cookie:",
        "traceback",
        "sqlalchemy",
        "sk-",
    )
    if any(marker in folded for marker in forbidden):
        return fallback
    return text[:MAX_SAFE_ERROR_MESSAGE_LENGTH]


def _with_response_headers(response_or_tuple: Any, audit_context: dict[str, Any], **headers: str):
    response = make_response(response_or_tuple)
    request_id = str(audit_context.get("request_id", "") or "")
    if request_id:
        response.headers["X-Request-ID"] = request_id
    for name, value in headers.items():
        response.headers[name.replace("_", "-")] = str(value)
    return response


def _success(core, data, audit_context, *, status=200, headers=None):
    response = core.api_success_with_audit_context(
        data,
        "Operation completed.",
        audit_context,
    )
    response = _with_response_headers(response, audit_context, **(headers or {}))
    response.status_code = status
    return response


def _error(core, audit_context, error_code, message, status):
    response = core.api_error_with_audit_context(
        error_code,
        _safe_error_message(message, "Document alignment request failed safely."),
        status,
        audit_context,
    )
    return _with_response_headers(response, audit_context)


def _authenticate(core: RouteCoreDependencies):
    audit_context = core.get_route_audit_context()
    user, error_response = core.require_current_user({"teacher", "admin"})
    if error_response:
        response = core.attach_request_id_to_response(error_response, audit_context)
        return None, audit_context, _with_response_headers(response, audit_context)
    return user, core.get_route_audit_context(user), None


def _validate_idempotency_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError("Idempotency-Key must contain 1 to 128 characters.")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError("Idempotency-Key contains invalid control characters.")
    return text


def _parse_start_body() -> dict[str, Any]:
    if not request.is_json:
        raise TypeError("Content-Type must be application/json.")
    try:
        data = request.get_json(silent=False)
    except BadRequest as exc:
        raise ValueError("Request body must contain valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    unknown = set(data) - {"source_uid"}
    if unknown:
        raise ValueError("Request body contains unsupported fields.")
    source_uid = str(data.get("source_uid") or "").strip()
    if not source_uid or len(source_uid) > 64:
        raise ValueError("source_uid is required and must not exceed 64 characters.")
    return {"source_uid": source_uid}


def _run_summary_data(run: Any) -> dict[str, Any]:
    return {
        "run_uid": run.run_uid,
        "workflow_version": run.workflow_version,
        "status": run.status,
        "stage": run.stage,
        "source_uid": run.source_uid,
        "source_title": run.source_title,
        "source_filename": run.source_filename,
        "course": run.course,
        "chapter": run.chapter,
        "requested_by": run.requested_by,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "total_items": run.total_items,
        "ready_for_review_items": run.ready_for_review_items,
        "blocked_items": run.blocked_items,
        "failed_items": run.failed_items,
        "warning_count": run.warning_count,
        "progress_percent": run.progress_percent,
        "safe_error_code": run.safe_error_code,
        "safe_error_message": run.safe_error_message,
        "consistency_warnings": list(run.consistency_warnings),
        "is_terminal": run.is_terminal,
        "can_view_items": run.can_view_items,
        "can_review_results": run.can_review_results,
    }


def _item_summary_data(item: Any) -> dict[str, Any]:
    return {
        "item_uid": item.item_uid,
        "candidate_term": item.candidate_term,
        "normalized_term": item.normalized_term,
        "status": item.status,
        "stage": item.stage,
        "source_chunk_count": item.source_chunk_count,
        "risk_labels": list(item.risk_labels),
        "draft_card_uid": item.draft_card_uid,
        "verification_run_uid": item.verification_run_uid,
        "confidence_score": item.confidence_score,
        "confidence_summary": item.confidence_summary,
        "recommendation": item.recommendation,
        "safe_error_code": item.safe_error_code,
        "safe_error_message": item.safe_error_message,
        "retry_count": item.retry_count,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "consistency_warnings": list(item.consistency_warnings),
        "is_terminal": item.is_terminal,
        "is_reviewable": item.is_reviewable,
    }


def _query_error(core, audit_context, result):
    status = QUERY_OUTCOME_HTTP_STATUS.get(result.outcome, 500)
    code = result.error_code or "DOCUMENT_ALIGNMENT_QUERY_ERROR"
    message = result.error_message or "Workflow state could not be read."
    return _error(core, audit_context, code, message, status)


def _parse_positive_integer(name: str, default: int, maximum: int | None = None) -> int:
    values = request.args.getlist(name)
    if len(values) > 1:
        raise ValueError(f"{name} must be specified once.")
    raw = values[0] if values else str(default)
    if not raw or not raw.isdigit():
        raise ValueError(f"{name} must be a positive integer.")
    value = int(raw)
    if value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside the allowed range.")
    return value


def _parse_reviewable_only() -> bool:
    values = request.args.getlist("reviewable_only")
    if len(values) > 1:
        raise ValueError("reviewable_only must be specified once.")
    if not values:
        return False
    if values[0] == "true":
        return True
    if values[0] == "false":
        return False
    raise ValueError("reviewable_only must be true or false.")


def _reject_get_body() -> None:
    if request.content_length not in (None, 0):
        raise ValueError("GET requests must not include a request body.")


def register_document_alignment_workflow_routes(
    app,
    *,
    core: RouteCoreDependencies,
    dependencies: DocumentAlignmentWorkflowRouteDependencies,
) -> None:
    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    def create_document_alignment_run():
        user, audit_context, auth_error = _authenticate(core)
        if auth_error:
            return auth_error
        try:
            idempotency_key = _validate_idempotency_key(request.headers.get("Idempotency-Key"))
            data = _parse_start_body()
            command = StartDocumentAlignmentWorkflowCommand(
                source_uid=data["source_uid"],
                requested_by=str(getattr(user, "id", "") or ""),
                request_id=str(audit_context.get("request_id", "") or ""),
                idempotency_key=idempotency_key,
            )
        except TypeError as exc:
            return _error(core, audit_context, "DOCUMENT_ALIGNMENT_UNSUPPORTED_MEDIA_TYPE", str(exc), 415)
        except ValueError as exc:
            return _error(core, audit_context, "DOCUMENT_ALIGNMENT_INVALID_REQUEST", str(exc), 400)

        result = dependencies.start_service(
            command,
            dependencies.admission_dependencies_factory(user),
        )
        if result.outcome not in {OUTCOME_CREATED, OUTCOME_REUSED}:
            return _error(
                core,
                audit_context,
                result.error_code or "DOCUMENT_ALIGNMENT_START_FAILED",
                result.error_message or "Document alignment workflow could not be started.",
                ADMISSION_OUTCOME_HTTP_STATUS.get(result.outcome, 500),
            )

        actor = _actor_from_user(user)
        query_result = dependencies.get_run_service(
            GetDocumentAlignmentWorkflowRunCommand(result.run_uid, actor),
            dependencies.query_dependencies_factory(),
        )
        if query_result.outcome != QUERY_OUTCOME_FOUND:
            return _query_error(core, audit_context, query_result)
        response_data = _run_summary_data(query_result.run)
        response_data.update({
            "reused": bool(result.reused),
            "status_url": f"/api/document-alignment-runs/{result.run_uid}",
            "items_url": f"/api/document-alignment-runs/{result.run_uid}/items",
        })
        return _success(
            core,
            response_data,
            audit_context,
            status=202,
            headers={
                "Location": response_data["status_url"],
                "Retry_After": str(RETRY_AFTER_SECONDS),
            },
        )

    def get_document_alignment_run(run_uid):
        user, audit_context, auth_error = _authenticate(core)
        if auth_error:
            return auth_error
        try:
            _reject_get_body()
        except ValueError as exc:
            return _error(
                core,
                audit_context,
                "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST",
                str(exc),
                400,
            )
        result = dependencies.get_run_service(
            GetDocumentAlignmentWorkflowRunCommand(run_uid, _actor_from_user(user)),
            dependencies.query_dependencies_factory(),
        )
        if result.outcome != QUERY_OUTCOME_FOUND:
            return _query_error(core, audit_context, result)
        return _success(core, _run_summary_data(result.run), audit_context)

    def list_document_alignment_run_items(run_uid):
        user, audit_context, auth_error = _authenticate(core)
        if auth_error:
            return auth_error
        try:
            _reject_get_body()
        except ValueError as exc:
            return _error(
                core,
                audit_context,
                "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST",
                str(exc),
                400,
            )
        unknown = set(request.args) - {"page", "page_size", "status", "reviewable_only"}
        if unknown:
            return _error(
                core,
                audit_context,
                "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST",
                "Unsupported query parameter.",
                400,
            )
        try:
            page = _parse_positive_integer("page", 1)
            page_size = _parse_positive_integer("page_size", DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)
            status_values = request.args.getlist("status")
            if len(status_values) > 1:
                raise ValueError("status must be specified once.")
            status = status_values[0].strip() if status_values else ""
            reviewable_only = _parse_reviewable_only()
        except ValueError as exc:
            return _error(
                core,
                audit_context,
                "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST",
                str(exc),
                400,
            )
        result = dependencies.list_items_service(
            ListDocumentAlignmentWorkflowItemsCommand(
                run_uid=run_uid,
                actor=_actor_from_user(user),
                page=page,
                page_size=page_size,
                status=status,
                reviewable_only=reviewable_only,
            ),
            dependencies.query_dependencies_factory(),
        )
        if result.outcome != QUERY_OUTCOME_FOUND:
            return _query_error(core, audit_context, result)
        result_page = result.page
        return _success(
            core,
            {
                "workflow_run_uid": result_page.workflow_run_uid,
                "items": [_item_summary_data(item) for item in result_page.items],
                "pagination": {
                    "page": result_page.page,
                    "page_size": result_page.page_size,
                    "total_items": result_page.total_items,
                    "total_pages": result_page.total_pages,
                    "has_next": result_page.has_next,
                    "has_previous": result_page.has_previous,
                },
            },
            audit_context,
        )

    targets = (
        ("/api/document-alignment-runs", "create_document_alignment_run", create_document_alignment_run, ["POST"]),
        ("/api/document-alignment-runs/<run_uid>", "get_document_alignment_run", get_document_alignment_run, ["GET"]),
        (
            "/api/document-alignment-runs/<run_uid>/items",
            "list_document_alignment_run_items",
            list_document_alignment_run_items,
            ["GET"],
        ),
    )
    for path, endpoint, view_func, methods in targets:
        for rule in app.url_map.iter_rules():
            if rule.rule == path and set(methods) & set(rule.methods):
                raise RuntimeError(f"Cannot register duplicate route {endpoint} for {path}.")
        app.add_url_rule(path, endpoint=endpoint, view_func=view_func, methods=methods)
    registered.add(ROUTE_MARKER)
