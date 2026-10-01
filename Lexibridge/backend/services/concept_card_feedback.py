"""Teacher-facing triage workflow for student Concept Card feedback."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from sqlalchemy import or_

from services import audit_records
from services import concept_card_review
from services import course_review_policy


FEEDBACK_SOURCE = "student_concept_card"
TRIAGE_ACTIONS = {
    "acknowledge",
    "mark_resolved",
    "mark_duplicate",
    "reject_feedback",
    "request_card_revision",
    "reopen_card_for_review",
    "link_to_existing_review",
    "add_teacher_note",
}

ACTION_TO_STATUS = {
    "acknowledge": "triaged",
    "mark_resolved": "resolved",
    "mark_duplicate": "duplicate",
    "reject_feedback": "rejected",
    "request_card_revision": "linked_to_review",
    "reopen_card_for_review": "linked_to_review",
    "link_to_existing_review": "linked_to_review",
}

ACTION_TO_AUDIT_EVENT = {
    "acknowledge": "concept_card_feedback_triaged",
    "add_teacher_note": "concept_card_feedback_triaged",
    "mark_resolved": "concept_card_feedback_resolved",
    "mark_duplicate": "concept_card_feedback_triaged",
    "reject_feedback": "concept_card_feedback_triaged",
    "request_card_revision": "concept_card_feedback_linked_to_review",
    "link_to_existing_review": "concept_card_feedback_linked_to_review",
    "reopen_card_for_review": "concept_card_reopened_from_student_feedback",
}


class ConceptCardFeedbackError(ValueError):
    """Stable error for Concept Card feedback queue operations."""

    def __init__(self, message: str, reason: str = "concept_card_feedback_error"):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class FeedbackQueueResult:
    items: list[Any]
    page: int
    per_page: int
    total: int

    @property
    def pagination(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "per_page": self.per_page,
            "total": self.total,
            "has_next": self.page * self.per_page < self.total,
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _loads(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def feedback_uid(feedback: Any) -> str:
    uid = _text(getattr(feedback, "feedback_uid", ""))
    return uid or f"feedback-{getattr(feedback, 'id', '')}"


def feedback_card_uid(feedback: Any) -> str:
    uid = _text(getattr(feedback, "card_uid", ""))
    if uid:
        return uid
    if _text(getattr(feedback, "feedback_source", "")) == FEEDBACK_SOURCE:
        actual = _text(getattr(feedback, "actual_result", ""))
        if actual:
            return actual
    meta = _loads(getattr(feedback, "evidence_comment", ""), {})
    if isinstance(meta, dict):
        return _text(meta.get("card_uid"))
    return ""


def get_feedback_by_uid(session: Any, feedback_model: Any, uid: str) -> Any:
    uid = _text(uid)
    if not uid:
        raise ConceptCardFeedbackError("feedback_uid is required.", "missing_feedback_uid")
    feedback = session.query(feedback_model).filter_by(feedback_uid=uid).first()
    if feedback is None and uid.startswith("feedback-"):
        raw_id = uid.split("feedback-", 1)[1]
        if raw_id.isdigit():
            feedback = session.get(feedback_model, int(raw_id))
    if feedback is None and uid.isdigit():
        feedback = session.get(feedback_model, int(uid))
    if feedback is None:
        raise ConceptCardFeedbackError("Feedback not found.", "feedback_not_found")
    return feedback


def get_card_for_feedback(session: Any, card_model: Any, feedback: Any) -> Any | None:
    card_uid = feedback_card_uid(feedback)
    if card_uid:
        card = session.query(card_model).filter_by(card_uid=card_uid).first()
        if card is not None:
            return card
    return session.query(card_model).filter_by(
        english_term=getattr(feedback, "english_term", ""),
        course=getattr(feedback, "course", ""),
        chapter=getattr(feedback, "chapter", ""),
    ).first()


def _permission_card(card: Any | None, feedback: Any) -> Any:
    if card is not None:
        return card
    return SimpleNamespace(
        card_uid=feedback_card_uid(feedback),
        course=getattr(feedback, "course", ""),
        chapter=getattr(feedback, "chapter", ""),
        status="approved",
        risk_labels="[]",
    )


def _can_reviewer_access_feedback(session: Any, permission_model: Any, card: Any | None, feedback: Any, reviewer_context: Any) -> tuple[bool, str]:
    reviewer_role = _text(getattr(reviewer_context, "role", "") if not isinstance(reviewer_context, dict) else reviewer_context.get("role") or reviewer_context.get("reviewer_role"))
    if reviewer_role == "admin":
        return True, ""
    ok, _permission, reason = course_review_policy.can_reviewer_review_card(
        session,
        permission_model,
        _permission_card(card, feedback),
        reviewer_context,
    )
    return ok, reason


def get_concept_card_feedback_queue(
    session: Any,
    feedback_model: Any,
    card_model: Any,
    review_model: Any,
    permission_model: Any,
    reviewer_context: Any,
    filters: dict[str, Any] | None = None,
) -> FeedbackQueueResult:
    filters = dict(filters or {})
    page = _int_range(filters.get("page"), 1, 1, 10_000)
    per_page = _int_range(filters.get("per_page"), 20, 1, 100)
    query = session.query(feedback_model).filter(feedback_model.feedback_source == FEEDBACK_SOURCE)
    if _text(filters.get("course")):
        query = query.filter(feedback_model.course == _text(filters.get("course")))
    if _text(filters.get("chapter")):
        query = query.filter(feedback_model.chapter == _text(filters.get("chapter")))
    if _text(filters.get("feedback_type")):
        query = query.filter(feedback_model.feedback_type == _text(filters.get("feedback_type")))
    if _text(filters.get("status")):
        query = query.filter(feedback_model.status == _text(filters.get("status")))
    if _text(filters.get("priority")):
        query = query.filter(feedback_model.priority == _text(filters.get("priority")))
    if _text(filters.get("q")):
        like = f"%{_text(filters.get('q'))}%"
        query = query.filter(or_(
            feedback_model.english_term.ilike(like),
            feedback_model.chinese_term.ilike(like),
            feedback_model.feedback_content.ilike(like),
            feedback_model.reported_issue.ilike(like),
            feedback_model.expected_result.ilike(like),
        ))
    rows = query.order_by(feedback_model.id.desc()).all()
    visible_rows = []
    for feedback in rows:
        card = get_card_for_feedback(session, card_model, feedback)
        ok, _reason = _can_reviewer_access_feedback(session, permission_model, card, feedback, reviewer_context)
        if ok:
            visible_rows.append(feedback)
    total = len(visible_rows)
    return FeedbackQueueResult(
        items=visible_rows[(page - 1) * per_page: page * per_page],
        page=page,
        per_page=per_page,
        total=total,
    )


def get_feedback_for_card(
    session: Any,
    feedback_model: Any,
    card_model: Any,
    permission_model: Any,
    card_uid: str,
    reviewer_context: Any,
) -> list[Any]:
    card = session.query(card_model).filter_by(card_uid=_text(card_uid)).first()
    if card is None:
        raise ConceptCardFeedbackError("Concept card not found.", "card_not_found")
    ok, _permission, reason = course_review_policy.can_reviewer_review_card(session, permission_model, card, reviewer_context)
    if not ok:
        raise ConceptCardFeedbackError("Current reviewer cannot access this card feedback.", reason or "permission_denied")
    return (
        session.query(feedback_model)
        .filter(feedback_model.feedback_source == FEEDBACK_SOURCE, feedback_model.card_uid == card.card_uid)
        .order_by(feedback_model.id.desc())
        .all()
    )


def _latest_review(session: Any, review_model: Any, card_uid: str) -> Any | None:
    if not card_uid:
        return None
    return session.query(review_model).filter_by(card_uid=card_uid).order_by(review_model.id.desc()).first()


def serialize_feedback_queue_item(session: Any, feedback: Any, card_model: Any, review_model: Any) -> dict[str, Any]:
    card = get_card_for_feedback(session, card_model, feedback)
    card_uid = feedback_card_uid(feedback)
    latest_review = _latest_review(session, review_model, card_uid)
    return {
        "feedback_uid": feedback_uid(feedback),
        "feedback_id": getattr(feedback, "id", None),
        "card_uid": card_uid,
        "english_term": getattr(feedback, "english_term", "") or getattr(card, "english_term", ""),
        "chinese_term": getattr(feedback, "chinese_term", "") or getattr(card, "chinese_term", ""),
        "course": getattr(feedback, "course", "") or getattr(card, "course", ""),
        "chapter": getattr(feedback, "chapter", "") or getattr(card, "chapter", ""),
        "feedback_type": getattr(feedback, "feedback_type", ""),
        "message": getattr(feedback, "message", "") or getattr(feedback, "reported_issue", "") or getattr(feedback, "feedback_content", ""),
        "message_snippet": (getattr(feedback, "reported_issue", "") or getattr(feedback, "feedback_content", ""))[:240],
        "suggested_chinese_term": getattr(feedback, "suggested_chinese_term", "") or getattr(feedback, "expected_result", ""),
        "submitted_by": getattr(feedback, "user_id", None),
        "status": getattr(feedback, "status", ""),
        "priority": getattr(feedback, "priority", ""),
        "created_at": getattr(feedback, "created_at", ""),
        "updated_at": getattr(feedback, "updated_at", ""),
        "handled_by": getattr(feedback, "handled_by", None),
        "handled_at": getattr(feedback, "handled_at", ""),
        "teacher_note": getattr(feedback, "teacher_note", ""),
        "linked_review_uid": getattr(feedback, "linked_review_uid", ""),
        "card_status": getattr(card, "status", ""),
        "card_risk_labels": _loads(getattr(card, "risk_labels", "[]"), []) if card is not None else [],
        "latest_review_summary": concept_card_review.serialize_review_record(latest_review) if latest_review else None,
    }


def validate_feedback_triage_action(feedback: Any, reviewer_context: Any, action: str, data: dict[str, Any]) -> None:
    del feedback
    role = _text(getattr(reviewer_context, "role", "") if not isinstance(reviewer_context, dict) else reviewer_context.get("role") or reviewer_context.get("reviewer_role"))
    if role not in {"teacher", "admin"}:
        raise ConceptCardFeedbackError("teacher or admin is required for feedback triage.", "permission_denied")
    if action not in TRIAGE_ACTIONS:
        raise ConceptCardFeedbackError(f"action must be one of {sorted(TRIAGE_ACTIONS)}.", "invalid_action")
    if action in {"request_card_revision", "reopen_card_for_review"} and not _text(data.get("reason_code")):
        raise ConceptCardFeedbackError("reason_code is required for this action.", "missing_reason_code")
    if action in {"request_card_revision", "reopen_card_for_review", "reject_feedback"} and not _text(data.get("teacher_note")):
        raise ConceptCardFeedbackError("teacher_note is required for this action.", "missing_teacher_note")


def _create_triage_record(
    session: Any,
    triage_model: Any,
    feedback: Any,
    card: Any | None,
    action: str,
    previous_status: str,
    new_status: str,
    reviewer_context: Any,
    data: dict[str, Any],
    *,
    linked_review_uid: str = "",
    now_fn=None,
) -> Any:
    now = now_fn() if now_fn else ""
    record = triage_model(
        triage_uid=str(uuid.uuid4()),
        feedback_uid=feedback_uid(feedback),
        card_uid=feedback_card_uid(feedback),
        course=getattr(feedback, "course", "") or getattr(card, "course", ""),
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        handled_by=getattr(reviewer_context, "id", None) if not isinstance(reviewer_context, dict) else reviewer_context.get("id") or reviewer_context.get("reviewer_id"),
        handler_role=getattr(reviewer_context, "role", "") if not isinstance(reviewer_context, dict) else reviewer_context.get("role") or reviewer_context.get("reviewer_role"),
        reason_code=_text(data.get("reason_code")),
        teacher_note=_text(data.get("teacher_note")),
        linked_review_uid=linked_review_uid,
        created_at=now,
    )
    session.add(record)
    session.flush()
    return record


def _record_feedback_audit(
    session: Any,
    audit_model: Any | None,
    event_type: str,
    feedback: Any,
    triage_record: Any | None,
    *,
    card: Any | None,
    action: str,
    previous_status: str,
    new_status: str,
    audit_context: dict[str, Any] | None,
    now_fn=None,
) -> Any | None:
    if audit_model is None:
        return None
    return audit_records.create_audit_record(
        session,
        audit_model,
        {
            "event_type": event_type,
            "target_type": "concept_card_feedback",
            "target_uid": feedback_uid(feedback),
            "source": "api",
            "result": "success",
            "input_payload": {
                "feedback_uid": feedback_uid(feedback),
                "card_uid": feedback_card_uid(feedback),
                "course": getattr(feedback, "course", "") or getattr(card, "course", ""),
                "action": action,
                "previous_status": previous_status,
                "new_status": new_status,
            },
            "output_payload": {
                "triage_uid": getattr(triage_record, "triage_uid", ""),
                "linked_review_uid": getattr(feedback, "linked_review_uid", ""),
            },
            "changed_fields": ["status"] if previous_status != new_status else [],
        },
        audit_context=audit_context,
        now_fn=now_fn,
        commit=False,
    )


def triage_concept_card_feedback(
    session: Any,
    feedback_model: Any,
    card_model: Any,
    review_model: Any,
    triage_model: Any,
    permission_model: Any,
    feedback_uid_value: str,
    reviewer_context: Any,
    action: str,
    data: dict[str, Any] | None = None,
    *,
    audit_model: Any | None = None,
    audit_context: dict[str, Any] | None = None,
    policy_model: Any | None = None,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, Any | None, Any | None]:
    data = dict(data or {})
    action = _text(action)
    feedback = get_feedback_by_uid(session, feedback_model, feedback_uid_value)
    card = get_card_for_feedback(session, card_model, feedback)
    ok, reason = _can_reviewer_access_feedback(session, permission_model, card, feedback, reviewer_context)
    if not ok:
        raise ConceptCardFeedbackError("Current reviewer cannot triage this feedback.", reason or "permission_denied")
    validate_feedback_triage_action(feedback, reviewer_context, action, data)
    previous_status = getattr(feedback, "status", "")
    new_status = ACTION_TO_STATUS.get(action, previous_status or "triaged")
    linked_review = None
    if action in {"request_card_revision", "reopen_card_for_review"}:
        if card is None:
            raise ConceptCardFeedbackError("Linked Concept Card is required for this action.", "card_not_found")
        review_payload = {
            "reason_code": _text(data.get("reason_code")),
            "review_comment": _text(data.get("teacher_note")),
            "required_changes": data.get("required_changes") or [],
        }
        kwargs = {
            "audit_model": audit_model,
            "audit_context": audit_context,
            "policy_model": policy_model,
            "permission_model": permission_model,
            "now_fn": now_fn,
            "commit": False,
        }
        if action == "request_card_revision":
            _card, linked_review = concept_card_review.request_card_revision(
                session,
                card_model,
                review_model,
                card.card_uid,
                reviewer_context,
                review_payload,
                **kwargs,
            )
        else:
            _card, linked_review = concept_card_review.reopen_concept_card(
                session,
                card_model,
                review_model,
                card.card_uid,
                reviewer_context,
                review_payload,
                **kwargs,
            )
        feedback.linked_review_uid = getattr(linked_review, "review_uid", "")
        feedback.linked_card_uid = card.card_uid
    elif action == "link_to_existing_review":
        feedback.linked_review_uid = _text(data.get("linked_review_uid"))
    feedback.status = new_status
    feedback.handled_by = getattr(reviewer_context, "id", None) if not isinstance(reviewer_context, dict) else reviewer_context.get("id") or reviewer_context.get("reviewer_id")
    feedback.handler_role = getattr(reviewer_context, "role", "") if not isinstance(reviewer_context, dict) else reviewer_context.get("role") or reviewer_context.get("reviewer_role")
    feedback.handled_at = now_fn() if now_fn else ""
    feedback.teacher_note = _text(data.get("teacher_note"))
    feedback.resolution_note = feedback.teacher_note or getattr(feedback, "resolution_note", "")
    if new_status in {"resolved", "rejected", "duplicate", "closed"}:
        feedback.resolved_by = feedback.handled_by
        feedback.resolved_at = feedback.handled_at
    feedback.updated_at = feedback.handled_at
    session.flush()
    triage_record = _create_triage_record(
        session,
        triage_model,
        feedback,
        card,
        action,
        previous_status,
        new_status,
        reviewer_context,
        data,
        linked_review_uid=getattr(linked_review, "review_uid", "") or getattr(feedback, "linked_review_uid", ""),
        now_fn=now_fn,
    )
    _record_feedback_audit(
        session,
        audit_model,
        ACTION_TO_AUDIT_EVENT.get(action, "concept_card_feedback_triaged"),
        feedback,
        triage_record,
        card=card,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        audit_context=audit_context,
        now_fn=now_fn,
    )
    if commit:
        session.commit()
    else:
        session.flush()
    return feedback, triage_record, linked_review


def serialize_feedback_triage_record(record: Any) -> dict[str, Any]:
    if record is None:
        return {}
    return {
        "triage_uid": getattr(record, "triage_uid", ""),
        "feedback_uid": getattr(record, "feedback_uid", ""),
        "card_uid": getattr(record, "card_uid", ""),
        "course": getattr(record, "course", ""),
        "action": getattr(record, "action", ""),
        "previous_status": getattr(record, "previous_status", ""),
        "new_status": getattr(record, "new_status", ""),
        "handled_by": getattr(record, "handled_by", None),
        "handler_role": getattr(record, "handler_role", ""),
        "reason_code": getattr(record, "reason_code", ""),
        "teacher_note": getattr(record, "teacher_note", ""),
        "linked_review_uid": getattr(record, "linked_review_uid", ""),
        "created_at": getattr(record, "created_at", ""),
    }
