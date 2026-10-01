"""Course-scoped review permissions and policy gates for Concept Cards."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


POLICY_STATUSES = {"active", "draft", "disabled"}
PERMISSION_STATUSES = {"active", "disabled", "revoked"}
REVIEWER_ROLES = {"teacher", "admin", "reviewer", "assistant"}
PERMISSION_LEVELS = {"read", "review", "approve", "override", "admin"}
REQUIRED_EVIDENCE_SIDES = {"english_only", "chinese_only", "both", "either"}

DEFAULT_BLOCKING_RISK_LABELS = [
    "no_english_evidence",
    "no_chinese_evidence",
    "missing_chinese_term",
    "no_chinese_candidate_found",
    "bilingual_alignment_not_verified",
    "candidate_not_alignment_verified",
    "input_partial_text",
    "input_mixed_quality",
    "ocr_low_confidence",
    "formula_recognition_unavailable",
    "parse_failed",
    "evidence_from_low_trust_source",
    "course_mismatch",
    "chapter_mismatch",
]

DEFAULT_OVERRIDE_FORBIDDEN_RISK_LABELS = [
    "parse_failed",
    "no_english_evidence",
    "no_chinese_evidence",
    "missing_chinese_term",
]


class CourseReviewPolicyError(ValueError):
    """Raised when course review policy or permission gates block an action."""

    def __init__(self, message: str, reason: str = "course_review_policy_blocked", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


@dataclass(frozen=True)
class PolicyListResult:
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
    if value in ("", None):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _dumps_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def normalize_list(value: Any) -> list[str]:
    if value in ("", None):
        return []
    if isinstance(value, str):
        parsed = _loads_json(value, None)
        if parsed is None:
            return [value] if value else []
        value = parsed
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _bool(value: Any, default: bool = False) -> bool:
    if value in ("", None):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def default_course_review_policy(course: str = "", chapter: str = "") -> dict[str, Any]:
    return {
        "policy_uid": "",
        "course": _text(course),
        "chapter": _text(chapter),
        "require_human_review": True,
        "require_two_step_review": False,
        "require_admin_for_override": True,
        "allow_teacher_override": False,
        "allow_approve_with_unverified_alignment": False,
        "allow_approve_with_partial_text": False,
        "allow_approve_with_missing_chinese_evidence": False,
        "allow_approve_with_missing_english_evidence": False,
        "blocking_risk_labels": list(DEFAULT_BLOCKING_RISK_LABELS),
        "override_allowed_risk_labels": [],
        "override_forbidden_risk_labels": list(DEFAULT_OVERRIDE_FORBIDDEN_RISK_LABELS),
        "required_evidence_sides": "both",
        "min_required_evidence_count": 2,
        "status": "active",
        "created_by": None,
        "updated_by": None,
        "created_at": "",
        "updated_at": "",
        "is_default": True,
    }


def serialize_course_review_policy(policy: Any) -> dict[str, Any]:
    if policy is None:
        return default_course_review_policy()
    if isinstance(policy, dict):
        data = dict(policy)
    else:
        data = {
            "id": getattr(policy, "id", None),
            "policy_uid": getattr(policy, "policy_uid", ""),
            "course": getattr(policy, "course", ""),
            "chapter": getattr(policy, "chapter", ""),
            "require_human_review": bool(getattr(policy, "require_human_review", True)),
            "require_two_step_review": bool(getattr(policy, "require_two_step_review", False)),
            "require_admin_for_override": bool(getattr(policy, "require_admin_for_override", True)),
            "allow_teacher_override": bool(getattr(policy, "allow_teacher_override", False)),
            "allow_approve_with_unverified_alignment": bool(getattr(policy, "allow_approve_with_unverified_alignment", False)),
            "allow_approve_with_partial_text": bool(getattr(policy, "allow_approve_with_partial_text", False)),
            "allow_approve_with_missing_chinese_evidence": bool(getattr(policy, "allow_approve_with_missing_chinese_evidence", False)),
            "allow_approve_with_missing_english_evidence": bool(getattr(policy, "allow_approve_with_missing_english_evidence", False)),
            "blocking_risk_labels": normalize_list(getattr(policy, "blocking_risk_labels", [])),
            "override_allowed_risk_labels": normalize_list(getattr(policy, "override_allowed_risk_labels", [])),
            "override_forbidden_risk_labels": normalize_list(getattr(policy, "override_forbidden_risk_labels", [])),
            "required_evidence_sides": getattr(policy, "required_evidence_sides", "both"),
            "min_required_evidence_count": getattr(policy, "min_required_evidence_count", 2) or 0,
            "status": getattr(policy, "status", ""),
            "created_by": getattr(policy, "created_by", None),
            "updated_by": getattr(policy, "updated_by", None),
            "created_at": getattr(policy, "created_at", ""),
            "updated_at": getattr(policy, "updated_at", ""),
        }
    base = default_course_review_policy(data.get("course", ""), data.get("chapter", ""))
    merged = {**base, **data}
    merged["blocking_risk_labels"] = normalize_list(merged.get("blocking_risk_labels", []))
    merged["override_allowed_risk_labels"] = normalize_list(merged.get("override_allowed_risk_labels", []))
    merged["override_forbidden_risk_labels"] = normalize_list(merged.get("override_forbidden_risk_labels", []))
    if merged.get("required_evidence_sides") not in REQUIRED_EVIDENCE_SIDES:
        merged["required_evidence_sides"] = "both"
    if merged.get("status") not in POLICY_STATUSES:
        merged["status"] = "disabled"
    merged["min_required_evidence_count"] = max(_int(merged.get("min_required_evidence_count"), 2), 0)
    return merged


def serialize_course_review_permission(permission: Any) -> dict[str, Any]:
    if permission is None:
        return {}
    if isinstance(permission, dict):
        data = dict(permission)
    else:
        data = {
            "id": getattr(permission, "id", None),
            "permission_uid": getattr(permission, "permission_uid", ""),
            "course": getattr(permission, "course", ""),
            "chapter": getattr(permission, "chapter", ""),
            "reviewer_id": getattr(permission, "reviewer_id", None),
            "reviewer_role": getattr(permission, "reviewer_role", ""),
            "permission_level": getattr(permission, "permission_level", ""),
            "can_review": bool(getattr(permission, "can_review", False)),
            "can_approve": bool(getattr(permission, "can_approve", False)),
            "can_override_risk": bool(getattr(permission, "can_override_risk", False)),
            "can_assign_reviewer": bool(getattr(permission, "can_assign_reviewer", False)),
            "status": getattr(permission, "status", ""),
            "granted_by": getattr(permission, "granted_by", None),
            "granted_at": getattr(permission, "granted_at", ""),
            "revoked_by": getattr(permission, "revoked_by", None),
            "revoked_at": getattr(permission, "revoked_at", ""),
            "created_at": getattr(permission, "created_at", ""),
            "updated_at": getattr(permission, "updated_at", ""),
        }
    if data.get("permission_level") not in PERMISSION_LEVELS:
        data["permission_level"] = "read"
    if data.get("reviewer_role") not in REVIEWER_ROLES:
        data["reviewer_role"] = _text(data.get("reviewer_role"))
    if data.get("status") not in PERMISSION_STATUSES:
        data["status"] = "disabled"
    return data


def _query_policy(session: Any, policy_model: Any, course: str, chapter: str = "") -> Any | None:
    course_name = _text(course)
    chapter_name = _text(chapter)
    if not course_name:
        return None
    if chapter_name:
        policy = session.query(policy_model).filter_by(course=course_name, chapter=chapter_name, status="active").first()
        if policy is not None:
            return policy
    return session.query(policy_model).filter_by(course=course_name, chapter="", status="active").first()


def get_course_review_policy(session: Any, policy_model: Any, course: str, chapter: str | None = None) -> Any | dict[str, Any]:
    policy = _query_policy(session, policy_model, course, chapter or "")
    return policy if policy is not None else default_course_review_policy(course, chapter or "")


def get_course_review_policy_by_uid(session: Any, policy_model: Any, policy_uid: str) -> Any | None:
    return session.query(policy_model).filter_by(policy_uid=_text(policy_uid)).first()


def _actor_id(actor: Any) -> int | None:
    if actor is None:
        return None
    if isinstance(actor, dict):
        value = actor.get("actor_id") or actor.get("id") or actor.get("reviewer_id")
    else:
        value = getattr(actor, "id", None)
    try:
        return int(value) if value not in ("", None) else None
    except (TypeError, ValueError):
        return None


def create_or_update_course_review_policy(
    session: Any,
    policy_model: Any,
    course: str,
    data: dict[str, Any] | None,
    *,
    actor: Any = None,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, bool]:
    payload = dict(data or {})
    course_name = _text(course or payload.get("course"))
    if not course_name:
        raise CourseReviewPolicyError("course is required.", "course_required")
    chapter = _text(payload.get("chapter", ""))
    policy = session.query(policy_model).filter_by(course=course_name, chapter=chapter).first()
    created = policy is None
    if policy is None:
        policy = policy_model(course=course_name, chapter=chapter)
        session.add(policy)
        if now_fn:
            policy.created_at = now_fn()
    base = default_course_review_policy(course_name, chapter)
    merged = {**base, **payload}
    bool_fields = {
        "require_human_review",
        "require_two_step_review",
        "require_admin_for_override",
        "allow_teacher_override",
        "allow_approve_with_unverified_alignment",
        "allow_approve_with_partial_text",
        "allow_approve_with_missing_chinese_evidence",
        "allow_approve_with_missing_english_evidence",
    }
    for field in bool_fields:
        setattr(policy, field, _bool(merged.get(field), bool(base[field])))
    policy.course = course_name
    policy.chapter = chapter
    policy.blocking_risk_labels = _dumps_json(normalize_list(merged.get("blocking_risk_labels", DEFAULT_BLOCKING_RISK_LABELS)))
    policy.override_allowed_risk_labels = _dumps_json(normalize_list(merged.get("override_allowed_risk_labels", [])))
    policy.override_forbidden_risk_labels = _dumps_json(normalize_list(merged.get("override_forbidden_risk_labels", DEFAULT_OVERRIDE_FORBIDDEN_RISK_LABELS)))
    required = _text(merged.get("required_evidence_sides")) or "both"
    policy.required_evidence_sides = required if required in REQUIRED_EVIDENCE_SIDES else "both"
    policy.min_required_evidence_count = max(_int(merged.get("min_required_evidence_count"), 2), 0)
    status = _text(merged.get("status")) or "active"
    policy.status = status if status in POLICY_STATUSES else "disabled"
    actor_id = _actor_id(actor)
    if actor_id is not None:
        if not getattr(policy, "created_by", None):
            policy.created_by = actor_id
        policy.updated_by = actor_id
    if now_fn:
        policy.updated_at = now_fn()
    if commit:
        session.commit()
    else:
        session.flush()
    return policy, created


def list_course_review_policies(session: Any, policy_model: Any, filters: dict[str, Any] | None = None) -> PolicyListResult:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    per_page = max(1, min(int(filters.get("per_page") or 20), 100))
    query = session.query(policy_model)
    if filters.get("course"):
        query = query.filter(policy_model.course == _text(filters.get("course")))
    if filters.get("status"):
        query = query.filter(policy_model.status == _text(filters.get("status")))
    total = query.count()
    items = query.order_by(policy_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return PolicyListResult(items=items, page=page, per_page=per_page, total=total)


def _apply_permission_level_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    level = _text(payload.get("permission_level")) or "read"
    if level not in PERMISSION_LEVELS:
        raise CourseReviewPolicyError(f"permission_level must be one of {sorted(PERMISSION_LEVELS)}.", "invalid_permission_level")
    defaults = {
        "read": {"can_review": False, "can_approve": False, "can_override_risk": False, "can_assign_reviewer": False},
        "review": {"can_review": True, "can_approve": False, "can_override_risk": False, "can_assign_reviewer": False},
        "approve": {"can_review": True, "can_approve": True, "can_override_risk": False, "can_assign_reviewer": False},
        "override": {"can_review": True, "can_approve": True, "can_override_risk": True, "can_assign_reviewer": False},
        "admin": {"can_review": True, "can_approve": True, "can_override_risk": True, "can_assign_reviewer": True},
    }[level]
    merged = {**payload, "permission_level": level}
    for field, default in defaults.items():
        merged[field] = _bool(payload.get(field), default)
    return merged


def grant_course_review_permission(
    session: Any,
    permission_model: Any,
    course: str,
    reviewer_id: Any,
    data: dict[str, Any] | None,
    *,
    actor: Any = None,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, bool]:
    payload = _apply_permission_level_defaults(dict(data or {}))
    course_name = _text(course or payload.get("course"))
    if not course_name:
        raise CourseReviewPolicyError("course is required.", "course_required")
    reviewer_value = reviewer_id if reviewer_id not in ("", None) else payload.get("reviewer_id")
    try:
        reviewer_int = int(reviewer_value)
    except (TypeError, ValueError):
        raise CourseReviewPolicyError("reviewer_id is required.", "reviewer_id_required")
    chapter = _text(payload.get("chapter", ""))
    permission = session.query(permission_model).filter_by(
        course=course_name,
        chapter=chapter,
        reviewer_id=reviewer_int,
    ).first()
    created = permission is None
    if permission is None:
        permission = permission_model(course=course_name, chapter=chapter, reviewer_id=reviewer_int)
        session.add(permission)
        if now_fn:
            permission.created_at = now_fn()
    permission.reviewer_role = _text(payload.get("reviewer_role")) or "teacher"
    permission.permission_level = payload["permission_level"]
    permission.can_review = bool(payload.get("can_review"))
    permission.can_approve = bool(payload.get("can_approve"))
    permission.can_override_risk = bool(payload.get("can_override_risk"))
    permission.can_assign_reviewer = bool(payload.get("can_assign_reviewer"))
    permission.status = _text(payload.get("status")) or "active"
    if permission.status not in PERMISSION_STATUSES:
        permission.status = "disabled"
    actor_id = _actor_id(actor)
    if actor_id is not None:
        permission.granted_by = actor_id
    if now_fn:
        permission.granted_at = permission.granted_at or now_fn()
        permission.updated_at = now_fn()
    if commit:
        session.commit()
    else:
        session.flush()
    return permission, created


def revoke_course_review_permission(
    session: Any,
    permission_model: Any,
    permission_uid: str,
    *,
    actor: Any = None,
    now_fn=None,
    commit: bool = True,
) -> Any:
    permission = session.query(permission_model).filter_by(permission_uid=_text(permission_uid)).first()
    if permission is None:
        raise CourseReviewPolicyError("CourseReviewPermission not found.", "permission_not_found")
    permission.status = "revoked"
    actor_id = _actor_id(actor)
    if actor_id is not None:
        permission.revoked_by = actor_id
    if now_fn:
        permission.revoked_at = now_fn()
        permission.updated_at = permission.revoked_at
    if commit:
        session.commit()
    else:
        session.flush()
    return permission


def list_course_review_permissions(session: Any, permission_model: Any, filters: dict[str, Any] | None = None) -> PolicyListResult:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    per_page = max(1, min(int(filters.get("per_page") or 20), 100))
    query = session.query(permission_model)
    if filters.get("course"):
        query = query.filter(permission_model.course == _text(filters.get("course")))
    if filters.get("reviewer_id"):
        query = query.filter(permission_model.reviewer_id == int(filters.get("reviewer_id")))
    if filters.get("reviewer_role"):
        query = query.filter(permission_model.reviewer_role == _text(filters.get("reviewer_role")))
    if filters.get("status"):
        query = query.filter(permission_model.status == _text(filters.get("status")))
    total = query.count()
    items = query.order_by(permission_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return PolicyListResult(items=items, page=page, per_page=per_page, total=total)


def get_reviewer_permissions(
    session: Any,
    permission_model: Any,
    *,
    reviewer_id: Any = None,
    reviewer_role: str | None = None,
    course: str | None = None,
    chapter: str | None = None,
) -> list[Any]:
    query = session.query(permission_model).filter(permission_model.status == "active")
    if reviewer_id not in ("", None):
        query = query.filter(permission_model.reviewer_id == int(reviewer_id))
    if reviewer_role:
        query = query.filter(permission_model.reviewer_role == _text(reviewer_role))
    if course:
        query = query.filter(permission_model.course == _text(course))
    if chapter:
        query = query.filter((permission_model.chapter == _text(chapter)) | (permission_model.chapter == ""))
    return query.all()


def _reviewer(reviewer_context: Any) -> dict[str, Any]:
    if isinstance(reviewer_context, dict):
        return {
            "reviewer_id": reviewer_context.get("reviewer_id") or reviewer_context.get("id") or reviewer_context.get("actor_id"),
            "reviewer_role": _text(reviewer_context.get("reviewer_role") or reviewer_context.get("role") or reviewer_context.get("actor_role")),
        }
    return {"reviewer_id": getattr(reviewer_context, "id", None), "reviewer_role": _text(getattr(reviewer_context, "role", ""))}


def _matching_permission(session: Any, permission_model: Any, card: Any, reviewer_context: Any) -> dict[str, Any] | None:
    reviewer = _reviewer(reviewer_context)
    role = reviewer.get("reviewer_role", "")
    if role == "admin":
        return {
            "permission_uid": "admin-default",
            "course": getattr(card, "course", ""),
            "chapter": getattr(card, "chapter", ""),
            "reviewer_id": reviewer.get("reviewer_id"),
            "reviewer_role": "admin",
            "permission_level": "admin",
            "can_review": True,
            "can_approve": True,
            "can_override_risk": True,
            "can_assign_reviewer": True,
            "status": "active",
            "is_admin_default": True,
        }
    permissions = get_reviewer_permissions(
        session,
        permission_model,
        reviewer_id=reviewer.get("reviewer_id"),
        course=getattr(card, "course", ""),
        chapter=getattr(card, "chapter", ""),
    )
    for permission in permissions:
        data = serialize_course_review_permission(permission)
        if data.get("chapter") and data.get("chapter") != getattr(card, "chapter", ""):
            continue
        return data
    return None


def can_reviewer_review_card(session: Any, permission_model: Any, card: Any, reviewer_context: Any) -> tuple[bool, dict[str, Any] | None, str]:
    reviewer = _reviewer(reviewer_context)
    if reviewer.get("reviewer_role") == "student":
        return False, None, "student_cannot_review"
    permission = _matching_permission(session, permission_model, card, reviewer_context)
    if not permission:
        return False, None, "course_review_permission_missing"
    if permission.get("status") != "active" or not permission.get("can_review"):
        return False, permission, "course_review_permission_denied"
    return True, permission, ""


def can_reviewer_approve_card(session: Any, permission_model: Any, card: Any, reviewer_context: Any) -> tuple[bool, dict[str, Any] | None, str]:
    ok, permission, reason = can_reviewer_review_card(session, permission_model, card, reviewer_context)
    if not ok:
        return False, permission, reason
    if not permission.get("can_approve"):
        return False, permission, "course_approve_permission_denied"
    return True, permission, ""


def can_reviewer_override_risk(
    session: Any,
    permission_model: Any,
    card: Any,
    reviewer_context: Any,
    risk_labels: list[str] | None = None,
) -> tuple[bool, dict[str, Any] | None, str]:
    del risk_labels
    ok, permission, reason = can_reviewer_approve_card(session, permission_model, card, reviewer_context)
    if not ok:
        return False, permission, reason
    if not permission.get("can_override_risk"):
        return False, permission, "course_override_permission_denied"
    return True, permission, ""


def _evidence_count(value: Any) -> int:
    parsed = _loads_json(value, [])
    if isinstance(parsed, list):
        return len([item for item in parsed if item])
    if isinstance(parsed, dict):
        return 1 if parsed else 0
    return 1 if _text(parsed) else 0


def _evidence_summary(card: Any) -> dict[str, Any]:
    english = _evidence_count(getattr(card, "english_evidence", "[]"))
    chinese = _evidence_count(getattr(card, "chinese_evidence", "[]"))
    return {"english_count": english, "chinese_count": chinese, "total": english + chinese}


def _policy_blocked_by_evidence(policy: dict[str, Any], evidence: dict[str, int]) -> list[str]:
    blocked: list[str] = []
    required = policy.get("required_evidence_sides", "both")
    if required in {"both", "english_only"} and evidence["english_count"] <= 0:
        blocked.append("missing_english_evidence")
    if required in {"both", "chinese_only"} and evidence["chinese_count"] <= 0:
        blocked.append("missing_chinese_evidence")
    if required == "either" and evidence["total"] <= 0:
        blocked.append("missing_evidence")
    if evidence["total"] < int(policy.get("min_required_evidence_count") or 0):
        blocked.append("min_required_evidence_count_not_met")
    if evidence["english_count"] <= 0 and not policy.get("allow_approve_with_missing_english_evidence"):
        blocked.append("missing_english_evidence")
    if evidence["chinese_count"] <= 0 and not policy.get("allow_approve_with_missing_chinese_evidence"):
        blocked.append("missing_chinese_evidence")
    return sorted(set(blocked))


def _policy_blocked_by_risks(policy: dict[str, Any], labels: set[str]) -> list[str]:
    blocked = set(labels & set(policy.get("blocking_risk_labels", [])))
    if "bilingual_alignment_not_verified" in labels and not policy.get("allow_approve_with_unverified_alignment"):
        blocked.add("bilingual_alignment_not_verified")
    partial_risks = {"input_partial_text", "input_mixed_quality", "ocr_low_confidence", "formula_recognition_unavailable"}
    if labels & partial_risks and not policy.get("allow_approve_with_partial_text"):
        blocked.update(labels & partial_risks)
    return sorted(blocked)


def evaluate_card_against_review_policy(
    session: Any,
    policy_model: Any,
    permission_model: Any,
    card: Any,
    action: str,
    reviewer_context: Any,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = data or {}
    action = _text(action)
    policy_obj = get_course_review_policy(session, policy_model, getattr(card, "course", ""), getattr(card, "chapter", ""))
    policy = serialize_course_review_policy(policy_obj)
    reviewer = _reviewer(reviewer_context)

    if action == "approve":
        permission_ok, permission, permission_reason = can_reviewer_approve_card(session, permission_model, card, reviewer_context)
    elif action == "assign_reviewer":
        ok, permission, permission_reason = can_reviewer_review_card(session, permission_model, card, reviewer_context)
        permission_ok = ok and bool(permission and permission.get("can_assign_reviewer"))
        if ok and not permission_ok:
            permission_reason = "course_assign_permission_denied"
    else:
        permission_ok, permission, permission_reason = can_reviewer_review_card(session, permission_model, card, reviewer_context)
    base = {
        "allowed": False,
        "policy": policy,
        "policy_uid": policy.get("policy_uid", ""),
        "permission": permission or {},
        "permission_uid": (permission or {}).get("permission_uid", ""),
        "reviewer_role": reviewer.get("reviewer_role", ""),
        "blocking_reasons": [],
        "nonblocking_risk_labels": [],
        "requires_second_review": False,
        "reason": "",
    }
    if not permission_ok:
        return {**base, "reason": permission_reason or "course_review_permission_denied", "blocking_reasons": [permission_reason or "course_review_permission_denied"]}
    if policy.get("status") != "active":
        return {**base, "reason": "course_review_policy_disabled", "blocking_reasons": ["course_review_policy_disabled"]}
    if action != "approve":
        return {**base, "allowed": True, "reason": "allowed"}

    evidence = _evidence_summary(card)
    labels = set(normalize_list(getattr(card, "risk_labels", "[]")))
    labels.update(reason for reason in _policy_blocked_by_evidence(policy, evidence) if reason.startswith("missing_"))
    evidence_blocks = _policy_blocked_by_evidence(policy, evidence)
    risk_blocks = _policy_blocked_by_risks(policy, labels)
    blocking = sorted(set(evidence_blocks + risk_blocks))
    override_requested = bool(data.get("allow_risk_override"))
    nonblocking = sorted(set(labels) - set(blocking))
    if not blocking:
        return {
            **base,
            "allowed": True,
            "reason": "allowed",
            "nonblocking_risk_labels": nonblocking,
            "requires_second_review": bool(policy.get("require_two_step_review") and reviewer.get("reviewer_role") != "admin"),
        }
    if not override_requested:
        return {**base, "reason": "course_review_policy_blocked", "blocking_reasons": blocking, "nonblocking_risk_labels": nonblocking}

    forbidden = sorted(set(blocking) & set(policy.get("override_forbidden_risk_labels", [])))
    if forbidden:
        return {**base, "reason": "course_review_risk_override_forbidden", "blocking_reasons": forbidden, "nonblocking_risk_labels": nonblocking}
    allowed_override = set(policy.get("override_allowed_risk_labels", []))
    if allowed_override and not set(blocking).issubset(allowed_override):
        return {
            **base,
            "reason": "course_review_risk_override_not_allowed",
            "blocking_reasons": sorted(set(blocking) - allowed_override),
            "nonblocking_risk_labels": nonblocking,
        }
    if policy.get("require_admin_for_override") and reviewer.get("reviewer_role") != "admin":
        return {**base, "reason": "course_review_admin_required_for_override", "blocking_reasons": blocking, "nonblocking_risk_labels": nonblocking}
    if reviewer.get("reviewer_role") != "admin" and not policy.get("allow_teacher_override"):
        return {**base, "reason": "course_review_teacher_override_not_allowed", "blocking_reasons": blocking, "nonblocking_risk_labels": nonblocking}
    override_ok, override_permission, override_reason = can_reviewer_override_risk(session, permission_model, card, reviewer_context, blocking)
    if not override_ok:
        return {
            **base,
            "permission": override_permission or permission or {},
            "permission_uid": (override_permission or permission or {}).get("permission_uid", ""),
            "reason": override_reason,
            "blocking_reasons": blocking,
            "nonblocking_risk_labels": nonblocking,
        }
    return {
        **base,
        "allowed": True,
        "reason": "allowed_with_risk_override",
        "blocking_reasons": blocking,
        "nonblocking_risk_labels": sorted(labels),
        "requires_second_review": bool(policy.get("require_two_step_review") and reviewer.get("reviewer_role") != "admin"),
    }
