"""Governed Reviewer Console workflow for Concept Alignment Cards."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_

from services import audit_records
from services import concept_alignment_cards
from services import concept_card_publication
from services import course_review_policy
from services import parse_quality_risk


REVIEW_ACTIONS = {
    "accept_recommendation",
    "select_alternative_candidate",
    "defer_review",
    "generate_draft",
    "approve",
    "reject",
    "request_revision",
    "mark_needs_more_evidence",
    "mark_candidate_incorrect",
    "mark_translation_ambiguous",
    "assign_reviewer",
    "unassign_reviewer",
    "add_review_note",
    "reopen",
    "deprecate",
}

REVIEW_DECISIONS = {
    "accepted",
    "alternative_selected",
    "deferred",
    "draft_generated",
    "approved",
    "rejected",
    "needs_revision",
    "insufficient_evidence",
    "candidate_incorrect",
    "ambiguous",
    "needs_review",
    "deprecated",
    "ready_for_admin_review",
    "pending_second_review",
}

REASON_CODES = {
    "evidence_sufficient",
    "evidence_insufficient",
    "chinese_term_wrong",
    "english_term_unclear",
    "course_context_mismatch",
    "chapter_context_mismatch",
    "candidate_ambiguous",
    "parse_quality_risk",
    "low_trust_evidence",
    "alignment_not_verified",
    "teacher_verified",
    "duplicate_card",
    "outdated_card",
    "other",
}

ASSIGNMENT_STATUSES = {"active", "completed", "canceled"}

BLOCKING_APPROVAL_RISK_LABELS = {
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
}
FATAL_HUMAN_APPROVAL_RISK_LABELS = {
    "evidence_provenance_incomplete",
    "provenance_incomplete",
    "source_governance_failed",
    "UPSTREAM_ENGLISH_EXTRACTION_MISSING",
    "UPSTREAM_ENGLISH_BINDING_AMBIGUOUS",
    "UPSTREAM_CROSS_LANGUAGE_RETRIEVAL_MISS",
    "UPSTREAM_CHINESE_TERM_IDENTIFICATION_MISSING",
    "no_english_evidence",
    "no_chinese_evidence",
    "no_chinese_candidate_found",
}

ACTION_TO_EVENT = {
    "accept_recommendation": "teacher_alignment_recommendation_accepted",
    "select_alternative_candidate": "teacher_alignment_alternative_selected",
    "defer_review": "teacher_alignment_review_deferred",
    "generate_draft": "teacher_alignment_draft_generated",
    "approve": "concept_card_approved",
    "reject": "concept_card_rejected",
    "request_revision": "concept_card_revision_requested",
    "mark_needs_more_evidence": "concept_card_more_evidence_requested",
    "mark_candidate_incorrect": "concept_card_revision_requested",
    "mark_translation_ambiguous": "concept_card_revision_requested",
    "reopen": "concept_card_reopened",
    "deprecate": "concept_card_deprecated",
    "assign_reviewer": "concept_card_reviewer_assigned",
    "unassign_reviewer": "concept_card_reviewer_assigned",
    "add_review_note": "concept_card_review_record_created",
}


class ConceptCardReviewError(ValueError):
    """Raised when review workflow validation fails."""


class ConceptCardSourceUnavailableError(ConceptCardReviewError):
    """Raised when source withdrawal invalidates a review action."""

    reason = "concept_card_source_unavailable"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class ReviewQueueResult:
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
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def normalize_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        parsed = _loads_json(value, None)
        if parsed is None:
            return [value] if value else []
        value = parsed
    if not isinstance(value, list):
        return []
    return value


def merge_labels(*groups: Any) -> list[str]:
    merged: list[str] = []
    for labels in groups:
        merged = parse_quality_risk.merge_risk_labels(merged, normalize_list(labels))
    return merged


def _has_evidence(value: Any) -> bool:
    if value in (None, ""):
        return False
    parsed = _loads_json(value, None)
    if isinstance(parsed, list):
        return any(bool(item) for item in parsed)
    if isinstance(parsed, dict):
        return bool(parsed)
    return bool(str(value).strip())


def _count_evidence(value: Any) -> int:
    if value in (None, ""):
        return 0
    parsed = _loads_json(value, None)
    if isinstance(parsed, list):
        return len([item for item in parsed if item])
    if isinstance(parsed, dict):
        return 1 if parsed else 0
    return 1 if str(value).strip() else 0


def _reviewer_context(reviewer_context: Any) -> dict[str, Any]:
    if reviewer_context is None:
        return {"reviewer_id": None, "reviewer_role": "", "reviewer_name": ""}
    if isinstance(reviewer_context, dict):
        return {
            "reviewer_id": reviewer_context.get("reviewer_id") or reviewer_context.get("id") or reviewer_context.get("actor_id"),
            "reviewer_role": _text(reviewer_context.get("reviewer_role") or reviewer_context.get("role") or reviewer_context.get("actor_role")),
            "reviewer_name": _text(
                reviewer_context.get("reviewer_name")
                or reviewer_context.get("name")
                or reviewer_context.get("username")
                or reviewer_context.get("actor_name")
            ),
        }
    return {
        "reviewer_id": getattr(reviewer_context, "id", None),
        "reviewer_role": _text(getattr(reviewer_context, "role", "")),
        "reviewer_name": _text(
            getattr(reviewer_context, "display_name", "")
            or getattr(reviewer_context, "username", "")
            or getattr(reviewer_context, "email", "")
        ),
    }


def _require_authorized_reviewer_role(reviewer_context: Any) -> dict[str, Any]:
    reviewer = _reviewer_context(reviewer_context)
    if reviewer["reviewer_role"] not in {"teacher", "reviewer", "admin"}:
        raise ConceptCardReviewError("an authorized reviewer role is required.")
    return reviewer


def _validate_reason(action: str, data: dict[str, Any]) -> str:
    reason = _text(data.get("reason_code"))
    if reason and reason not in REASON_CODES:
        raise ConceptCardReviewError(f"reason_code must be one of {sorted(REASON_CODES)}.")
    if action in {"reject", "mark_needs_more_evidence", "reopen", "deprecate"} and not reason:
        raise ConceptCardReviewError("reason_code is required for this review action.")
    if action == "request_revision" and not (reason or normalize_list(data.get("required_changes"))):
        raise ConceptCardReviewError("required_changes or reason_code is required for request_revision.")
    return reason


def _decision_for(action: str) -> str:
    return {
        "accept_recommendation": "accepted",
        "select_alternative_candidate": "alternative_selected",
        "defer_review": "deferred",
        "generate_draft": "draft_generated",
        "approve": "approved",
        "reject": "rejected",
        "request_revision": "needs_revision",
        "mark_needs_more_evidence": "insufficient_evidence",
        "mark_candidate_incorrect": "candidate_incorrect",
        "mark_translation_ambiguous": "ambiguous",
        "assign_reviewer": "needs_review",
        "unassign_reviewer": "needs_review",
        "add_review_note": "needs_review",
        "reopen": "needs_review",
        "deprecate": "deprecated",
    }.get(action, "needs_review")


def _remaining_labels(card: Any, resolved: list[str]) -> list[str]:
    resolved_set = set(_text(item) for item in resolved)
    return [label for label in normalize_list(getattr(card, "risk_labels", "[]")) if _text(label) not in resolved_set]


def _blocking_risks(card: Any, data: dict[str, Any] | None = None) -> list[str]:
    labels = set(normalize_list(getattr(card, "risk_labels", "[]")))
    nonblocking = set(normalize_list((data or {}).get("_policy_nonblocking_risk_labels", [])))
    return sorted((labels & BLOCKING_APPROVAL_RISK_LABELS) - nonblocking)


def _assessment(data: dict[str, Any], field: str, fallback: dict[str, Any]) -> dict[str, Any]:
    value = data.get(field)
    return value if isinstance(value, dict) else fallback


def _serialize_json_list(value: Any) -> str:
    return _dumps_json(normalize_list(value))


def _event_for_action(action: str) -> str:
    return ACTION_TO_EVENT.get(action, "concept_card_review_record_created")


def validate_review_action(card: Any, action: str, data: dict[str, Any], reviewer_context: Any | None = None) -> dict[str, Any]:
    action = _text(action)
    if action not in REVIEW_ACTIONS:
        raise ConceptCardReviewError(f"action must be one of {sorted(REVIEW_ACTIONS)}.")
    reviewer = _require_authorized_reviewer_role(reviewer_context)
    reason = _validate_reason(action, data)
    comment = _text(data.get("review_comment"))
    if action in {"reject", "request_revision", "mark_needs_more_evidence"} and not (comment or normalize_list(data.get("required_changes"))):
        raise ConceptCardReviewError("review_comment or required_changes is required for this review action.")
    if action in {"accept_recommendation", "select_alternative_candidate"}:
        labels = set(normalize_list(getattr(card, "risk_labels", "[]")))
        if labels & FATAL_HUMAN_APPROVAL_RISK_LABELS:
            raise ConceptCardReviewError(
                "human review cannot bypass fatal evidence or provenance state."
            )
        if not (
            _has_evidence(getattr(card, "english_evidence", ""))
            and _has_evidence(getattr(card, "chinese_evidence", ""))
        ):
            raise ConceptCardReviewError(
                "human approval requires complete bilingual evidence."
            )
        if not comment:
            raise ConceptCardReviewError("review_comment is required.")
        if action == "select_alternative_candidate" and not _text(
            data.get("selected_candidate_uid")
        ):
            raise ConceptCardReviewError("selected_candidate_uid is required.")
    if action == "approve":
        fatal = set(normalize_list(getattr(card, "risk_labels", "[]"))) & (
            FATAL_HUMAN_APPROVAL_RISK_LABELS
        )
        if fatal:
            raise ConceptCardReviewError(
                "human review cannot bypass fatal evidence or provenance state."
            )
        if getattr(card, "status", "") == "deprecated":
            raise ConceptCardReviewError("deprecated ConceptAlignmentCard cannot be approved.")
        if not _text(getattr(card, "english_term", "")):
            raise ConceptCardReviewError("english_term is required before approval.")
        if not _text(getattr(card, "chinese_term", "")):
            raise ConceptCardReviewError("chinese_term is required before approval.")
        if not _text(getattr(card, "course", "")):
            raise ConceptCardReviewError("course is required before approval.")
        if not (_has_evidence(getattr(card, "english_evidence", "")) or _has_evidence(getattr(card, "chinese_evidence", ""))):
            raise ConceptCardReviewError("approval requires English or Chinese evidence.")
        if not (reason or comment):
            raise ConceptCardReviewError("reason_code or review_comment is required for approval.")
        blocking = _blocking_risks(card, data)
        if blocking and not data.get("allow_risk_override"):
            raise ConceptCardReviewError(f"approval blocked by unresolved risk labels: {', '.join(blocking)}.")
        if data.get("allow_risk_override") and not _text(data.get("override_reason")):
            raise ConceptCardReviewError("override_reason is required when allow_risk_override is true.")
    if action == "reopen" and getattr(card, "status", "") not in {"approved", "rejected", "deprecated"}:
        raise ConceptCardReviewError("only approved, rejected, or deprecated cards can be reopened.")
    if action == "assign_reviewer" and not _text(data.get("assigned_to")):
        raise ConceptCardReviewError("assigned_to is required.")
    return reviewer


def create_review_record(
    session: Any,
    review_model: Any,
    card: Any,
    action: str,
    reviewer_context: Any,
    data: dict[str, Any] | None = None,
    *,
    previous_status: str | None = None,
    new_status: str | None = None,
    now_fn=None,
    commit: bool = True,
) -> Any:
    data = data or {}
    reviewer = _reviewer_context(reviewer_context)
    resolved = normalize_list(data.get("resolved_risk_labels"))
    remaining = _remaining_labels(card, resolved)
    blocking = _blocking_risks(card, data)
    record = review_model(
        card_uid=getattr(card, "card_uid", ""),
        reviewer_id=reviewer.get("reviewer_id"),
        reviewer_role=reviewer.get("reviewer_role", ""),
        reviewer_name=reviewer.get("reviewer_name", ""),
        action=action,
        previous_status=previous_status if previous_status is not None else getattr(card, "status", ""),
        new_status=new_status if new_status is not None else getattr(card, "status", ""),
        decision=data.get("decision") or _decision_for(action),
        reason_code=_text(data.get("reason_code")),
        review_comment=_text(data.get("review_comment")),
        evidence_assessment=_dumps_json(_assessment(data, "evidence_assessment", {
            "english_evidence_present": _has_evidence(getattr(card, "english_evidence", "")),
            "chinese_evidence_present": _has_evidence(getattr(card, "chinese_evidence", "")),
        })),
        term_assessment=_dumps_json(_assessment(data, "term_assessment", {
            "english_term_present": bool(_text(getattr(card, "english_term", ""))),
            "chinese_term_present": bool(_text(getattr(card, "chinese_term", ""))),
        })),
        risk_assessment=_dumps_json(_assessment(data, "risk_assessment", {
            "blocking_risk_labels": blocking,
            "risk_override_used": bool(data.get("allow_risk_override")),
            "override_reason": _text(data.get("override_reason")),
        })),
        required_changes=_serialize_json_list(data.get("required_changes")),
        resolved_risk_labels=_serialize_json_list(resolved),
        remaining_risk_labels=_serialize_json_list(remaining),
        verification_run_uid=_text(data.get("verification_run_uid")),
        request_id=_text(data.get("request_id")),
        created_at=now_fn() if now_fn else "",
    )
    session.add(record)
    if commit:
        session.commit()
    else:
        session.flush()
    return record


def _record_review_audit(
    session: Any,
    audit_model: Any | None,
    event_type: str,
    card: Any,
    review_record: Any,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    *,
    data: dict[str, Any],
    reviewer_context: Any,
    audit_context: dict[str, Any] | None,
    now_fn=None,
    commit: bool = False,
) -> Any | None:
    if audit_model is None:
        return None
    output = {
        "review_uid": getattr(review_record, "review_uid", ""),
        "card_uid": getattr(card, "card_uid", ""),
        "action": getattr(review_record, "action", ""),
        "previous_status": getattr(review_record, "previous_status", ""),
        "new_status": getattr(review_record, "new_status", ""),
        "reviewer_role": getattr(review_record, "reviewer_role", ""),
        "reason_code": getattr(review_record, "reason_code", ""),
        "risk_override_used": bool(data.get("allow_risk_override")),
        "resolved_risk_labels": normalize_list(getattr(review_record, "resolved_risk_labels", "[]")),
        "remaining_risk_labels": normalize_list(getattr(review_record, "remaining_risk_labels", "[]")),
    }
    return audit_records.create_audit_record(
        session,
        audit_model,
        {
            "event_type": event_type,
            "target_type": audit_records.CONCEPT_CARD_TARGET_TYPE,
            "target_uid": getattr(card, "card_uid", ""),
            "source": "api",
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "input_payload": {
                "action": data.get("action", getattr(review_record, "action", "")),
                "reason_code": data.get("reason_code", ""),
                "risk_override_used": bool(data.get("allow_risk_override")),
            },
            "output_payload": output,
            "changed_fields": audit_records.changed_fields(before_snapshot, after_snapshot),
            "result": "success",
        },
        audit_context=audit_context,
        now_fn=now_fn,
        commit=commit,
    )


def _record_review_block_audit(
    session: Any,
    audit_model: Any | None,
    card: Any,
    action: str,
    reviewer_context: Any,
    gate: dict[str, Any],
    *,
    data: dict[str, Any],
    audit_context: dict[str, Any] | None,
    now_fn=None,
    commit: bool = False,
) -> Any | None:
    if audit_model is None:
        return None
    reason = gate.get("reason") or "course_review_policy_blocked"
    if "permission" in reason:
        event_type = "concept_card_review_blocked_by_permission"
    elif "override" in reason:
        event_type = "concept_card_risk_override_blocked_by_policy"
    else:
        event_type = "concept_card_review_blocked_by_course_policy"
    reviewer = _reviewer_context(reviewer_context)
    snapshot = audit_records.concept_card_snapshot(card)
    return audit_records.create_audit_record(
        session,
        audit_model,
        {
            "event_type": event_type,
            "target_type": audit_records.CONCEPT_CARD_TARGET_TYPE,
            "target_uid": getattr(card, "card_uid", ""),
            "source": "api",
            "before_snapshot": snapshot,
            "after_snapshot": snapshot,
            "input_payload": {
                "action": action,
                "reason_code": data.get("reason_code", ""),
                "risk_override_requested": bool(data.get("allow_risk_override")),
            },
            "output_payload": {
                "card_uid": getattr(card, "card_uid", ""),
                "course": getattr(card, "course", ""),
                "policy_uid": gate.get("policy_uid", ""),
                "permission_uid": gate.get("permission_uid", ""),
                "reviewer_id": reviewer.get("reviewer_id"),
                "reviewer_role": reviewer.get("reviewer_role", ""),
                "action": action,
                "blocked_reason": reason,
                "risk_labels": normalize_list(getattr(card, "risk_labels", "[]")),
                "blocking_reasons": gate.get("blocking_reasons", []),
            },
            "changed_fields": [],
            "result": "error",
            "error_code": reason,
            "error_message": reason,
        },
        audit_context=audit_context,
        now_fn=now_fn,
        commit=commit,
    )


def _persist_review_action(
    session: Any,
    card: Any,
    review_model: Any,
    action: str,
    reviewer_context: Any,
    data: dict[str, Any],
    *,
    audit_model: Any | None = None,
    audit_context: dict[str, Any] | None = None,
    policy_model: Any | None = None,
    permission_model: Any | None = None,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
    require_concurrency_token: bool = False,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, Any]:
    before = audit_records.concept_card_snapshot(card)
    previous_status = getattr(card, "status", "")
    now = now_fn() if now_fn else ""
    if require_concurrency_token:
        concept_alignment_cards.require_current_version(card, data)
    if policy_model is not None and permission_model is not None:
        gate = course_review_policy.evaluate_card_against_review_policy(
            session,
            policy_model,
            permission_model,
            card,
            action,
            reviewer_context,
            data,
        )
        data["_course_review_policy_gate"] = gate
        data["_policy_nonblocking_risk_labels"] = gate.get("nonblocking_risk_labels", [])
        data["_requires_second_review"] = bool(gate.get("requires_second_review", False))
        if not gate.get("allowed"):
            _record_review_block_audit(
                session,
                audit_model,
                card,
                action,
                reviewer_context,
                gate,
                data=data,
                audit_context=audit_context,
                now_fn=now_fn,
                commit=commit,
            )
            raise ConceptCardReviewError(f"review blocked by course policy: {gate.get('reason')}")
    reviewer = validate_review_action(card, action, data, reviewer_context)
    if action == "approve" and source_model is not None:
        try:
            concept_card_publication.assert_sources_available(
                session,
                card,
                source_model=source_model,
                chunk_model=chunk_model,
            )
        except concept_card_publication.ConceptCardPublicationError as exc:
            raise ConceptCardSourceUnavailableError(str(exc), getattr(exc, "details", {})) from exc

    if action in {"accept_recommendation", "select_alternative_candidate"}:
        card.status = "needs_review"
        card.reviewed_by = reviewer.get("reviewer_id")
        card.reviewed_at = now
    elif action == "defer_review":
        card.status = "needs_review"
    elif action == "generate_draft":
        card.status = "draft"
    elif action == "approve":
        if data.get("_requires_second_review") and reviewer.get("reviewer_role") != "admin":
            card.status = "needs_review"
            data["decision"] = "ready_for_admin_review"
        else:
            card.status = "approved"
            card.reviewed_by = reviewer.get("reviewer_id")
            card.reviewed_at = now
    elif action == "reject":
        card.status = "rejected"
        card.reviewed_by = reviewer.get("reviewer_id")
        card.reviewed_at = now
    elif action == "request_revision":
        card.status = "draft" if previous_status == "draft" else "needs_review"
    elif action == "mark_needs_more_evidence":
        card.status = "needs_review"
        card.risk_labels = merge_labels(getattr(card, "risk_labels", "[]"), ["insufficient_evidence"])
    elif action == "mark_candidate_incorrect":
        card.status = "needs_review"
        card.risk_labels = merge_labels(getattr(card, "risk_labels", "[]"), ["candidate_incorrect"])
    elif action == "mark_translation_ambiguous":
        card.status = "needs_review"
        card.risk_labels = merge_labels(getattr(card, "risk_labels", "[]"), ["candidate_ambiguous"])
    elif action == "reopen":
        card.status = "needs_review"
    elif action == "deprecate":
        card.status = "deprecated"
    elif action in {"add_review_note", "assign_reviewer", "unassign_reviewer"}:
        pass
    if action in {"accept_recommendation", "select_alternative_candidate", "defer_review", "generate_draft", "approve", "reject", "request_revision", "mark_needs_more_evidence", "mark_candidate_incorrect", "mark_translation_ambiguous", "reopen", "deprecate"}:
        card.version = int(getattr(card, "version", 1) or 1) + 1
    if now:
        card.updated_at = now
    session.flush()

    after = audit_records.concept_card_snapshot(card)
    review_data = {
        **data,
        "request_id": _text(data.get("request_id"))
        or (audit_context or {}).get("request_id", ""),
    }
    review_record = create_review_record(
        session,
        review_model,
        card,
        action,
        reviewer,
        review_data,
        previous_status=previous_status,
        new_status=getattr(card, "status", ""),
        now_fn=now_fn,
        commit=False,
    )
    _record_review_audit(
        session,
        audit_model,
        "concept_card_review_record_created",
        card,
        review_record,
        before,
        after,
        data=review_data,
        reviewer_context=reviewer,
        audit_context=audit_context,
        now_fn=now_fn,
        commit=False,
    )
    event_type = _event_for_action(action)
    if event_type != "concept_card_review_record_created":
        _record_review_audit(
            session,
            audit_model,
            event_type,
            card,
            review_record,
            before,
            after,
            data=review_data,
            reviewer_context=reviewer,
            audit_context=audit_context,
            now_fn=now_fn,
            commit=False,
        )
    if action == "approve" and data.get("allow_risk_override"):
        _record_review_audit(
            session,
            audit_model,
            "concept_card_risk_override_used",
            card,
            review_record,
            before,
            after,
            data=review_data,
            reviewer_context=reviewer,
            audit_context=audit_context,
            now_fn=now_fn,
            commit=False,
        )
    if commit:
        session.commit()
    else:
        session.flush()
    return card, review_record


def approve_concept_card(session: Any, card_model: Any, review_model: Any, card_uid: str, reviewer_context: Any, data: dict[str, Any] | None = None, **kwargs) -> tuple[Any, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    return _persist_review_action(session, card, review_model, "approve", reviewer_context, data or {}, **kwargs)


def reject_concept_card(session: Any, card_model: Any, review_model: Any, card_uid: str, reviewer_context: Any, data: dict[str, Any] | None = None, **kwargs) -> tuple[Any, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    return _persist_review_action(session, card, review_model, "reject", reviewer_context, data or {}, **kwargs)


def request_card_revision(session: Any, card_model: Any, review_model: Any, card_uid: str, reviewer_context: Any, data: dict[str, Any] | None = None, **kwargs) -> tuple[Any, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    return _persist_review_action(session, card, review_model, "request_revision", reviewer_context, data or {}, **kwargs)


def mark_card_needs_more_evidence(session: Any, card_model: Any, review_model: Any, card_uid: str, reviewer_context: Any, data: dict[str, Any] | None = None, **kwargs) -> tuple[Any, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    return _persist_review_action(session, card, review_model, "mark_needs_more_evidence", reviewer_context, data or {}, **kwargs)


def reopen_concept_card(session: Any, card_model: Any, review_model: Any, card_uid: str, reviewer_context: Any, data: dict[str, Any] | None = None, **kwargs) -> tuple[Any, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    return _persist_review_action(session, card, review_model, "reopen", reviewer_context, data or {}, **kwargs)


def deprecate_concept_card(session: Any, card_model: Any, review_model: Any, card_uid: str, reviewer_context: Any, data: dict[str, Any] | None = None, **kwargs) -> tuple[Any, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    return _persist_review_action(session, card, review_model, "deprecate", reviewer_context, data or {}, **kwargs)


def dispatch_review_action(session: Any, card_model: Any, review_model: Any, card_uid: str, action: str, reviewer_context: Any, data: dict[str, Any] | None = None, **kwargs) -> tuple[Any, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    return _persist_review_action(session, card, review_model, action, reviewer_context, data or {}, **kwargs)


def assign_card_reviewer(
    session: Any,
    card_model: Any,
    review_model: Any,
    assignment_model: Any,
    card_uid: str,
    reviewer_context: Any,
    data: dict[str, Any] | None = None,
    *,
    audit_model: Any | None = None,
    audit_context: dict[str, Any] | None = None,
    policy_model: Any | None = None,
    permission_model: Any | None = None,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, Any, Any]:
    data = data or {}
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    if policy_model is not None and permission_model is not None:
        gate = course_review_policy.evaluate_card_against_review_policy(
            session,
            policy_model,
            permission_model,
            card,
            "assign_reviewer",
            reviewer_context,
            data,
        )
        if not gate.get("allowed"):
            _record_review_block_audit(
                session,
                audit_model,
                card,
                "assign_reviewer",
                reviewer_context,
                gate,
                data=data,
                audit_context=audit_context,
                now_fn=now_fn,
                commit=commit,
            )
            raise ConceptCardReviewError(f"review blocked by course policy: {gate.get('reason')}")
    reviewer = validate_review_action(card, "assign_reviewer", data, reviewer_context)
    now = now_fn() if now_fn else ""
    assignment = assignment_model(
        card_uid=card.card_uid,
        assigned_to=_text(data.get("assigned_to")),
        assigned_by=reviewer.get("reviewer_id"),
        assignment_status="active",
        due_at=_text(data.get("due_at")),
        created_at=now,
        updated_at=now,
    )
    session.add(assignment)
    session.flush()
    card, record = _persist_review_action(
        session,
        card,
        review_model,
        "assign_reviewer",
        reviewer,
        data,
        audit_model=audit_model,
        audit_context=audit_context,
        policy_model=policy_model,
        permission_model=permission_model,
        now_fn=now_fn,
        commit=False,
    )
    if commit:
        session.commit()
    else:
        session.flush()
    return card, record, assignment


def get_review_queue(
    session: Any,
    card_model: Any,
    filters: dict[str, Any] | None = None,
    *,
    review_model: Any | None = None,
) -> ReviewQueueResult:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    per_page = max(1, min(int(filters.get("per_page") or filters.get("page_size") or 20), 100))
    include_deprecated = _text(filters.get("include_deprecated")).lower() in {"1", "true", "yes", "on"}
    query = card_model.query
    status = _text(filters.get("machine_status") or filters.get("status"))
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        query = query.filter(card_model.status.in_(statuses))
    else:
        query = query.filter(card_model.status.in_(["draft", "needs_review"]))
    if not include_deprecated:
        query = query.filter(card_model.status != "deprecated")
    for field in ("course", "chapter"):
        value = _text(filters.get(field))
        if value:
            query = query.filter(getattr(card_model, field) == value)
    courses = filters.get("courses") or []
    if isinstance(courses, str):
        courses = [item.strip() for item in courses.split(",") if item.strip()]
    if isinstance(courses, list) and courses:
        query = query.filter(card_model.course.in_([_text(item) for item in courses if _text(item)]))
    risk_label = _text(filters.get("risk_label"))
    if risk_label:
        query = query.filter(card_model.risk_labels.ilike(f"%{risk_label}%"))
    updated_after = _text(filters.get("updated_after"))
    updated_before = _text(filters.get("updated_before"))
    if updated_after:
        query = query.filter(card_model.updated_at >= updated_after)
    if updated_before:
        query = query.filter(card_model.updated_at <= updated_before)
    human_status = _text(filters.get("human_review_status")).lower()
    if human_status and review_model is not None:
        reviewed_cards = session.query(review_model.card_uid)
        if human_status in {"unreviewed", "pending"}:
            query = query.filter(~card_model.card_uid.in_(reviewed_cards))
        else:
            action_by_status = {
                "accepted": ("accept_recommendation",),
                "alternative_selected": ("select_alternative_candidate",),
                "rejected": ("reject",),
                "deferred": ("defer_review",),
                "human_approved": (
                    "accept_recommendation",
                    "select_alternative_candidate",
                ),
            }
            actions = action_by_status.get(human_status, ())
            if actions:
                query = query.filter(
                    card_model.card_uid.in_(
                        reviewed_cards.filter(review_model.action.in_(actions))
                    )
                )
    reviewer = _text(filters.get("reviewer"))
    if reviewer:
        if reviewer.isdigit():
            query = query.filter(card_model.reviewed_by == int(reviewer))
        else:
            query = query.filter(card_model.reviewed_by.is_(None))
    q = _text(filters.get("q"))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(card_model.english_term.ilike(like), card_model.chinese_term.ilike(like)))
    total = query.count()
    items = query.order_by(card_model.updated_at.desc(), card_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return ReviewQueueResult(items=items, page=page, per_page=per_page, total=total)


def get_card_review_history(session: Any, review_model: Any, card_uid: str, filters: dict[str, Any] | None = None) -> ReviewQueueResult:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    per_page = max(1, min(int(filters.get("per_page") or filters.get("page_size") or 20), 100))
    query = session.query(review_model).filter_by(card_uid=_text(card_uid))
    total = query.count()
    items = query.order_by(review_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return ReviewQueueResult(items=items, page=page, per_page=per_page, total=total)


def serialize_review_record(record: Any) -> dict[str, Any]:
    return {
        "id": getattr(record, "id", None),
        "review_uid": getattr(record, "review_uid", ""),
        "card_uid": getattr(record, "card_uid", ""),
        "reviewer_id": getattr(record, "reviewer_id", None),
        "reviewer_role": getattr(record, "reviewer_role", ""),
        "reviewer_name": getattr(record, "reviewer_name", ""),
        "action": getattr(record, "action", ""),
        "previous_status": getattr(record, "previous_status", ""),
        "new_status": getattr(record, "new_status", ""),
        "decision": getattr(record, "decision", ""),
        "reason_code": getattr(record, "reason_code", ""),
        "review_comment": getattr(record, "review_comment", ""),
        "evidence_assessment": _loads_json(getattr(record, "evidence_assessment", "{}"), {}),
        "term_assessment": _loads_json(getattr(record, "term_assessment", "{}"), {}),
        "risk_assessment": _loads_json(getattr(record, "risk_assessment", "{}"), {}),
        "required_changes": _loads_json(getattr(record, "required_changes", "[]"), []),
        "resolved_risk_labels": _loads_json(getattr(record, "resolved_risk_labels", "[]"), []),
        "remaining_risk_labels": _loads_json(getattr(record, "remaining_risk_labels", "[]"), []),
        "verification_run_uid": getattr(record, "verification_run_uid", ""),
        "request_id": getattr(record, "request_id", ""),
        "created_at": getattr(record, "created_at", ""),
    }


def serialize_assignment(assignment: Any) -> dict[str, Any]:
    return {
        "id": getattr(assignment, "id", None),
        "assignment_uid": getattr(assignment, "assignment_uid", ""),
        "card_uid": getattr(assignment, "card_uid", ""),
        "assigned_to": getattr(assignment, "assigned_to", ""),
        "assigned_by": getattr(assignment, "assigned_by", None),
        "assignment_status": getattr(assignment, "assignment_status", ""),
        "due_at": getattr(assignment, "due_at", ""),
        "created_at": getattr(assignment, "created_at", ""),
        "updated_at": getattr(assignment, "updated_at", ""),
    }


def evidence_summary(card: Any) -> dict[str, Any]:
    english_count = _count_evidence(getattr(card, "english_evidence", "[]"))
    chinese_count = _count_evidence(getattr(card, "chinese_evidence", "[]"))
    return {
        "english_count": english_count,
        "chinese_count": chinese_count,
        "total_count": english_count + chinese_count,
        "has_english_evidence": english_count > 0,
        "has_chinese_evidence": chinese_count > 0,
    }


def serialize_review_queue_item(
    card: Any,
    *,
    session: Any | None = None,
    source_model: Any | None = None,
    chunk_model: Any | None = None,
    parse_model: Any | None = None,
) -> dict[str, Any]:
    data = concept_alignment_cards.serialize_concept_card(card)
    data["blocking_approval_risk_labels"] = _blocking_risks(card)
    data["evidence_summary"] = evidence_summary(card)
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
