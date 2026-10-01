"""Governance policy and usage guards for alignment providers."""

from __future__ import annotations

import json
from typing import Any

from services import llm_provider_config
from services import parse_quality_risk


POLICY_STATUSES = {"active", "draft", "disabled", "deprecated"}
MOCK_LOCAL_PROVIDERS = {"mock-rule-v1", "fake-llm-v1"}
REPLAY_PROVIDER_TYPES = {"mock", "fake_llm", "replay_llm"}

GOVERNANCE_ERROR_CODES = {
    "provider_policy_missing",
    "provider_disabled_by_policy",
    "provider_external_calls_not_allowed",
    "provider_replay_only",
    "course_not_allowed",
    "course_blocked",
    "provider_usage_limit_exceeded",
    "provider_daily_cost_limit_exceeded",
    "provider_monthly_cost_limit_exceeded",
    "provider_human_review_required",
    "provider_auto_approve_forbidden",
    "provider_policy_invalid",
    "provider_attach_not_allowed",
}


class ProviderGovernanceError(ValueError):
    """Raised when provider governance data is invalid."""


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
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        parsed = _loads_json(value, None)
        if parsed is None:
            return [value] if value else []
        value = parsed
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def provider_type_for(provider_name: str) -> str:
    provider = _text(provider_name)
    if provider == "mock-rule-v1":
        return "mock"
    if provider == "fake-llm-v1":
        return "fake_llm"
    if provider == llm_provider_config.REPLAY_EXTERNAL_PROVIDER_NAME:
        return "replay_llm"
    if provider in {
        llm_provider_config.DISABLED_EXTERNAL_PROVIDER_NAME,
        llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
    }:
        return "external_llm"
    return "unknown"


def default_policy_data(provider_name: str, provider_type: str | None = None) -> dict[str, Any]:
    provider = _text(provider_name)
    ptype = _text(provider_type) or provider_type_for(provider)
    return {
        "provider_name": provider,
        "provider_type": ptype,
        "enabled": False,
        "replay_only": True,
        "allow_external_calls": False,
        "allow_attach_to_card": False,
        "allow_production_result": False,
        "allow_auto_approve": False,
        "require_human_review": True,
        "allowed_courses": [],
        "blocked_courses": [],
        "allowed_roles": [],
        "max_calls_per_day": 0,
        "max_calls_per_month": 0,
        "max_estimated_cost_per_call": None,
        "max_estimated_cost_per_day": None,
        "max_prompt_chars": llm_provider_config.DEFAULT_MAX_PROMPT_CHARS,
        "max_output_chars": llm_provider_config.DEFAULT_MAX_OUTPUT_CHARS,
        "timeout_seconds": llm_provider_config.DEFAULT_TIMEOUT_SECONDS,
        "max_retries": llm_provider_config.DEFAULT_MAX_RETRIES,
        "status": "disabled",
    }


def builtin_local_policy(provider_name: str) -> dict[str, Any] | None:
    provider = _text(provider_name)
    if provider not in MOCK_LOCAL_PROVIDERS:
        return None
    data = default_policy_data(provider, provider_type_for(provider))
    data.update({
        "policy_uid": f"builtin-{provider}",
        "enabled": True,
        "replay_only": True,
        "allow_attach_to_card": True,
        "status": "active",
        "allowed_roles": ["student", "teacher", "admin"],
        "builtin": True,
    })
    if provider == "mock-rule-v1":
        data.update({
            "allowed_courses": ["*"],
            "max_calls_per_day": 100,
            "max_calls_per_month": 1000,
            "max_estimated_cost_per_call": 0.0,
            "max_estimated_cost_per_day": 0.0,
        })
    return data


