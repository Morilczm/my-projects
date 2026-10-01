"""Teacher-facing learning analytics for approved Concept Cards.

The analytics layer is intentionally aggregate-only. It never returns student
email/name details, provider raw output, AuditRecord payloads, or review
override reasons.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from sqlalchemy import or_

from services import course_review_policy
from services import student_course_access


APPROVED_STATUS = "approved"
FEEDBACK_SOURCE = "student_concept_card"
UNRESOLVED_FEEDBACK_STATUSES = {"submitted", "triaged", "linked_to_review", "open"}
RESOLVED_FEEDBACK_STATUSES = {"resolved", "rejected", "duplicate", "closed"}
SORT_VALUES = {"feedback_count", "mastery_rate", "unmastered", "updated_at"}


class TeacherLearningAnalyticsError(ValueError):
    """Stable analytics error for API responses."""

    def __init__(self, message: str, reason: str = "teacher_learning_analytics_error"):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class CardAnalyticsResult:
    items: list[dict[str, Any]]
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


def _role(user: Any) -> str:
    if isinstance(user, dict):
        return _text(user.get("role") or user.get("reviewer_role") or user.get("actor_role"))
    return _text(getattr(user, "role", ""))


def _user_id(user: Any) -> int | None:
    value = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _loads(value: Any, fallback: Any) -> Any:
    if value in ("", None):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bool(value: Any, default: bool = False) -> bool:
    if value in ("", None):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _rate(numerator: int, denominator: int) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _feedback_card_uid(feedback: Any) -> str:
    card_uid = _text(getattr(feedback, "card_uid", ""))
    if card_uid:
        return card_uid
    actual = _text(getattr(feedback, "actual_result", ""))
    if actual:
        return actual
    meta = _loads(getattr(feedback, "evidence_comment", ""), {})
    if isinstance(meta, dict):
        return _text(meta.get("card_uid"))
    return ""


def _known_approved_courses(session: Any, card_model: Any) -> list[str]:
    return sorted({
        _text(row[0])
        for row in session.query(card_model.course)
        .filter(card_model.status == APPROVED_STATUS)
        .distinct()
        .all()
        if _text(row[0])
    })


def _is_student_visible_course(session: Any, visibility_policy_model: Any, course: str) -> bool:
    policy = student_course_access.get_course_student_visibility_policy(session, visibility_policy_model, course)
    fields = student_course_access.serialize_course_student_visibility_policy(policy, course)
    return fields.get("status", "active") == "active" and fields.get("visibility") in {"public", "enrolled_only"}


def get_authorized_courses(
    session: Any,
    card_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    course: str = "",
) -> list[str]:
    requested_course = _text(course)
    courses = [requested_course] if requested_course else _known_approved_courses(session, card_model)
    role = _role(reviewer_context)
    if role == "admin":
        return sorted(set(courses))
    reviewer_id = _user_id(reviewer_context)
    if not reviewer_id:
        return []
    allowed: list[str] = []
    for course_name in courses:
        if not _is_student_visible_course(session, visibility_policy_model, course_name):
            continue
        permission_card = SimpleNamespace(course=course_name, chapter="", status=APPROVED_STATUS, risk_labels="[]")
        ok, _permission, _reason = course_review_policy.can_reviewer_review_card(
            session,
            permission_model,
            permission_card,
            reviewer_context,
        )
        if ok:
            allowed.append(course_name)
    return sorted(set(allowed))


def _approved_cards(
    session: Any,
    card_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    course: str = "",
    chapter: str = "",
    q: str = "",
) -> list[Any]:
    courses = get_authorized_courses(
        session,
        card_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=course,
    )
    if not courses:
        return []
    query = session.query(card_model).filter(card_model.status == APPROVED_STATUS, card_model.course.in_(courses))
    if _text(chapter):
        query = query.filter(card_model.chapter == _text(chapter))
    if _text(q):
        like = f"%{_text(q)}%"
        query = query.filter(or_(
            card_model.english_term.ilike(like),
            card_model.chinese_term.ilike(like),
            card_model.course.ilike(like),
            card_model.chapter.ilike(like),
            card_model.concept_scope.ilike(like),
        ))
    return query.order_by(card_model.course.asc(), card_model.chapter.asc(), card_model.english_term.asc()).all()


def _enrolled_student_ids(session: Any, membership_model: Any, course: str) -> list[int]:
    rows = (
        session.query(membership_model.user_id)
        .filter(
            membership_model.course == _text(course),
            membership_model.status == "active",
            membership_model.role_in_course == "student",
        )
        .all()
    )
    return sorted({int(row[0]) for row in rows if row[0] is not None})


def _student_ids_by_course(session: Any, membership_model: Any, courses: list[str]) -> dict[str, list[int]]:
    return {course: _enrolled_student_ids(session, membership_model, course) for course in sorted(set(courses))}


def _states_by_card(session: Any, state_model: Any, card_uids: list[str], student_ids: set[int]) -> dict[str, list[Any]]:
    if not card_uids or not student_ids:
        return {}
    rows = (
        session.query(state_model)
        .filter(state_model.card_uid.in_(card_uids), state_model.user_id.in_(sorted(student_ids)))
        .all()
    )
    grouped: dict[str, list[Any]] = {}
    for state in rows:
        grouped.setdefault(getattr(state, "card_uid", ""), []).append(state)
    return grouped


def _feedback_by_card(session: Any, feedback_model: Any, card_uids: list[str]) -> dict[str, list[Any]]:
    if not card_uids:
        return {}
    rows = (
        session.query(feedback_model)
        .filter(feedback_model.feedback_source == FEEDBACK_SOURCE)
        .all()
    )
    card_set = set(card_uids)
    grouped: dict[str, list[Any]] = {}
    for feedback in rows:
        uid = _feedback_card_uid(feedback)
        if uid in card_set:
            grouped.setdefault(uid, []).append(feedback)
    for values in grouped.values():
        values.sort(key=lambda item: (_text(getattr(item, "created_at", "")), getattr(item, "id", 0)), reverse=True)
    return grouped


def _viewed(state: Any) -> bool:
    return _int(getattr(state, "view_count", 0)) > 0 or bool(_text(getattr(state, "last_viewed_at", "")))


def _feedback_status(feedback: Any) -> str:
    return _text(getattr(feedback, "status", "")) or "submitted"


def _priority_hint(metrics: dict[str, Any]) -> str:
    if metrics["feedback_count"] >= 2 and metrics["mastery_rate"] < 0.5:
        return "high_feedback_low_mastery"
    if metrics["unresolved_feedback_count"] >= 2:
        return "many_unresolved_feedback"
    if metrics["viewed_count"] == 0 and metrics["enrolled_student_count"] > 0:
        return "missing_learning_activity"
    if metrics["favorited_count"] >= 1 and metrics["mastery_rate"] < 0.5:
        return "frequently_favorited_unmastered"
    if metrics["unresolved_feedback_count"] > 0 or (metrics["feedback_count"] > 0 and metrics["mastery_rate"] < 0.7):
        return "needs_teacher_attention"
    return "stable"


def _card_metrics(card: Any, states: list[Any], feedbacks: list[Any], enrolled_student_count: int) -> dict[str, Any]:
    mastered_count = sum(1 for state in states if bool(getattr(state, "mastered", False)))
    favorited_count = sum(1 for state in states if bool(getattr(state, "favorited", False)))
    viewed_count = sum(1 for state in states if _viewed(state))
    total_view_count = sum(_int(getattr(state, "view_count", 0)) for state in states)
    unresolved_count = sum(1 for feedback in feedbacks if _feedback_status(feedback) in UNRESOLVED_FEEDBACK_STATUSES)
    resolved_count = sum(1 for feedback in feedbacks if _feedback_status(feedback) in RESOLVED_FEEDBACK_STATUSES)
    latest_feedback = feedbacks[0] if feedbacks else None
    opportunity_count = enrolled_student_count
    metrics = {
        "card_uid": getattr(card, "card_uid", ""),
        "english_term": getattr(card, "english_term", ""),
        "chinese_term": getattr(card, "chinese_term", ""),
        "course": getattr(card, "course", ""),
        "chapter": getattr(card, "chapter", ""),
        "enrolled_student_count": enrolled_student_count,
        "mastered_count": mastered_count,
        "unmastered_count": max(0, opportunity_count - mastered_count),
        "favorited_count": favorited_count,
        "viewed_count": viewed_count,
        "total_view_count": total_view_count,
        "feedback_count": len(feedbacks),
        "unresolved_feedback_count": unresolved_count,
        "resolved_feedback_count": resolved_count,
        "mastery_rate": _rate(mastered_count, opportunity_count),
        "feedback_rate": _rate(len(feedbacks), opportunity_count),
        "latest_feedback_type": _text(getattr(latest_feedback, "feedback_type", "")) if latest_feedback else "",
        "latest_feedback_status": _feedback_status(latest_feedback) if latest_feedback else "",
        "risk_labels": course_review_policy.normalize_list(getattr(card, "risk_labels", "[]")),
        "reviewed_at": getattr(card, "reviewed_at", ""),
        "updated_at": getattr(card, "updated_at", ""),
    }
    metrics["priority_hint"] = _priority_hint(metrics)
    return metrics


def _build_card_items(
    session: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    cards: list[Any],
) -> list[dict[str, Any]]:
    courses = sorted({_text(getattr(card, "course", "")) for card in cards if _text(getattr(card, "course", ""))})
    student_ids_by_course = _student_ids_by_course(session, membership_model, courses)
    all_student_ids = {student_id for ids in student_ids_by_course.values() for student_id in ids}
    card_uids = [getattr(card, "card_uid", "") for card in cards]
    states = _states_by_card(session, state_model, card_uids, all_student_ids)
    feedbacks = _feedback_by_card(session, feedback_model, card_uids)
    return [
        _card_metrics(
            card,
            states.get(getattr(card, "card_uid", ""), []),
            feedbacks.get(getattr(card, "card_uid", ""), []),
            len(student_ids_by_course.get(_text(getattr(card, "course", "")), [])),
        )
        for card in cards
    ]


def _course_summary(items: list[dict[str, Any]], enrolled_by_course: dict[str, list[int]]) -> dict[str, Any]:
    approved = len(items)
    courses = sorted({_text(item.get("course")) for item in items if _text(item.get("course"))})
    enrolled_total = sum(len(enrolled_by_course.get(course, [])) for course in courses)
    opportunities = sum(len(enrolled_by_course.get(_text(item.get("course")), [])) for item in items)
    mastered = sum(_int(item.get("mastered_count")) for item in items)
    favorited = sum(_int(item.get("favorited_count")) for item in items)
    feedback_count = sum(_int(item.get("feedback_count")) for item in items)
    unresolved = sum(_int(item.get("unresolved_feedback_count")) for item in items)
    resolved = sum(_int(item.get("resolved_feedback_count")) for item in items)
    total_views = sum(_int(item.get("total_view_count")) for item in items)
    viewed_cards = sum(1 for item in items if _int(item.get("viewed_count")) > 0)
    return {
        "course": courses[0] if len(courses) == 1 else "",
        "courses": courses,
        "approved_card_count": approved,
        "enrolled_student_count": enrolled_total,
        "viewed_card_count": viewed_cards,
        "mastered_card_count": mastered,
        "unmastered_card_count": max(0, opportunities - mastered),
        "favorited_card_count": favorited,
        "feedback_count": feedback_count,
        "unresolved_feedback_count": unresolved,
        "resolved_feedback_count": resolved,
        "mastery_rate": _rate(mastered, opportunities),
        "feedback_rate": _rate(feedback_count, approved),
        "average_view_count_per_card": round(float(total_views) / float(approved), 4) if approved else 0.0,
    }


def _chapter_summaries(items: list[dict[str, Any]], enrolled_by_course: dict[str, list[int]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        key = (_text(item.get("course")), _text(item.get("chapter")))
        buckets.setdefault(key, []).append(item)
    rows: list[dict[str, Any]] = []
    for (course, chapter), values in sorted(buckets.items()):
        opportunities = len(values) * len(enrolled_by_course.get(course, []))
        mastered = sum(_int(item.get("mastered_count")) for item in values)
        feedback_count = sum(_int(item.get("feedback_count")) for item in values)
        unresolved = sum(_int(item.get("unresolved_feedback_count")) for item in values)
        rows.append({
            "course": course,
            "chapter": chapter,
            "approved_card_count": len(values),
            "mastered_count": mastered,
            "unmastered_count": max(0, opportunities - mastered),
            "feedback_count": feedback_count,
            "unresolved_feedback_count": unresolved,
            "mastery_rate": _rate(mastered, opportunities),
        })
    return rows


def _enrolled_by_course_for_items(session: Any, membership_model: Any, items: list[dict[str, Any]]) -> dict[str, list[int]]:
    courses = sorted({_text(item.get("course")) for item in items if _text(item.get("course"))})
    return _student_ids_by_course(session, membership_model, courses)


def _sort_cards(items: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    sort = _text(sort) or "feedback_count"
    if sort not in SORT_VALUES:
        sort = "feedback_count"
    if sort == "mastery_rate":
        return sorted(items, key=lambda item: (float(item.get("mastery_rate") or 0), -_int(item.get("feedback_count")), item.get("english_term", "")))
    if sort == "unmastered":
        return sorted(items, key=lambda item: (-_int(item.get("unmastered_count")), float(item.get("mastery_rate") or 0), item.get("english_term", "")))
    if sort == "updated_at":
        return sorted(items, key=lambda item: (_text(item.get("updated_at")), _text(item.get("reviewed_at"))), reverse=True)
    return sorted(items, key=lambda item: (-_int(item.get("feedback_count")), -_int(item.get("unresolved_feedback_count")), float(item.get("mastery_rate") or 0), item.get("english_term", "")))


def get_card_learning_analytics(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    card_uid: str = "",
    course: str = "",
    chapter: str = "",
    q: str = "",
    sort: str = "feedback_count",
    page: int = 1,
    per_page: int = 20,
) -> CardAnalyticsResult:
    cards = _approved_cards(
        session,
        card_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=course,
        chapter=chapter,
        q=q,
    )
    if _text(card_uid):
        cards = [card for card in cards if getattr(card, "card_uid", "") == _text(card_uid)]
    items = _sort_cards(_build_card_items(session, state_model, feedback_model, membership_model, cards), sort)
    page = _int_range(page, 1, 1, 10_000)
    per_page = _int_range(per_page, 20, 1, 100)
    total = len(items)
    return CardAnalyticsResult(
        items=items[(page - 1) * per_page: page * per_page],
        page=page,
        per_page=per_page,
        total=total,
    )


def get_low_mastery_cards(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    course: str = "",
    chapter: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    result = get_card_learning_analytics(
        session,
        card_model,
        state_model,
        feedback_model,
        membership_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=course,
        chapter=chapter,
        sort="mastery_rate",
        page=1,
        per_page=max(1, min(int(limit or 20), 100)),
    )
    return result.items


def get_feedback_hotspots(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    course: str = "",
    chapter: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    result = get_card_learning_analytics(
        session,
        card_model,
        state_model,
        feedback_model,
        membership_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=course,
        chapter=chapter,
        sort="feedback_count",
        page=1,
        per_page=max(1, min(int(limit or 20), 100)),
    )
    return [item for item in result.items if _int(item.get("feedback_count")) > 0]


def get_unresolved_feedback_summary(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    course: str = "",
    chapter: str = "",
) -> dict[str, Any]:
    cards = _approved_cards(
        session,
        card_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=course,
        chapter=chapter,
    )
    items = _build_card_items(session, state_model, feedback_model, membership_model, cards)
    by_status: dict[str, int] = {}
    for uid, feedbacks in _feedback_by_card(session, feedback_model, [getattr(card, "card_uid", "") for card in cards]).items():
        del uid
        for feedback in feedbacks:
            status = _feedback_status(feedback)
            by_status[status] = by_status.get(status, 0) + 1
    return {
        "unresolved_feedback_count": sum(_int(item.get("unresolved_feedback_count")) for item in items),
        "resolved_feedback_count": sum(_int(item.get("resolved_feedback_count")) for item in items),
        "by_status": by_status,
    }


def get_teacher_chapter_analytics(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    course: str = "",
) -> list[dict[str, Any]]:
    cards = _approved_cards(
        session,
        card_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=course,
    )
    items = _build_card_items(session, state_model, feedback_model, membership_model, cards)
    enrolled_by_course = _enrolled_by_course_for_items(session, membership_model, items)
    return _chapter_summaries(items, enrolled_by_course)


def get_teacher_course_analytics(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    *,
    course: str = "",
    chapter: str = "",
    include_cards: bool = False,
    include_feedback_hotspots: bool = True,
    limit: int = 20,
) -> dict[str, Any]:
    cards = _approved_cards(
        session,
        card_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=course,
        chapter=chapter,
    )
    items = _build_card_items(session, state_model, feedback_model, membership_model, cards)
    enrolled_by_course = _enrolled_by_course_for_items(session, membership_model, items)
    low_mastery = _sort_cards(items, "mastery_rate")[: max(1, min(int(limit or 20), 100))]
    hotspots = _sort_cards([item for item in items if _int(item.get("feedback_count")) > 0], "feedback_count")[: max(1, min(int(limit or 20), 100))]
    return {
        "course_summary": _course_summary(items, enrolled_by_course),
        "chapter_summaries": _chapter_summaries(items, enrolled_by_course),
        "low_mastery_cards": low_mastery,
        "feedback_hotspots": hotspots if include_feedback_hotspots else [],
        "unresolved_feedback": {
            "unresolved_feedback_count": sum(_int(item.get("unresolved_feedback_count")) for item in items),
            "resolved_feedback_count": sum(_int(item.get("resolved_feedback_count")) for item in items),
        },
        "cards": items[: max(1, min(int(limit or 20), 100))] if include_cards else [],
    }


def serialize_course_analytics(summary: dict[str, Any]) -> dict[str, Any]:
    return dict(summary or {})


def serialize_card_analytics(item: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "card_uid",
        "english_term",
        "chinese_term",
        "course",
        "chapter",
        "enrolled_student_count",
        "mastered_count",
        "unmastered_count",
        "favorited_count",
        "viewed_count",
        "feedback_count",
        "unresolved_feedback_count",
        "resolved_feedback_count",
        "mastery_rate",
        "feedback_rate",
        "latest_feedback_type",
        "latest_feedback_status",
        "risk_labels",
        "reviewed_at",
        "updated_at",
        "priority_hint",
    }
    return {key: item.get(key) for key in allowed if key in item}


def export_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "course": item.get("course", ""),
            "chapter": item.get("chapter", ""),
            "english_term": item.get("english_term", ""),
            "chinese_term": item.get("chinese_term", ""),
            "mastered_count": item.get("mastered_count", 0),
            "favorited_count": item.get("favorited_count", 0),
            "viewed_count": item.get("viewed_count", 0),
            "feedback_count": item.get("feedback_count", 0),
            "unresolved_feedback_count": item.get("unresolved_feedback_count", 0),
            "priority_hint": item.get("priority_hint", ""),
        }
        for item in items
    ]


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "course,chapter,english_term,chinese_term,mastered_count,favorited_count,viewed_count,feedback_count,unresolved_feedback_count,priority_hint\n"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def export_teacher_learning_report(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    permission_model: Any,
    visibility_policy_model: Any,
    reviewer_context: Any,
    filters: dict[str, Any] | None = None,
    *,
    format: str = "csv",
) -> dict[str, Any]:
    del format
    filters = dict(filters or {})
    result = get_card_learning_analytics(
        session,
        card_model,
        state_model,
        feedback_model,
        membership_model,
        permission_model,
        visibility_policy_model,
        reviewer_context,
        course=_text(filters.get("course")),
        chapter=_text(filters.get("chapter")),
        q=_text(filters.get("q")),
        sort=_text(filters.get("sort") or "feedback_count"),
        page=1,
        per_page=_int_range(filters.get("per_page"), 100, 1, 500),
    )
    rows = export_rows(result.items)
    return {"items": rows, "count": len(rows)}
