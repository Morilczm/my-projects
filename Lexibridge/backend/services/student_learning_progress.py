"""Student learning progress over approved, visible Concept Cards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services import student_course_access


APPROVED_STATUS = "approved"
FEEDBACK_SOURCE = "student_concept_card"


@dataclass(frozen=True)
class StudentProgressResult:
    overall: dict[str, Any]
    courses: list[dict[str, Any]]
    chapters: list[dict[str, Any]]
    recent_activity: list[dict[str, Any]]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rate(mastered: int, total: int) -> float:
    return round(mastered / total, 4) if total else 0.0


def _visible_course_names(
    session: Any,
    card_model: Any,
    membership_model: Any,
    policy_model: Any,
    user_context: Any,
) -> list[str]:
    known_courses = [
        row[0]
        for row in session.query(card_model.course)
        .filter(card_model.status == APPROVED_STATUS)
        .distinct()
        .all()
        if _text(row[0])
    ]
    return student_course_access.visible_courses_for_user(
        session,
        membership_model,
        policy_model,
        user_context,
        known_courses=known_courses,
    )


def get_visible_approved_cards(
    session: Any,
    card_model: Any,
    membership_model: Any,
    policy_model: Any,
    user_context: Any,
    *,
    filters: dict[str, Any] | None = None,
) -> list[Any]:
    filters = dict(filters or {})
    allowed_courses = _visible_course_names(session, card_model, membership_model, policy_model, user_context)
    if not allowed_courses:
        return []
    query = session.query(card_model).filter(
        card_model.status == APPROVED_STATUS,
        card_model.course.in_(allowed_courses),
    )
    course = _text(filters.get("course"))
    chapter = _text(filters.get("chapter"))
    if course:
        query = query.filter(card_model.course == course)
    if chapter:
        query = query.filter(card_model.chapter == chapter)
    return query.order_by(card_model.course.asc(), card_model.chapter.asc(), card_model.english_term.asc()).all()


def states_by_card_uid(session: Any, state_model: Any, user_id: int, card_uids: list[str]) -> dict[str, Any]:
    if not card_uids:
        return {}
    rows = (
        session.query(state_model)
        .filter(state_model.user_id == int(user_id), state_model.card_uid.in_(card_uids))
        .all()
    )
    return {row.card_uid: row for row in rows}


def feedback_count_for_student(session: Any, feedback_model: Any, user_context: Any, *, course: str = "", card_uids: list[str] | None = None) -> int:
    query = session.query(feedback_model).filter(
        feedback_model.user_id == int(getattr(user_context, "id", 0)),
        feedback_model.feedback_source == FEEDBACK_SOURCE,
    )
    if course:
        query = query.filter(feedback_model.course == course)
    if card_uids is not None:
        query = query.filter(feedback_model.card_uid.in_(card_uids or ["__no_visible_card__"]))
    return query.count()


def _summarize_cards(cards: list[Any], states: dict[str, Any], feedback_count: int) -> dict[str, Any]:
    total = len(cards)
    mastered = 0
    favorited = 0
    viewed = 0
    for card in cards:
        state = states.get(getattr(card, "card_uid", ""))
        if not state:
            continue
        if bool(getattr(state, "mastered", False)):
            mastered += 1
        if bool(getattr(state, "favorited", False)):
            favorited += 1
        if _int(getattr(state, "view_count", 0)) > 0 or _text(getattr(state, "last_viewed_at", "")):
            viewed += 1
    return {
        "visible_card_count": total,
        "mastered_count": mastered,
        "unmastered_count": max(0, total - mastered),
        "favorited_count": favorited,
        "viewed_count": viewed,
        "feedback_count": feedback_count,
        "mastery_rate": _rate(mastered, total),
    }


def _group_summary(cards: list[Any], states: dict[str, Any], feedback_model: Any, session: Any, user_context: Any, *, group: str) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[Any]] = {}
    for card in cards:
        key = (_text(getattr(card, "course", "")), _text(getattr(card, "chapter", "")) if group == "chapter" else "")
        buckets.setdefault(key, []).append(card)
    rows: list[dict[str, Any]] = []
    for (course, chapter), group_cards in sorted(buckets.items()):
        card_uids = [card.card_uid for card in group_cards]
        feedback_count = feedback_count_for_student(session, feedback_model, user_context, course=course, card_uids=card_uids)
        summary = _summarize_cards(group_cards, states, feedback_count)
        row = {"course": course, **summary}
        if group == "chapter":
            row["chapter"] = chapter
        rows.append(row)
    return rows


def get_student_recent_activity(session: Any, card_model: Any, state_model: Any, user_context: Any, visible_card_uids: list[str], limit: int = 10) -> list[dict[str, Any]]:
    if not visible_card_uids:
        return []
    rows = (
        session.query(state_model)
        .filter(state_model.user_id == int(getattr(user_context, "id", 0)), state_model.card_uid.in_(visible_card_uids))
        .order_by(state_model.updated_at.desc(), state_model.id.desc())
        .limit(max(1, min(int(limit or 10), 50)))
        .all()
    )
    cards = {
        card.card_uid: card
        for card in session.query(card_model).filter(card_model.card_uid.in_([row.card_uid for row in rows])).all()
    }
    activity: list[dict[str, Any]] = []
    for state in rows:
        card = cards.get(state.card_uid)
        if not card:
            continue
        activity.append({
            "card_uid": card.card_uid,
            "english_term": card.english_term,
            "chinese_term": card.chinese_term,
            "course": card.course,
            "chapter": card.chapter,
            "favorited": bool(getattr(state, "favorited", False)),
            "mastered": bool(getattr(state, "mastered", False)),
            "view_count": _int(getattr(state, "view_count", 0)),
            "last_viewed_at": getattr(state, "last_viewed_at", ""),
            "updated_at": getattr(state, "updated_at", ""),
        })
    return activity


def get_student_progress(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    membership_model: Any,
    policy_model: Any,
    user_context: Any,
    *,
    filters: dict[str, Any] | None = None,
) -> StudentProgressResult:
    filters = dict(filters or {})
    visible_cards = get_visible_approved_cards(
        session,
        card_model,
        membership_model,
        policy_model,
        user_context,
        filters=filters,
    )
    card_uids = [card.card_uid for card in visible_cards]
    states = states_by_card_uid(session, state_model, getattr(user_context, "id", 0), card_uids)
    overall_feedback_count = feedback_count_for_student(
        session,
        feedback_model,
        user_context,
        course=_text(filters.get("course")),
        card_uids=card_uids,
    )
    overall = _summarize_cards(visible_cards, states, overall_feedback_count)
    courses = _group_summary(visible_cards, states, feedback_model, session, user_context, group="course")
    chapters = _group_summary(visible_cards, states, feedback_model, session, user_context, group="chapter")
    include_recent = str(filters.get("include_recent", "true")).strip().lower() not in {"0", "false", "no"}
    recent_activity = get_student_recent_activity(session, card_model, state_model, user_context, card_uids) if include_recent else []
    return StudentProgressResult(overall=overall, courses=courses, chapters=chapters, recent_activity=recent_activity)


def get_unmastered_cards(
    session: Any,
    card_model: Any,
    state_model: Any,
    membership_model: Any,
    policy_model: Any,
    user_context: Any,
    *,
    course: str = "",
    chapter: str = "",
    limit: int = 20,
) -> list[Any]:
    cards = get_visible_approved_cards(
        session,
        card_model,
        membership_model,
        policy_model,
        user_context,
        filters={"course": course, "chapter": chapter},
    )
    states = states_by_card_uid(session, state_model, getattr(user_context, "id", 0), [card.card_uid for card in cards])
    unmastered = [card for card in cards if not bool(getattr(states.get(card.card_uid), "mastered", False))]
    return unmastered[: max(1, min(int(limit or 20), 100))]


def serialize_student_progress_summary(result: StudentProgressResult) -> dict[str, Any]:
    return {
        "overall": result.overall,
        "courses": result.courses,
        "chapters": result.chapters,
        "recent_activity": result.recent_activity,
    }