def serialize_provider_policy(policy: Any) -> dict[str, Any]:
    if policy is None:
        return {}
    if isinstance(policy, dict):
        data = dict(policy)
    else:
        data = {
            "id": getattr(policy, "id", None),
            "policy_uid": getattr(policy, "policy_uid", ""),
            "provider_name": getattr(policy, "provider_name", ""),
            "provider_type": getattr(policy, "provider_type", ""),
            "enabled": bool(getattr(policy, "enabled", False)),
            "replay_only": bool(getattr(policy, "replay_only", True)),
            "allow_external_calls": bool(getattr(policy, "allow_external_calls", False)),
            "allow_attach_to_card": bool(getattr(policy, "allow_attach_to_card", False)),
            "allow_production_result": bool(getattr(policy, "allow_production_result", False)),
            "allow_auto_approve": bool(getattr(policy, "allow_auto_approve", False)),
            "require_human_review": bool(getattr(policy, "require_human_review", True)),
            "allowed_courses": normalize_list(getattr(policy, "allowed_courses", [])),
            "blocked_courses": normalize_list(getattr(policy, "blocked_courses", [])),
            "allowed_roles": normalize_list(getattr(policy, "allowed_roles", [])),
            "max_calls_per_day": getattr(policy, "max_calls_per_day", 0) or 0,
            "max_calls_per_month": getattr(policy, "max_calls_per_month", 0) or 0,
            "max_estimated_cost_per_call": getattr(policy, "max_estimated_cost_per_call", None),
            "max_estimated_cost_per_day": getattr(policy, "max_estimated_cost_per_day", None),
            "max_prompt_chars": getattr(policy, "max_prompt_chars", None),
            "max_output_chars": getattr(policy, "max_output_chars", None),
            "timeout_seconds": getattr(policy, "timeout_seconds", None),
            "max_retries": getattr(policy, "max_retries", None),
            "status": getattr(policy, "status", ""),
            "created_by": getattr(policy, "created_by", None),
            "updated_by": getattr(policy, "updated_by", None),
            "created_at": getattr(policy, "created_at", ""),
            "updated_at": getattr(policy, "updated_at", ""),
        }
    data["allowed_courses"] = normalize_list(data.get("allowed_courses", []))
    data["blocked_courses"] = normalize_list(data.get("blocked_courses", []))
    data["allowed_roles"] = normalize_list(data.get("allowed_roles", []))
    data["allow_auto_approve"] = False
    data["require_human_review"] = True
    return data


def serialize_provider_usage_record(record: Any) -> dict[str, Any]:
    return {
        "id": getattr(record, "id", None),
        "usage_uid": getattr(record, "usage_uid", ""),
        "provider_name": getattr(record, "provider_name", ""),
        "provider_type": getattr(record, "provider_type", ""),
        "run_uid": getattr(record, "run_uid", ""),
        "card_uid": getattr(record, "card_uid", ""),
        "course": getattr(record, "course", ""),
        "chapter": getattr(record, "chapter", ""),
        "request_id": getattr(record, "request_id", ""),
        "estimated_input_tokens": getattr(record, "estimated_input_tokens", 0) or 0,
        "estimated_output_tokens": getattr(record, "estimated_output_tokens", 0) or 0,
        "estimated_cost": getattr(record, "estimated_cost", 0.0) or 0.0,
        "actual_cost": getattr(record, "actual_cost", None),
        "provider_response_status": getattr(record, "provider_response_status", ""),
        "error_code": getattr(record, "error_code", ""),
        "error_message": getattr(record, "error_message", ""),
        "created_at": getattr(record, "created_at", ""),
    }


def get_provider_policy(session: Any, policy_model: Any, provider_name: str) -> Any | None:
    return session.query(policy_model).filter_by(provider_name=_text(provider_name)).first()


def get_effective_provider_policy(session: Any, policy_model: Any, provider_name: str) -> Any | dict[str, Any] | None:
    policy = get_provider_policy(session, policy_model, provider_name)
    if policy is not None:
        return policy
    return builtin_local_policy(provider_name)


