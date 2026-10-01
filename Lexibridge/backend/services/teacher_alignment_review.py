"""Teacher-facing adapter over the existing Formal Concept Card workflow."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from services import concept_alignment_cards
from services import concept_card_review
from services import provider_execution
from services import provider_readiness


FATAL_REVIEW_REASONS = {
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
HUMAN_APPROVAL_ACTIONS = {"accept_recommendation", "select_alternative_candidate"}
DRAFT_EDIT_FIELDS = {
    "concept_scope",
    "english_explanation",
    "chinese_explanation",
    "alignment_reason",
}


class TeacherAlignmentReviewError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_evidence(value: Any) -> list[dict[str, Any]]:
    items = _loads(value, [])
    result = []
    for raw in items if isinstance(items, list) else []:
        if not isinstance(raw, dict):
            continue
        result.append({
            "source_uid": _text(raw.get("source_uid")),
            "chunk_uid": _text(raw.get("chunk_uid")),
            "language": _text(raw.get("language")),
            "source_role": _text(raw.get("source_role") or raw.get("source_type")),
            "source_status": _text(raw.get("source_status") or "active"),
            "quality_status": _text(raw.get("quality_status")),
            "source_locator": _text(raw.get("source_locator"))[:240],
            "page_number": raw.get("page_number"),
            "page_end": raw.get("page_end"),
            "block_type": _text(raw.get("block_type")),
            "heading_path": _text(raw.get("heading_path"))[:240],
            "span_start": raw.get("span_start"),
            "span_end": raw.get("span_end"),
            "parse_uid": _text(raw.get("parse_uid")),
            "parse_block_uid": _text(raw.get("parse_block_uid")),
            "snippet": _text(
                raw.get("snippet") or raw.get("evidence_snippet") or raw.get("text")
            )[:600],
            "score": raw.get("score"),
            "extraction_score": raw.get("extraction_score"),
            "retrieval_score": raw.get("retrieval_score"),
            "rank": raw.get("rank"),
            "candidate_uid": _text(raw.get("candidate_uid")),
            "candidate_text": _text(
                raw.get("candidate_text") or raw.get("chinese_term")
            )[:160],
            "extraction_rank": raw.get("extraction_rank"),
            "retrieval_rank": raw.get("retrieval_rank"),
            "generated": bool(raw.get("generated")),
            "no_evidence": bool(raw.get("no_evidence")),
            "provenance_type": _text(raw.get("provenance_type")),
            "evidence_backed": bool(raw.get("evidence_backed", True)),
        })
    return result


def candidate_pool(card: Any) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for evidence in _bounded_evidence(getattr(card, "chinese_evidence", "[]")):
        text = evidence["candidate_text"]
        if not text or evidence["generated"] or evidence["no_evidence"]:
            continue
        if evidence["provenance_type"] == "GENERATED_HINT":
            continue
        if not (
            evidence["evidence_backed"]
            and evidence["source_uid"]
            and evidence["chunk_uid"]
            and evidence["parse_block_uid"]
        ):
            continue
        uid = evidence["candidate_uid"] or "candidate:" + _hash(
            "|".join((text, evidence["source_uid"], evidence["chunk_uid"]))
        )[:24]
        if uid in seen:
            continue
        seen.add(uid)
        rows.append({
            "candidate_uid": uid,
            "text": text,
            "normalized_text": text,
            "extraction_rank": int(evidence["extraction_rank"] or 999),
            "extraction_score": (
                evidence["extraction_score"]
                if evidence["extraction_score"] is not None
                else evidence["score"]
            ),
            "retrieval_rank": int(evidence["retrieval_rank"] or evidence["rank"] or 999),
            "retrieval_score": (
                evidence["retrieval_score"]
                if evidence["retrieval_score"] is not None
                else evidence["score"]
            ),
            "source_uid": evidence["source_uid"],
            "chunk_uid": evidence["chunk_uid"],
            "source_locator": evidence["source_locator"],
            "parse_uid": evidence["parse_uid"],
            "parse_block_uid": evidence["parse_block_uid"],
            "evidence_backed": True,
            "generated": False,
        })
    rows.sort(key=lambda row: (
        row["extraction_rank"],
        row["retrieval_rank"],
        row["source_uid"],
        row["chunk_uid"],
        row["normalized_text"],
    ))
    return rows[:20]


def _machine_candidate(card: Any, pool: list[dict[str, Any]]) -> dict[str, Any]:
    current = _text(getattr(card, "chinese_term", ""))
    return next(
        (row for row in pool if row["text"] == current),
        pool[0] if pool else {
            "candidate_uid": "",
            "text": current,
            "evidence_backed": False,
            "generated": False,
        },
    )


def _latest_review(session: Any, review_model: Any, card_uid: str):
    return (
        session.query(review_model)
        .filter_by(card_uid=card_uid)
        .order_by(review_model.id.desc())
        .first()
    )


def _latest_approval(session: Any, review_model: Any, card_uid: str):
    return (
        session.query(review_model)
        .filter(
            review_model.card_uid == card_uid,
            review_model.action.in_(sorted(HUMAN_APPROVAL_ACTIONS)),
        )
        .order_by(review_model.id.desc())
        .first()
    )


def _human_decision(review: Any | None) -> str:
    return {
        "accept_recommendation": "ACCEPTED",
        "select_alternative_candidate": "ALTERNATIVE_SELECTED",
        "reject": "REJECTED",
        "defer_review": "DEFERRED",
        "generate_draft": "DRAFT_GENERATED",
    }.get(_text(getattr(review, "action", "")), "UNREVIEWED")


def serialize_review_case(
    session: Any,
    card: Any,
    *,
    review_model: Any,
    workflow_item_model: Any | None = None,
    workflow_run_model: Any | None = None,
) -> dict[str, Any]:
    pool = candidate_pool(card)
    machine = _machine_candidate(card, pool)
    latest = _latest_review(session, review_model, card.card_uid)
    approval = _latest_approval(session, review_model, card.card_uid)
    item = None
    run = None
    if workflow_item_model is not None:
        item = (
            session.query(workflow_item_model)
            .filter_by(draft_card_uid=card.card_uid)
            .order_by(workflow_item_model.id.desc())
            .first()
        )
    if item is not None and workflow_run_model is not None:
        run = session.get(workflow_run_model, item.workflow_run_id)
    term_assessment = (
        _loads(getattr(approval, "term_assessment", "{}"), {})
        if approval
        else (_loads(getattr(latest, "term_assessment", "{}"), {}) if latest else {})
    )
    snapshot_machine_uid = _text(term_assessment.get("machine_candidate_uid"))
    if snapshot_machine_uid:
        machine = next(
            (
                row
                for row in pool
                if row["candidate_uid"] == snapshot_machine_uid
            ),
            machine,
        )
    business = {
        "ACCEPTED": "HUMAN_APPROVED",
        "ALTERNATIVE_SELECTED": "HUMAN_APPROVED",
        "REJECTED": "HUMAN_REJECTED",
        "DEFERRED": "DEFERRED",
        "DRAFT_GENERATED": "DRAFT_GENERATED",
    }.get(_human_decision(latest), "REVIEW_REQUIRED")
    return {
        "identity": {
            "alignment_case_uid": card.card_uid,
            "alignment_item_uid": _text(getattr(item, "item_uid", "")),
            "workflow_run_uid": _text(getattr(run, "run_uid", "")),
            "course": card.course,
            "source_document_uids": sorted({
                row["source_uid"]
                for row in (
                    _bounded_evidence(card.english_evidence)
                    + _bounded_evidence(card.chinese_evidence)
                )
                if row["source_uid"]
            }),
            "version": int(card.version or 1),
            "created_at": card.created_at,
            "updated_at": card.updated_at,
        },
        "english": {
            "canonical_term": card.english_term,
            "context": _text(card.english_explanation or card.concept_scope)[:800],
            "evidence": _bounded_evidence(card.english_evidence),
        },
        "chinese": {
            "candidate_pool": pool,
            "evidence": _bounded_evidence(card.chinese_evidence),
        },
        "machine_decision": {
            "decision": _text(getattr(item, "recommendation", "")) or "REVIEW_REQUIRED",
            "status": (
                _text(getattr(item, "status", ""))
                or _text(getattr(approval or latest, "previous_status", ""))
                or card.status
            ),
            "selected_candidate": machine,
            "pair_components": _loads(getattr(item, "confidence_summary", "{}"), {}),
            "qualification_decision": _text(
                _loads(getattr(item, "confidence_summary", "{}"), {}).get(
                    "qualification_decision"
                )
            ),
            "readiness_decision": _text(
                _loads(getattr(item, "confidence_summary", "{}"), {}).get(
                    "readiness_decision"
                )
            ),
            "risk_labels": _loads(card.risk_labels, []),
            "reason_codes": sorted(set(
                _loads(card.risk_labels, [])
                + ([_text(getattr(item, "error_code", ""))] if item and item.error_code else [])
            )),
            "retrieval_version": card.retrieval_version,
            "prompt_version": card.prompt_version,
            "model_name": card.model_name,
        },
        "human_review": {
            "status": "reviewed" if latest else "unreviewed",
            "decision": _human_decision(latest),
            "selected_candidate_uid": _text(
                term_assessment.get("selected_candidate_uid")
            ),
            "review_uid": _text(getattr(latest, "review_uid", "")),
            "approval_review_uid": _text(getattr(approval, "review_uid", "")),
            "reviewer_uid": getattr(latest, "reviewer_id", None),
            "rationale": _text(getattr(latest, "review_comment", ""))[:1000],
            "reviewed_at": _text(getattr(latest, "created_at", "")),
            "review_version": int(card.version or 1),
        },
        "draft": {
            "draft_uid": card.card_uid,
            "draft_status": "DRAFT" if card.status == "draft" else "NOT_GENERATED",
            "provider_execution_status": (
                "SUCCEEDED" if card.status == "draft" and card.model_name == "fake-llm-v1:v1"
                else "NOT_EXECUTED"
            ),
            "publication_status": "NOT_PUBLISHED" if card.status != "approved" else "PUBLISHED",
        },
        "business_status": business,
    }


def apply_human_decision(
    session: Any,
    card_model: Any,
    review_model: Any,
    card_uid: str,
    action: str,
    reviewer: Any,
    data: dict[str, Any],
    **kwargs,
):
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    idempotency_key = _text(data.get("idempotency_key"))
    if not idempotency_key:
        raise TeacherAlignmentReviewError(
            "idempotency key is required for teacher alignment decisions."
        )
    reused = (
        session.query(review_model)
        .filter_by(card_uid=card_uid, action=action, request_id=idempotency_key)
        .first()
    )
    if reused is not None:
        return card, reused, True
    pool = candidate_pool(card)
    machine = _machine_candidate(card, pool)
    selected = machine
    if action == "select_alternative_candidate":
        selected_uid = _text(data.get("selected_candidate_uid"))
        selected = next(
            (row for row in pool if row["candidate_uid"] == selected_uid), None
        )
        if selected is None:
            raise TeacherAlignmentReviewError(
                "selected candidate is not in the evidence-backed bounded pool."
            )
        card.chinese_term = selected["text"]
    if action in HUMAN_APPROVAL_ACTIONS and not selected.get("evidence_backed"):
        raise TeacherAlignmentReviewError(
            "human approval requires an evidence-backed candidate."
        )
    payload = {
        **data,
        "request_id": idempotency_key,
        "term_assessment": {
            "machine_candidate_uid": machine.get("candidate_uid", ""),
            "machine_candidate_text": machine.get("text", ""),
            "selected_candidate_uid": selected.get("candidate_uid", ""),
            "selected_candidate_text": selected.get("text", ""),
            "human_override": action == "select_alternative_candidate",
        },
        "risk_assessment": {
            "machine_risk_labels": _loads(card.risk_labels, []),
            "fatal_reasons": sorted(set(_loads(card.risk_labels, [])) & FATAL_REVIEW_REASONS),
        },
    }
    card, review = concept_card_review.dispatch_review_action(
        session, card_model, review_model, card_uid, action, reviewer, payload, **kwargs
    )
    return card, review, False


def _evidence_refs(card: Any, side: str) -> tuple[str, ...]:
    values = _bounded_evidence(getattr(card, f"{side}_evidence", "[]"))
    return tuple(sorted({
        f"{row['source_uid']}:{row['chunk_uid']}"
        for row in values
        if row["source_uid"] and row["chunk_uid"] and row["parse_block_uid"]
    }))


def evaluate_human_approved_readiness(
    session: Any, card: Any, review_model: Any, *, idempotency_key: str
) -> dict[str, Any]:
    approval = _latest_approval(session, review_model, card.card_uid)
    if approval is None:
        raise TeacherAlignmentReviewError("human approval is required.")
    risks = set(_loads(card.risk_labels, []))
    fatal = tuple(sorted(risks & FATAL_REVIEW_REASONS))
    english_refs = _evidence_refs(card, "english")
    chinese_refs = _evidence_refs(card, "chinese")
    result = provider_readiness.evaluate_provider_readiness(
        provider_readiness.ProviderReadinessInput(
            qualification_decision="QUALIFIED",
            qualification_policy=provider_readiness.ACTIVE_QUALIFICATION_POLICY,
            qualification_result_id=approval.review_uid,
            qualification_score=1.0,
            qualification_reason_codes=(),
            qualification_risk_labels=tuple(sorted(risks)),
            english_term=card.english_term,
            chinese_term=card.chinese_term,
            english_evidence_refs=english_refs,
            chinese_evidence_refs=chinese_refs,
            pair_rank=1,
            pair_score=float(card.confidence_score or 0.0),
            pair_model_metadata_complete=bool(card.retrieval_version),
            provider_id="fake-llm-v1",
            provider_policy_id="fake-provider-policy@1.0.0",
            provider_allowed=True,
            provider_config_complete=True,
            credential_reference_configured=True,
            prompt_registry_id="term_alignment",
            prompt_version="v1",
            prompt_approved=True,
            privacy_classification="LOCAL_ONLY_PRIVATE",
            privacy_gate_passed=True,
            provenance_gate_passed=bool(english_refs and chinese_refs),
            source_governance_passed=not fatal,
            request_token_budget=4000,
            cost_ceiling=0.0,
            retry_budget=0,
            timeout_seconds=30,
            idempotency_key=idempotency_key,
            audit_context=f"teacher-review:{approval.review_uid}",
            upstream_fatal_reasons=fatal,
        )
    )
    payload = provider_readiness.serialize_provider_readiness_result(result)
    payload["approval_source"] = "HUMAN_REVIEW"
    payload["review_decision_id"] = approval.review_uid
    return payload


def generate_fake_draft(
    session: Any,
    card_model: Any,
    review_model: Any,
    card_uid: str,
    reviewer: Any,
    data: dict[str, Any],
    **kwargs,
) -> dict[str, Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    key = _text(data.get("idempotency_key"))
    if not key:
        raise TeacherAlignmentReviewError("idempotency key is required.")
    reused = (
        session.query(review_model)
        .filter_by(card_uid=card_uid, action="generate_draft", request_id=key)
        .first()
    )
    if reused is not None:
        assessment = _loads(reused.risk_assessment, {})
        return {
            "draft": serialize_draft(card),
            "readiness": assessment.get("readiness", {}),
            "execution": assessment.get("execution", {}),
            "reused": True,
        }
    concept_alignment_cards.require_current_version(card, data)
    readiness = evaluate_human_approved_readiness(
        session, card, review_model, idempotency_key=key
    )
    if readiness["decision"] != "READY":
        raise TeacherAlignmentReviewError("governed readiness did not approve draft generation.")
    english_refs = _evidence_refs(card, "english")
    chinese_refs = _evidence_refs(card, "chinese")
    english_context = " ".join(
        row["snippet"] for row in _bounded_evidence(card.english_evidence)
    )[:800]
    chinese_context = " ".join(
        row["snippet"] for row in _bounded_evidence(card.chinese_evidence)
    )[:800]
    request = provider_execution.ProviderExecutionRequest(
        readiness_decision="READY",
        readiness_policy="governed-provider-readiness@1.0.0",
        readiness_result_id=readiness["readiness_id"],
        qualification_decision="QUALIFIED",
        qualification_policy=provider_readiness.ACTIVE_QUALIFICATION_POLICY,
        qualification_result_id=readiness["review_decision_id"],
        execution_admission=True,
        privacy_gate_passed=True,
        provenance_gate_passed=True,
        budget_gate_passed=True,
        provider_id="fake-llm-v1",
        model_id="fake-llm-v1:v1",
        prompt_registry_id="term_alignment",
        prompt_version="v1",
        english_term=card.english_term,
        english_context=english_context,
        english_evidence=english_refs,
        chinese_term=card.chinese_term,
        chinese_context=chinese_context,
        chinese_evidence=chinese_refs,
        request_token_ceiling=4000,
        cost_ceiling=0.0,
        timeout_seconds=30,
        retry_budget=0,
        idempotency_key=key,
        audit_correlation_id=f"teacher-draft:{card.card_uid}:{_hash(key)[:16]}",
    )
    execution = provider_execution.execute_provider_request(
        request,
        transport=provider_execution.DeterministicFakeProviderTransport(),
    )
    execution_payload = asdict(execution)
    execution_payload["reason_codes"] = list(execution.reason_codes)
    if execution.status != provider_execution.SUCCEEDED:
        raise TeacherAlignmentReviewError("fake Provider draft execution failed.")
    card.english_explanation = "Fake bounded concept explanation."
    card.chinese_explanation = "确定性 fake Provider 生成的有界概念说明。"
    card.alignment_reason = "Fake deterministic evidence-bound alignment."
    card.model_name = "fake-llm-v1:v1"
    card.prompt_version = "v1"
    _, review, _ = apply_human_decision(
        session,
        card_model,
        review_model,
        card_uid,
        "generate_draft",
        reviewer,
        {
            **data,
            "review_comment": "Governed fake Provider draft generated.",
            "risk_assessment": {
                "readiness": readiness,
                "execution": execution_payload,
            },
        },
        **kwargs,
    )
    review.risk_assessment = json.dumps(
        {"readiness": readiness, "execution": execution_payload},
        ensure_ascii=False,
        sort_keys=True,
    )
    session.commit()
    return {
        "draft": serialize_draft(card),
        "readiness": readiness,
        "execution": execution_payload,
        "reused": False,
    }


def serialize_draft(card: Any) -> dict[str, Any]:
    return {
        "draft_uid": card.card_uid,
        "alignment_case_uid": card.card_uid,
        "status": "DRAFT",
        "publication_status": "NOT_PUBLISHED",
        "english_term": card.english_term,
        "chinese_term": card.chinese_term,
        "concept_scope": _text(card.concept_scope)[:1000],
        "english_explanation": _text(card.english_explanation)[:2000],
        "chinese_explanation": _text(card.chinese_explanation)[:2000],
        "alignment_reason": _text(card.alignment_reason)[:2000],
        "english_evidence": _bounded_evidence(card.english_evidence),
        "chinese_evidence": _bounded_evidence(card.chinese_evidence),
        "model_name": card.model_name,
        "prompt_version": card.prompt_version,
        "version": int(card.version or 1),
        "updated_at": card.updated_at,
    }


def require_generated_draft(
    session: Any, review_model: Any, card_uid: str
) -> Any:
    record = (
        session.query(review_model)
        .filter_by(card_uid=card_uid, action="generate_draft")
        .order_by(review_model.id.desc())
        .first()
    )
    if record is None:
        raise TeacherAlignmentReviewError(
            "a governed Provider execution must generate the draft before editing."
        )
    return record


def update_draft(
    session: Any,
    card_model: Any,
    review_model: Any,
    card_uid: str,
    data: dict[str, Any],
    **kwargs,
):
    require_generated_draft(session, review_model, card_uid)
    invalid = sorted(set(data) - DRAFT_EDIT_FIELDS - {"expected_version"})
    if invalid:
        raise TeacherAlignmentReviewError(
            f"unsupported draft fields: {', '.join(invalid)}"
        )
    existing = concept_alignment_cards.get_concept_card(
        session, card_model, card_uid
    )
    if existing.status == "approved":
        raise TeacherAlignmentReviewError(
            "published cards cannot be edited as drafts."
        )
    card = concept_alignment_cards.update_concept_card(
        session,
        card_model,
        card_uid,
        data,
        require_concurrency_token=True,
        **kwargs,
    )
    return card
