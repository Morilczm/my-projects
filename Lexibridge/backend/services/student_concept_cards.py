"""Student-facing ConceptAlignmentCard learning helpers.

This service deliberately exposes only teacher-approved cards. It does not
modify ConceptAlignmentCard review state and does not surface provider raw
output or internal audit details to students.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_

from services import concept_card_publication


APPROVED_STATUS = "approved"
FEEDBACK_SOURCE = "student_concept_card"
FEEDBACK_TYPE_MAP = {
    "translation_issue": "translation_error",
    "evidence_issue": "evidence_error",
    "explanation_unclear": "concept_explanation_error",
    "duplicate": "other",
    "other": "other",
}


class StudentConceptCardError(ValueError):
    """Raised for stable student concept card API errors."""

    def __init__(self, message: str, reason: str = "student_concept_card_error"):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class StudentConceptCardListResult:
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


def _loads_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bool_filter(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _card_evidence(card: Any, side: str) -> list[Any]:
    field = "english_evidence" if side == "english" else "chinese_evidence"
    value = getattr(card, field, "[]")
    parsed = _loads_json(value, [])
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, str) and parsed.strip():
        return [{"snippet": parsed.strip()}]
    return []


def _truncate(value: Any, max_chars: int = 300) -> str:
    text = _text(value)
    return text if len(text) <= max_chars else f"{text[: max_chars - 1]}..."


def _short_explanation(value: Any) -> str:
    return _truncate(value, 160)


def _state_for_card(states_by_card_uid: dict[str, Any], card_uid: str) -> Any | None:
    return states_by_card_uid.get(card_uid)


def _feedback_counts(feedback_model: Any, user_id: int | None = None) -> dict[str, int]:
    query = feedback_model.query.filter_by(feedback_source=FEEDBACK_SOURCE)
    if user_id is not None:
        query = query.filter_by(user_id=int(user_id))
    counts: dict[str, int] = {}
    for item in query.all():
        card_uid = _text(getattr(item, "actual_result", ""))
        if card_uid:
            counts[card_uid] = counts.get(card_uid, 0) + 1
    return counts


def _source_summary_from_evidence(card: Any, limit: int = 4) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    sources: list[dict[str, Any]] = []
    for item in _card_evidence(card, "english") + _card_evidence(card, "chinese"):
        if isinstance(item, str):
            continue
        source_uid = _text(item.get("source_uid") or item.get("source_title"))
        source_title = _text(item.get("source_title") or item.get("source_uid") or "Evidence source")
        key = (source_uid, source_title)
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "source_uid": source_uid,
            "source_title": source_title,
            "source_role": _text(item.get("source_role") or item.get("source_type")),
            "trust_level": _text(item.get("trust_level")),
            "quality_status": _text(item.get("quality_status")),
        })
        if len(sources) >= limit:
            break
    return sources


def _public_badges(card: Any) -> list[str]:
    badges = ["Teacher reviewed"]
    if _card_evidence(card, "english") or _card_evidence(card, "chinese"):
        badges.append("Evidence-based")
    if _source_summary_from_evidence(card, 1):
        badges.append("Source-backed")
    return badges


def _public_warning(card: Any) -> str:
    if not _card_evidence(card, "english") and not _card_evidence(card, "chinese"):
        return "Evidence unavailable"
    return ""


def _state_dict(state: Any | None) -> dict[str, Any]:
    if state is None:
        return {
            "favorited": False,
            "mastered": False,
            "mastered_at": "",
            "last_viewed_at": "",
            "view_count": 0,
            "personal_note": "",
        }
    return {
        "state_uid": getattr(state, "state_uid", ""),
        "favorited": bool(getattr(state, "favorited", False)),
        "mastered": bool(getattr(state, "mastered", False)),
        "mastered_at": getattr(state, "mastered_at", ""),
        "last_viewed_at": getattr(state, "last_viewed_at", ""),
        "view_count": int(getattr(state, "view_count", 0) or 0),
        "personal_note": getattr(state, "personal_note", ""),
    }


def _serialize_evidence_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {
            "chunk_uid": "",
            "source_uid": "",
            "source_title": "Evidence",
            "course": "",
            "chapter": "",
            "language": "",
            "source_role": "",
            "trust_level": "",
            "quality_status": "",
            "source_locator": "",
            "snippet": _truncate(item, 300),
            "score": None,
            "retrieval_reason": "",
            "risk_labels": [],
            "parse_uid": "",
            "parse_block_uid": "",
        }
    return {
        "chunk_uid": _text(item.get("chunk_uid")),
        "source_uid": _text(item.get("source_uid")),
        "source_title": _text(item.get("source_title") or item.get("source_uid") or "Evidence source"),
        "course": _text(item.get("course")),
        "chapter": _text(item.get("chapter")),
        "language": _text(item.get("language")),
        "source_role": _text(item.get("source_role") or item.get("source_type")),
        "trust_level": _text(item.get("trust_level")),
        "quality_status": _text(item.get("quality_status")),
        "source_locator": _text(item.get("source_locator") or item.get("page_number") or item.get("slide_number")),
        "snippet": _truncate(item.get("snippet") or item.get("evidence_snippet") or item.get("text"), 300),
        "score": item.get("score", item.get("retrieval_score")),
        "retrieval_reason": _text(item.get("retrieval_reason")),
        "risk_labels": _loads_json(item.get("risk_labels", []), []),
        "parse_uid": _text(item.get("parse_uid")),
        "parse_block_uid": _text(item.get("parse_block_uid")),
    }


def _serialize_evidence(items: list[Any], limit: int = 8) -> list[dict[str, Any]]:
    return [_serialize_evidence_item(item) for item in items[:limit]]


def get_approved_card(session: Any, card_model: Any, card_uid: str) -> Any:
    uid = _text(card_uid)
    if not uid:
        raise StudentConceptCardError("Concept card uid is required.", "missing_card_uid")
    card = session.query(card_model).filter_by(card_uid=uid, status=APPROVED_STATUS).first()
    if card is None:
        raise StudentConceptCardError("Concept card is not available for student learning.", "concept_card_not_available")
    return card


def get_publishable_approved_card(
    session: Any,
    card_model: Any,
    card_uid: str,
    *,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
) -> Any:
    card = get_approved_card(session, card_model, card_uid)
    if source_model is not None and not concept_card_publication.card_is_publishable(
        session,
        card,
        source_model=source_model,
        chunk_model=chunk_model,
    ):
        raise StudentConceptCardError(
            "Concept card is not available for student learning.",
            "concept_card_source_unavailable",
        )
    return card


def get_states_by_card_uid(session: Any, state_model: Any, user_id: int, card_uids: list[str]) -> dict[str, Any]:
    if not card_uids:
        return {}
    rows = (
        session.query(state_model)
        .filter(state_model.user_id == int(user_id), state_model.card_uid.in_(card_uids))
        .all()
    )
    return {row.card_uid: row for row in rows}


def get_or_create_state(
    session: Any,
    state_model: Any,
    *,
    user_id: int,
    card_uid: str,
    course: str = "",
    now_fn=None,
) -> Any:
    state = session.query(state_model).filter_by(user_id=int(user_id), card_uid=_text(card_uid)).first()
    now = now_fn() if now_fn else ""
    if state is None:
        state = state_model(
            state_uid=str(uuid.uuid4()),
            user_id=int(user_id),
            card_uid=_text(card_uid),
            course=_text(course),
            favorited=False,
            mastered=False,
            mastered_at="",
            last_viewed_at="",
            view_count=0,
            personal_note="",
            created_at=now,
            updated_at=now,
        )
        session.add(state)
        session.flush()
    return state


def _base_card_query(session: Any, card_model: Any, filters: dict[str, Any]) -> Any:
    query = session.query(card_model).filter(card_model.status == APPROVED_STATUS)
    allowed_courses = filters.get("allowed_courses")
    if allowed_courses is not None:
        allowed_courses = [_text(item) for item in allowed_courses if _text(item)]
        if not allowed_courses:
            return query.filter(card_model.course == "__no_student_course_access__")
        query = query.filter(card_model.course.in_(allowed_courses))
    course = _text(filters.get("course"))
    chapter = _text(filters.get("chapter"))
    q = _text(filters.get("q"))
    if course:
        query = query.filter(card_model.course == course)
    if chapter:
        query = query.filter(card_model.chapter == chapter)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            card_model.english_term.ilike(like),
            card_model.chinese_term.ilike(like),
            card_model.course.ilike(like),
            card_model.chapter.ilike(like),
            card_model.concept_scope.ilike(like),
            card_model.english_explanation.ilike(like),
            card_model.chinese_explanation.ilike(like),
        ))
    return query


def list_student_concept_cards(
    session: Any,
    card_model: Any,
    state_model: Any,
    feedback_model: Any,
    *,
    user: Any,
    filters: dict[str, Any] | None = None,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
) -> StudentConceptCardListResult:
    filters = dict(filters or {})
    page = _int_range(filters.get("page"), 1, 1, 10_000)
    per_page = _int_range(filters.get("per_page"), 20, 1, 100)
    query = _base_card_query(session, card_model, filters)

    favorited = _bool_filter(filters.get("favorited"))
    mastered = _bool_filter(filters.get("mastered"))
    scope = _text(filters.get("scope"))
    if scope == "favorited":
        favorited = True
    elif scope == "mastered":
        mastered = True
    elif scope == "unmastered":
        mastered = False

    if favorited is True:
        matching_card_uids = [
            row[0]
            for row in session.query(state_model.card_uid)
            .filter(state_model.user_id == int(user.id), state_model.favorited.is_(True))
            .all()
        ]
        query = query.filter(card_model.card_uid.in_(matching_card_uids or ["__no_student_state_match__"]))
    elif favorited is False:
        excluded_card_uids = [
            row[0]
            for row in session.query(state_model.card_uid)
            .filter(state_model.user_id == int(user.id), state_model.favorited.is_(True))
            .all()
        ]
        if excluded_card_uids:
            query = query.filter(~card_model.card_uid.in_(excluded_card_uids))

    if mastered is True:
        matching_card_uids = [
            row[0]
            for row in session.query(state_model.card_uid)
            .filter(state_model.user_id == int(user.id), state_model.mastered.is_(True))
            .all()
        ]
        query = query.filter(card_model.card_uid.in_(matching_card_uids or ["__no_student_state_match__"]))
    elif mastered is False:
        excluded_card_uids = [
            row[0]
            for row in session.query(state_model.card_uid)
            .filter(state_model.user_id == int(user.id), state_model.mastered.is_(True))
            .all()
        ]
        if excluded_card_uids:
            query = query.filter(~card_model.card_uid.in_(excluded_card_uids))

    has_feedback = _bool_filter(filters.get("has_feedback"))
    if has_feedback is not None:
        feedback_card_uids = [
            row[0]
            for row in session.query(feedback_model.actual_result)
            .filter_by(user_id=int(user.id), feedback_source=FEEDBACK_SOURCE)
            .all()
            if _text(row[0])
        ]
        if has_feedback:
            query = query.filter(card_model.card_uid.in_(feedback_card_uids or ["__no_feedback_match__"]))
        elif feedback_card_uids:
            query = query.filter(~card_model.card_uid.in_(feedback_card_uids))

    ordered_items = (
        query.order_by(card_model.updated_at.desc(), card_model.id.desc())
        .all()
    )
    if source_model is not None:
        ordered_items = [
            card
            for card in ordered_items
            if concept_card_publication.card_is_publishable(
                session,
                card,
                source_model=source_model,
                chunk_model=chunk_model,
            )
        ]
    total = len(ordered_items)
    items = ordered_items[(page - 1) * per_page: page * per_page]
    return StudentConceptCardListResult(items=items, page=page, per_page=per_page, total=total)


def serialize_student_card_summary(
    card: Any,
    state: Any | None = None,
    feedback_count: int = 0,
    *,
    session: Any | None = None,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
    parse_model: Any | None = None,
) -> dict[str, Any]:
    english = _card_evidence(card, "english")
    chinese = _card_evidence(card, "chinese")
    state_data = _state_dict(state)
    data = {
        "card_uid": card.card_uid,
        "english_term": card.english_term,
        "chinese_term": card.chinese_term,
        "course": card.course,
        "chapter": card.chapter,
        "concept_scope": card.concept_scope,
        "status": APPROVED_STATUS,
        "short_english_explanation": _short_explanation(card.english_explanation),
        "short_chinese_explanation": _short_explanation(card.chinese_explanation),
        "evidence_count": len(english) + len(chinese),
        "source_summary": _source_summary_from_evidence(card),
        "favorited": state_data["favorited"],
        "mastered": state_data["mastered"],
        "has_feedback": feedback_count > 0,
        "feedback_count": feedback_count,
        "public_badges": _public_badges(card),
        "public_warning": _public_warning(card),
        "updated_at": card.updated_at,
    }
    if session is not None:
        data = concept_card_publication.enrich_card_payload(
            session,
            card,
            data,
            source_model=source_model,
            chunk_model=chunk_model,
            parse_model=parse_model,
        )
    return data


def serialize_student_card_detail(
    card: Any,
    state: Any | None = None,
    feedback_count: int = 0,
    *,
    session: Any | None = None,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
    parse_model: Any | None = None,
) -> dict[str, Any]:
    data = serialize_student_card_summary(
        card,
        state=state,
        feedback_count=feedback_count,
        session=session,
        source_model=source_model,
        chunk_model=chunk_model,
        parse_model=parse_model,
    )
    data.update({
        "english_explanation": card.english_explanation,
        "chinese_explanation": card.chinese_explanation,
        "english_evidence": data.get("english_evidence") or _serialize_evidence(_card_evidence(card, "english")),
        "chinese_evidence": data.get("chinese_evidence") or _serialize_evidence(_card_evidence(card, "chinese")),
        "retrieval_version": getattr(card, "retrieval_version", ""),
        "reviewed_by": getattr(card, "reviewed_by", None),
        "reviewed_at": getattr(card, "reviewed_at", ""),
        "student_state": _state_dict(state),
        "feedback_summary": {
            "count": feedback_count,
            "has_feedback": feedback_count > 0,
        },
        "public_risk_labels": _public_badges(card),
    })
    return data


def record_card_view(
    session: Any,
    state_model: Any,
    card: Any,
    *,
    user_id: int,
    now_fn=None,
    commit: bool = False,
) -> Any:
    state = get_or_create_state(session, state_model, user_id=user_id, card_uid=card.card_uid, course=card.course, now_fn=now_fn)
    now = now_fn() if now_fn else ""
    state.last_viewed_at = now or getattr(state, "last_viewed_at", "")
    state.view_count = int(getattr(state, "view_count", 0) or 0) + 1
    state.updated_at = now or getattr(state, "updated_at", "")
    session.flush()
    if commit:
        session.commit()
    return state


def update_student_state(
    session: Any,
    state_model: Any,
    card: Any,
    user: Any,
    data: dict[str, Any],
    *,
    now_fn=None,
    commit: bool = False,
) -> Any:
    state = get_or_create_state(session, state_model, user_id=user.id, card_uid=card.card_uid, course=card.course, now_fn=now_fn)
    now = now_fn() if now_fn else ""
    if "favorited" in data:
        state.favorited = bool(data.get("favorited"))
    if "mastered" in data:
        state.mastered = bool(data.get("mastered"))
        state.mastered_at = now if state.mastered else ""
    if "personal_note" in data:
        state.personal_note = _truncate(data.get("personal_note"), 2000)
    state.updated_at = now or getattr(state, "updated_at", "")
    session.flush()
    if commit:
        session.commit()
    return state


def create_student_feedback(
    session: Any,
    feedback_model: Any,
    card: Any,
    user: Any,
    data: dict[str, Any],
    *,
    now_fn=None,
    commit: bool = False,
) -> Any:
    message = _text(data.get("message") or data.get("feedback_content") or data.get("reported_issue"))
    if not message:
        raise StudentConceptCardError("Feedback message is required.", "missing_feedback_message")
    incoming_type = _text(data.get("feedback_type")) or "other"
    feedback_type = FEEDBACK_TYPE_MAP.get(incoming_type, "other")
    suggested = _text(data.get("suggested_chinese_term"))
    now = now_fn() if now_fn else ""
    feedback = feedback_model(
        feedback_uid=str(uuid.uuid4()),
        term_id=0,
        user_id=user.id,
        user_role=getattr(user, "role", ""),
        course=card.course,
        chapter=card.chapter,
        card_uid=card.card_uid,
        english_term=card.english_term,
        chinese_term=card.chinese_term,
        feedback_type=feedback_type,
        feedback_source=FEEDBACK_SOURCE,
        severity="normal",
        priority="P2",
        message=message,
        suggested_chinese_term=suggested,
        feedback_content=message,
        reported_issue=message,
        expected_result=suggested,
        actual_result=card.card_uid,
        evidence_comment=_dumps_json({
            "card_uid": card.card_uid,
            "original_feedback_type": incoming_type,
            "suggested_chinese_term": suggested,
        }),
        classification="teacher_review_needed",
        root_cause="unknown",
        status="submitted",
        linked_card_uid=card.card_uid,
        created_at=now,
        updated_at=now,
    )
    session.add(feedback)
    session.flush()
    if commit:
        session.commit()
    return feedback


def serialize_feedback_result(feedback: Any) -> dict[str, Any]:
    return {
        "feedback_uid": getattr(feedback, "feedback_uid", ""),
        "feedback_id": feedback.id,
        "feedback_status": feedback.status,
        "card_uid": feedback.actual_result,
        "feedback_type": feedback.feedback_type,
        "feedback_source": feedback.feedback_source,
        "created_at": feedback.created_at,
    }


def export_rows(cards: list[Any], states_by_card_uid: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for card in cards:
        state = _state_for_card(states_by_card_uid, card.card_uid)
        state_data = _state_dict(state)
        rows.append({
            "english_term": card.english_term,
            "chinese_term": card.chinese_term,
            "course": card.course,
            "chapter": card.chapter,
            "concept_scope": card.concept_scope,
            "english_explanation": card.english_explanation,
            "chinese_explanation": card.chinese_explanation,
            "source_summary": _dumps_json(_source_summary_from_evidence(card)),
            "mastered": state_data["mastered"],
            "favorited": state_data["favorited"],
        })
    return rows


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