def _apply_policy_data(policy: Any, data: dict[str, Any], actor: Any = None) -> Any:
    base = default_policy_data(data.get("provider_name") or getattr(policy, "provider_name", ""), data.get("provider_type") or getattr(policy, "provider_type", ""))
    merged = {**base, **dict(data or {})}
    policy.provider_name = _text(merged.get("provider_name"))
    policy.provider_type = _text(merged.get("provider_type")) or provider_type_for(policy.provider_name)
    policy.enabled = bool(merged.get("enabled", False))
    policy.replay_only = bool(merged.get("replay_only", True))
    policy.allow_external_calls = bool(merged.get("allow_external_calls", False))
    policy.allow_attach_to_card = bool(merged.get("allow_attach_to_card", False))
    policy.allow_production_result = bool(merged.get("allow_production_result", False))
    policy.allow_auto_approve = False
    policy.require_human_review = True
    policy.allowed_courses = _dumps_json(normalize_list(merged.get("allowed_courses", [])))
    policy.blocked_courses = _dumps_json(normalize_list(merged.get("blocked_courses", [])))
    policy.allowed_roles = _dumps_json(normalize_list(merged.get("allowed_roles", [])))
    policy.max_calls_per_day = int(merged.get("max_calls_per_day") or 0)
    policy.max_calls_per_month = int(merged.get("max_calls_per_month") or 0)
    policy.max_estimated_cost_per_call = merged.get("max_estimated_cost_per_call")
    policy.max_estimated_cost_per_day = merged.get("max_estimated_cost_per_day")
    policy.max_prompt_chars = int(merged.get("max_prompt_chars") or llm_provider_config.DEFAULT_MAX_PROMPT_CHARS)
    policy.max_output_chars = int(merged.get("max_output_chars") or llm_provider_config.DEFAULT_MAX_OUTPUT_CHARS)
    policy.timeout_seconds = llm_provider_config.normalize_provider_timeout(merged.get("timeout_seconds"))
    policy.max_retries = llm_provider_config.normalize_provider_retry_policy(merged.get("max_retries")).get("max_retries", 0)
    status = _text(merged.get("status")) or ("active" if policy.enabled else "disabled")
    policy.status = status if status in POLICY_STATUSES else "disabled"
    actor_id = getattr(actor, "id", None)
    if actor_id is not None:
        if not getattr(policy, "created_by", None):
            policy.created_by = actor_id
        policy.updated_by = actor_id
    return policy


def create_or_update_provider_policy(
    session: Any,
    policy_model: Any,
    provider_name: str,
    data: dict[str, Any] | None,
    *,
    actor: Any = None,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, bool]:
    provider = _text(provider_name)
    policy = get_provider_policy(session, policy_model, provider)
    created = policy is None
    if created:
        policy = policy_model(provider_name=provider)
        session.add(policy)
        if now_fn:
            policy.created_at = now_fn()
    payload = {"provider_name": provider, **dict(data or {})}
    _apply_policy_data(policy, payload, actor=actor)
    if now_fn:
        policy.updated_at = now_fn()
    if commit:
        session.commit()
    else:
        session.flush()
    return policy, created


def check_course_scope(policy: dict[str, Any], course: str) -> tuple[bool, str]:
    course_name = _text(course)
    blocked = set(normalize_list(policy.get("blocked_courses", [])))
    allowed = set(normalize_list(policy.get("allowed_courses", [])))
    if course_name and course_name in blocked:
        return False, "course_blocked"
    if allowed and "*" not in allowed and course_name not in allowed:
        return False, "course_not_allowed"
    return True, ""


def check_role_scope(policy: dict[str, Any], actor_role: str) -> tuple[bool, str]:
    allowed = set(normalize_list(policy.get("allowed_roles", [])))
    if allowed and _text(actor_role) not in allowed:
        return False, "provider_policy_invalid"
    return True, ""


def _date_prefixes(now_text: str) -> tuple[str, str]:
    now_text = _text(now_text)
    day = now_text[:10]
    month = now_text[:7]
    return day, month


def _usage_query(session: Any, usage_model: Any, provider_name: str, prefix: str):
    return session.query(usage_model).filter(
        usage_model.provider_name == _text(provider_name),
        usage_model.created_at.like(f"{prefix}%"),
    )


def check_usage_limits(
    session: Any,
    usage_model: Any,
    policy: dict[str, Any],
    provider_name: str,
    *,
    now_text: str = "",
) -> tuple[bool, str]:
    day, month = _date_prefixes(now_text)
    if policy.get("max_calls_per_day") and day:
        if _usage_query(session, usage_model, provider_name, day).count() >= int(policy.get("max_calls_per_day") or 0):
            return False, "provider_usage_limit_exceeded"
    if policy.get("max_calls_per_month") and month:
        if _usage_query(session, usage_model, provider_name, month).count() >= int(policy.get("max_calls_per_month") or 0):
            return False, "provider_usage_limit_exceeded"
    return True, ""


def check_cost_limits(
    session: Any,
    usage_model: Any,
    policy: dict[str, Any],
    provider_name: str,
    estimated_cost: dict[str, Any] | None,
    *,
    now_text: str = "",
) -> tuple[bool, str]:
    estimate = estimated_cost or {}
    cost = float(estimate.get("estimated_cost") or 0.0)
    per_call = policy.get("max_estimated_cost_per_call")
    if per_call not in (None, "") and cost > float(per_call):
        return False, "provider_cost_limit_exceeded"
    per_day = policy.get("max_estimated_cost_per_day")
    day, _ = _date_prefixes(now_text)
    if per_day not in (None, "") and day:
        existing = sum(float(item.estimated_cost or 0.0) for item in _usage_query(session, usage_model, provider_name, day).all())
        if existing + cost > float(per_day):
            return False, "provider_daily_cost_limit_exceeded"
    return True, ""


