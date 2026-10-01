"""Course-scoped visibility rules for student Concept Card learning."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


MEMBERSHIP_STATUSES = {"active", "inactive", "revoked"}
ROLE_IN_COURSE = {"student", "teaching_assistant", "auditor", "teacher", "admin"}
VISIBILITY_VALUES = {"public", "enrolled_only", "private", "disabled"}
POLICY_STATUSES = {"active", "disabled"}
DEFAULT_VISIBILITY = "enrolled_only"


class StudentCourseAccessError(ValueError):
    """Stable error for student course access service operations."""

    def __init__(self, message: str, reason: str = "student_course_access_error"):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class StudentCourseAccessDecision:
    allowed: bool
    reason: str
    course: str
    visibility: str = DEFAULT_VISIBILITY
    policy_uid: str = ""
    membership_uid: str = ""
    role_in_course: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "course": self.course,
            "visibility": self.visibility,
            "policy_uid": self.policy_uid,
            "membership_uid": self.membership_uid,
            "role_in_course": self.role_in_course,
        }


@dataclass(frozen=True)
class StudentCourseListResult:
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


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _now(now_fn=None) -> str:
    return now_fn() if now_fn else ""


def normalize_membership_status(value: Any) -> str:
    status = _text(value) or "active"
    return status if status in MEMBERSHIP_STATUSES else "inactive"


def normalize_role(value: Any) -> str:
    role = _text(value) or "student"
    return role if role in ROLE_IN_COURSE else "student"


def normalize_visibility(value: Any) -> str:
    visibility = _text(value) or DEFAULT_VISIBILITY
    return visibility if visibility in VISIBILITY_VALUES else DEFAULT_VISIBILITY


def get_student_course_memberships(
    session: Any,
    membership_model: Any,
    *,
    user_id: int | None = None,
    status: str | None = "active",
    filters: dict[str, Any] | None = None,
) -> StudentCourseListResult:
    filters = dict(filters or {})
    page = _int_range(filters.get("page"), 1, 1, 10_000)
    per_page = _int_range(filters.get("per_page"), 50, 1, 100)
    query = session.query(membership_model)
    if user_id is not None:
        query = query.filter(membership_model.user_id == int(user_id))
    status_filter = _text(filters.get("status")) or _text(status)
    if status_filter:
        query = query.filter(membership_model.status == status_filter)
    course = _text(filters.get("course"))
    if course:
        query = query.filter(membership_model.course == course)
    total = query.count()
    items = (
        query.order_by(membership_model.course.asc(), membership_model.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return StudentCourseListResult(items=items, page=page, per_page=per_page, total=total)


def get_active_membership(session: Any, membership_model: Any, user_id: int, course: str) -> Any | None:
    course = _text(course)
    if not course:
        return None
    return (
        session.query(membership_model)
        .filter_by(user_id=int(user_id), course=course, status="active")
        .first()
    )


def add_student_course_membership(
    session: Any,
    membership_model: Any,
    user_id: int,
    course: str,
    data: dict[str, Any] | None = None,
    *,
    actor: Any = None,
    now_fn=None,
    commit: bool = False,
) -> Any:
    data = dict(data or {})
    course = _text(course or data.get("course"))
    if not course:
        raise StudentCourseAccessError("course is required.", "missing_course")
    if not user_id:
        raise StudentCourseAccessError("user_id is required.", "missing_user_id")
    membership = session.query(membership_model).filter_by(user_id=int(user_id), course=course).first()
    now = _now(now_fn)
    if membership is None:
        membership = membership_model(
            membership_uid=str(uuid.uuid4()),
            user_id=int(user_id),
            course=course,
            created_at=now,
        )
        session.add(membership)
    membership.role_in_course = normalize_role(data.get("role_in_course"))
    membership.status = normalize_membership_status(data.get("status") or "active")
    membership.enrolled_by = getattr(actor, "id", None) if actor is not None else data.get("enrolled_by")
    membership.enrolled_at = membership.enrolled_at or now
    if membership.status == "active":
        membership.revoked_by = None
        membership.revoked_at = ""
    membership.updated_at = now
    session.flush()
    if commit:
        session.commit()
    return membership


def revoke_student_course_membership(
    session: Any,
    membership_model: Any,
    membership_uid: str,
    *,
    actor: Any = None,
    now_fn=None,
    commit: bool = False,
) -> Any:
    membership = session.query(membership_model).filter_by(membership_uid=_text(membership_uid)).first()
    if membership is None:
        raise StudentCourseAccessError("membership not found.", "membership_not_found")
    membership.status = "revoked"
    membership.revoked_by = getattr(actor, "id", None) if actor is not None else None
    membership.revoked_at = _now(now_fn)
    membership.updated_at = membership.revoked_at
    session.flush()
    if commit:
        session.commit()
    return membership


def get_course_student_visibility_policy(session: Any, policy_model: Any, course: str) -> Any | None:
    course = _text(course)
    if not course:
        return None
    return session.query(policy_model).filter_by(course=course).order_by(policy_model.id.desc()).first()


def default_policy_dict(course: str) -> dict[str, Any]:
    return {
        "course": _text(course),
        "visibility": DEFAULT_VISIBILITY,
        "allow_auditor_view": False,
        "allow_teacher_preview": True,
        "allow_cross_course_search": False,
        "status": "active",
    }


def create_or_update_course_student_visibility_policy(
    session: Any,
    policy_model: Any,
    course: str,
    data: dict[str, Any] | None = None,
    *,
    actor: Any = None,
    now_fn=None,
    commit: bool = False,
) -> tuple[Any, bool]:
    data = dict(data or {})
    course = _text(course or data.get("course"))
    if not course:
        raise StudentCourseAccessError("course is required.", "missing_course")
    policy = get_course_student_visibility_policy(session, policy_model, course)
    created = False
    now = _now(now_fn)
    if policy is None:
        policy = policy_model(policy_uid=str(uuid.uuid4()), course=course, created_at=now)
        session.add(policy)
        created = True
    policy.visibility = normalize_visibility(data.get("visibility"))
    policy.allow_auditor_view = _bool(data.get("allow_auditor_view"), False)
    policy.allow_teacher_preview = _bool(data.get("allow_teacher_preview"), True)
    policy.allow_cross_course_search = _bool(data.get("allow_cross_course_search"), False)
    policy.status = _text(data.get("status")) or "active"
    if policy.status not in POLICY_STATUSES:
        policy.status = "disabled"
    actor_id = getattr(actor, "id", None) if actor is not None else None
    if created:
        policy.created_by = actor_id
    policy.updated_by = actor_id
    policy.updated_at = now
    session.flush()
    if commit:
        session.commit()
    return policy, created


def _policy_fields(policy: Any | None, course: str) -> dict[str, Any]:
    if policy is None:
        return default_policy_dict(course)
    if getattr(policy, "status", "active") != "active":
        return {
            "course": _text(course),
            "visibility": "disabled",
            "allow_auditor_view": False,
            "allow_teacher_preview": False,
            "allow_cross_course_search": False,
            "status": "disabled",
            "policy_uid": getattr(policy, "policy_uid", ""),
        }
    return {
        "course": _text(course),
        "visibility": normalize_visibility(getattr(policy, "visibility", DEFAULT_VISIBILITY)),
        "allow_auditor_view": bool(getattr(policy, "allow_auditor_view", False)),
        "allow_teacher_preview": bool(getattr(policy, "allow_teacher_preview", True)),
        "allow_cross_course_search": bool(getattr(policy, "allow_cross_course_search", False)),
        "status": getattr(policy, "status", "active"),
        "policy_uid": getattr(policy, "policy_uid", ""),
    }


def can_student_view_course(
    session: Any,
    membership_model: Any,
    policy_model: Any,
    user_context: Any,
    course: str,
) -> StudentCourseAccessDecision:
    course = _text(course)
    if not course:
        return StudentCourseAccessDecision(False, "missing_course", course)
    if user_context is None:
        return StudentCourseAccessDecision(False, "auth_required", course)
    policy = get_course_student_visibility_policy(session, policy_model, course)
    fields = _policy_fields(policy, course)
    visibility = fields["visibility"]
    if visibility == "disabled":
        return StudentCourseAccessDecision(False, "course_visibility_disabled", course, visibility, fields.get("policy_uid", ""))
    role = getattr(user_context, "role", "")
    if role == "admin":
        return StudentCourseAccessDecision(True, "admin_preview", course, visibility, fields.get("policy_uid", ""), role_in_course="admin")
    if role == "teacher":
        allowed = bool(fields.get("allow_teacher_preview", True))
        return StudentCourseAccessDecision(
            allowed,
            "teacher_preview_allowed" if allowed else "teacher_preview_disabled",
            course,
            visibility,
            fields.get("policy_uid", ""),
            role_in_course="teacher",
        )
    if visibility == "public":
        return StudentCourseAccessDecision(True, "course_public", course, visibility, fields.get("policy_uid", ""), role_in_course="student")
    if visibility == "private":
        return StudentCourseAccessDecision(False, "course_private", course, visibility, fields.get("policy_uid", ""))
    membership = get_active_membership(session, membership_model, getattr(user_context, "id", 0), course)
    if membership is None:
        return StudentCourseAccessDecision(False, "membership_required", course, visibility, fields.get("policy_uid", ""))
    role_in_course = normalize_role(getattr(membership, "role_in_course", "student"))
    if role_in_course == "auditor" and not fields.get("allow_auditor_view", False):
        return StudentCourseAccessDecision(
            False,
            "auditor_view_disabled",
            course,
            visibility,
            fields.get("policy_uid", ""),
            getattr(membership, "membership_uid", ""),
            role_in_course,
        )
    return StudentCourseAccessDecision(
        True,
        "membership_active",
        course,
        visibility,
        fields.get("policy_uid", ""),
        getattr(membership, "membership_uid", ""),
        role_in_course,
    )


def can_student_view_concept_card(
    session: Any,
    membership_model: Any,
    policy_model: Any,
    user_context: Any,
    card: Any,
) -> StudentCourseAccessDecision:
    if getattr(card, "status", "") != "approved":
        return StudentCourseAccessDecision(False, "card_not_approved", _text(getattr(card, "course", "")))
    return can_student_view_course(session, membership_model, policy_model, user_context, getattr(card, "course", ""))


def visible_courses_for_user(
    session: Any,
    membership_model: Any,
    policy_model: Any,
    user_context: Any,
    *,
    known_courses: list[str] | None = None,
) -> list[str]:
    role = getattr(user_context, "role", "")
    known_courses = [_text(course) for course in (known_courses or []) if _text(course)]
    if role in {"teacher", "admin"}:
        visible = []
        for course in known_courses:
            decision = can_student_view_course(session, membership_model, policy_model, user_context, course)
            if decision.allowed:
                visible.append(course)
        return sorted(set(visible))
    membership_courses = [
        row.course
        for row in session.query(membership_model.course)
        .filter_by(user_id=getattr(user_context, "id", 0), status="active")
        .all()
        if _text(row.course)
    ]
    public_courses = [
        row.course
        for row in session.query(policy_model.course)
        .filter_by(visibility="public", status="active")
        .all()
        if _text(row.course)
    ]
    candidates = sorted(set(membership_courses + public_courses))
    return [course for course in candidates if can_student_view_course(session, membership_model, policy_model, user_context, course).allowed]


def serialize_student_course_membership(membership: Any) -> dict[str, Any]:
    return {
        "membership_uid": getattr(membership, "membership_uid", ""),
        "user_id": getattr(membership, "user_id", None),
        "course": getattr(membership, "course", ""),
        "role_in_course": getattr(membership, "role_in_course", ""),
        "status": getattr(membership, "status", ""),
        "enrolled_by": getattr(membership, "enrolled_by", None),
        "enrolled_at": getattr(membership, "enrolled_at", ""),
        "revoked_by": getattr(membership, "revoked_by", None),
        "revoked_at": getattr(membership, "revoked_at", ""),
        "created_at": getattr(membership, "created_at", ""),
        "updated_at": getattr(membership, "updated_at", ""),
    }


def serialize_course_student_visibility_policy(policy: Any | None, course: str = "") -> dict[str, Any]:
    policy_course = course
    if policy is not None and not policy_course:
        policy_course = getattr(policy, "course", "")
    fields = _policy_fields(policy, policy_course)
    return {
        "policy_uid": getattr(policy, "policy_uid", "") if policy is not None else "",
        "course": fields.get("course", ""),
        "visibility": fields.get("visibility", DEFAULT_VISIBILITY),
        "allow_auditor_view": bool(fields.get("allow_auditor_view", False)),
        "allow_teacher_preview": bool(fields.get("allow_teacher_preview", True)),
        "allow_cross_course_search": bool(fields.get("allow_cross_course_search", False)),
        "status": fields.get("status", "active"),
        "created_by": getattr(policy, "created_by", None) if policy is not None else None,
        "updated_by": getattr(policy, "updated_by", None) if policy is not None else None,
        "created_at": getattr(policy, "created_at", "") if policy is not None else "",
        "updated_at": getattr(policy, "updated_at", "") if policy is not None else "",
    }


def serialize_access_decision(decision: StudentCourseAccessDecision) -> dict[str, Any]:
    return decision.as_dict()