def _provider_config_overrides(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_prompt_chars": policy.get("max_prompt_chars"),
        "max_output_chars": policy.get("max_output_chars"),
        "timeout_seconds": policy.get("timeout_seconds"),
        "max_retries": policy.get("max_retries"),
        "max_estimated_cost": policy.get("max_estimated_cost_per_call"),
    }


def estimate_request_cost(provider_name: str, input_data: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        config = llm_provider_config.get_llm_provider_config(provider_name, overrides=_provider_config_overrides(policy or {}))
    except llm_provider_config.LLMProviderConfigError:
        config = {
            "max_output_chars": llm_provider_config.DEFAULT_MAX_OUTPUT_CHARS,
            "cost_per_1k_input_tokens": 0.001,
            "cost_per_1k_output_tokens": 0.001,
        }
    input_chars = len(json.dumps(input_data or {}, ensure_ascii=False, sort_keys=True))
    return llm_provider_config.estimate_alignment_call_cost(
        {"input_chars": input_chars, "expected_output_chars": config.get("max_output_chars")},
        provider_name,
        config=config,
    )


def evaluate_provider_request(
    session: Any,
    policy_model: Any,
    usage_model: Any,
    provider_name: str,
    input_data: dict[str, Any],
    *,
    actor_role: str = "",
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
) -> dict[str, Any]:
    del audit_context
    provider = _text(provider_name)
    raw_policy = get_effective_provider_policy(session, policy_model, provider)
    if raw_policy is None:
        return build_provider_blocked_result("provider_policy_missing", {"provider_name": provider})
    policy = serialize_provider_policy(raw_policy)
    estimated_cost = estimate_request_cost(provider, input_data, policy)
    base = {
        "policy_uid": policy.get("policy_uid", ""),
        "policy": policy,
        "requires_human_review": True,
        "estimated_cost": estimated_cost,
    }
    if policy.get("allow_auto_approve"):
        return build_provider_blocked_result("provider_auto_approve_forbidden", base)
    if policy.get("status") != "active":
        return build_provider_blocked_result("provider_disabled_by_policy", base)
    if not policy.get("enabled"):
        return build_provider_blocked_result("provider_disabled_by_policy", base)
    role_ok, role_reason = check_role_scope(policy, actor_role)
    if not role_ok:
        return build_provider_blocked_result(role_reason, base)
    course_ok, course_reason = check_course_scope(policy, input_data.get("course", ""))
    if not course_ok:
        return build_provider_blocked_result(course_reason, base)
    provider_type = policy.get("provider_type") or provider_type_for(provider)
    if policy.get("replay_only") and provider_type not in REPLAY_PROVIDER_TYPES:
        return build_provider_blocked_result("provider_replay_only", base)
    if provider_type == "external_llm" and not policy.get("allow_external_calls"):
        return build_provider_blocked_result("provider_external_calls_not_allowed", base)
    now_text = now_fn() if now_fn else ""
    usage_ok, usage_reason = check_usage_limits(session, usage_model, policy, provider, now_text=now_text)
    if not usage_ok:
        return build_provider_blocked_result(usage_reason, base)
    cost_ok, cost_reason = check_cost_limits(session, usage_model, policy, provider, estimated_cost, now_text=now_text)
    if not cost_ok:
        return build_provider_blocked_result(cost_reason, base)
    reason = "allowed_replay" if policy.get("replay_only") else "allowed"
    return {"allowed": True, "reason": reason, "details": base, **base}


def build_provider_blocked_result(reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "reason": reason,
        "details": details or {},
        "policy_uid": (details or {}).get("policy_uid", ""),
        "requires_human_review": True,
        "estimated_cost": (details or {}).get("estimated_cost", {}),
    }


def provider_blocked_output(provider_name: str, provider_type: str, gate_result: dict[str, Any]) -> dict[str, Any]:
    reason = gate_result.get("reason") or "provider_policy_invalid"
    policy = gate_result.get("policy") or gate_result.get("details", {}).get("policy", {})
    return {
        "provider_name": provider_name,
        "provider_type": provider_type or provider_type_for(provider_name),
        "provider_version": "governance-v1",
        "alignment_decision": "uncertain",
        "alignment_confidence": None,
        "recommendation": "needs_review",
        "risk_labels": parse_quality_risk.merge_risk_labels([reason], ["alignment_provider_policy_blocked"]),
        "evidence_assessment": {
            "english_evidence_supported": False,
            "chinese_evidence_supported": False,
            "cross_language_support": "missing",
            "evidence_limitations": [reason],
        },
        "term_assessment": {
            "english_term_ok": False,
            "chinese_term_ok": False,
            "candidate_ambiguity": "high",
            "notes": "Provider request was blocked by governance policy.",
        },
        "course_context_assessment": {
            "course_match": None,
            "chapter_match": None,
            "notes": "",
        },
        "explanation": "Alignment provider request was blocked by provider governance policy.",
        "limitations": ["provider_governance_blocked"],
        "is_production_result": False,
        "can_auto_approve": False,
        "verification_status": "failed",
        "provider_response_status": reason,
        "estimated_cost": gate_result.get("estimated_cost", {}),
        "retry_count": 0,
        "error_code": reason,
        "error_message": reason,
        "policy_uid": gate_result.get("policy_uid", policy.get("policy_uid", "")),
    }


def requires_human_review_for_verification(run_or_result: Any, policy: Any) -> bool:
    del run_or_result
    data = serialize_provider_policy(policy)
    return bool(data.get("require_human_review", True))


def can_attach_verification_to_card(run_or_result: Any, policy: Any) -> bool:
    del run_or_result
    data = serialize_provider_policy(policy)
    return bool(data.get("allow_attach_to_card", False))


def can_mark_alignment_ready_for_review(run_or_result: Any, policy: Any) -> bool:
    del run_or_result
    return requires_human_review_for_verification({}, policy)


def can_auto_approve_alignment(run_or_result: Any, policy: Any) -> bool:
    del run_or_result, policy
    return False


def record_provider_usage(
    session: Any,
    usage_model: Any,
    provider_name: str,
    *,
    execution_key: str | None = None,
    run_uid: str = "",
    input_summary: dict[str, Any] | None = None,
    result_summary: dict[str, Any] | None = None,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = True,
) -> Any:
    input_summary = input_summary or {}
    result_summary = result_summary or {}
    estimated_cost = result_summary.get("estimated_cost") or input_summary.get("estimated_cost") or {}
    record = usage_model(
        execution_key=_text(execution_key) or None,
        provider_name=provider_name,
        provider_type=result_summary.get("provider_type") or provider_type_for(provider_name),
        run_uid=run_uid or result_summary.get("run_uid", ""),
        card_uid=result_summary.get("card_uid") or input_summary.get("card_uid", ""),
        course=input_summary.get("course", ""),
        chapter=input_summary.get("chapter", ""),
        request_id=(audit_context or {}).get("request_id", ""),
        estimated_input_tokens=estimated_cost.get("estimated_input_tokens", 0) or 0,
        estimated_output_tokens=estimated_cost.get("estimated_output_tokens", 0) or 0,
        estimated_cost=estimated_cost.get("estimated_cost", 0.0) or 0.0,
        actual_cost=result_summary.get("actual_cost"),
        provider_response_status=result_summary.get("provider_response_status", ""),
        error_code=result_summary.get("error_code", ""),
        error_message=result_summary.get("error_message", ""),
        created_at=now_fn() if now_fn else "",
    )
    session.add(record)
    if commit:
        session.commit()
    else:
        session.flush()
    return record


def list_provider_usage_records(
    session: Any,
    usage_model: Any,
    provider_name: str,
    *,
    filters: dict[str, Any] | None = None,
) -> tuple[list[Any], int, int, int]:
    filters = filters or {}
    page = max(int(filters.get("page") or 1), 1)
    per_page = min(max(int(filters.get("per_page") or 20), 1), 100)
    query = session.query(usage_model).filter_by(provider_name=_text(provider_name))
    if filters.get("course"):
        query = query.filter(usage_model.course == _text(filters.get("course")))
    if filters.get("date_from"):
        query = query.filter(usage_model.created_at >= _text(filters.get("date_from")))
    if filters.get("date_to"):
        query = query.filter(usage_model.created_at <= _text(filters.get("date_to")))
    total = query.count()
    items = query.order_by(usage_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return items, total, page, per_page
