"""Read-only preflight checks for alignment provider enablement.

The preflight layer reports whether a provider appears ready for future
enablement. It never enables a provider, never calls external networks, and
never exposes API key values.
"""

from __future__ import annotations

import json
import os
from typing import Any

from services import alignment_providers
from services import alignment_verification
from services import llm_provider_config
from services import provider_governance
from services.formal_real_provider_evaluation_policy import (
    is_trusted_formal_real_provider_evaluation_context,
)


PREFLIGHT_STATUSES = {"passed", "failed", "warning", "blocked"}
REPLAY_DRY_RUN_STATUSES = {"not_run", "passed", "failed"}

BLOCK_PROVIDER_NOT_REGISTERED = "provider_not_registered"
BLOCK_PROVIDER_POLICY_MISSING = "provider_policy_missing"
BLOCK_AUTO_APPROVE_FORBIDDEN = "provider_auto_approve_forbidden"
BLOCK_HUMAN_REVIEW_REQUIRED = "provider_human_review_required"
BLOCK_PRODUCTION_RESULT_FORBIDDEN = "provider_production_result_forbidden"
BLOCK_COURSE_SCOPE_MISSING = "course_scope_missing"
BLOCK_COURSE_NOT_ALLOWED = "course_not_allowed"
BLOCK_COURSE_BLOCKED = "course_blocked"
BLOCK_USAGE_LIMIT_MISSING = "provider_usage_limit_missing"
BLOCK_COST_LIMIT_MISSING = "provider_cost_limit_missing"
BLOCK_REPLAY_DRY_RUN_FAILED = "provider_replay_dry_run_failed"
BLOCK_CONFIG_INVALID = "provider_config_invalid"


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


def _append_unique(items: list[str], value: str) -> None:
    value = _text(value)
    if value and value not in items:
        items.append(value)


def _actor_id(actor: Any) -> str:
    if actor is None:
        return ""
    return str(getattr(actor, "id", "") or getattr(actor, "username", "") or "")


def _safe_policy_summary(policy: Any) -> dict[str, Any]:
    return provider_governance.serialize_provider_policy(policy) if policy is not None else {}


def _raw_policy_bool(policy: Any, key: str, default: bool = False) -> bool:
    if policy is None:
        return default
    if isinstance(policy, dict):
        return bool(policy.get(key, default))
    return bool(getattr(policy, key, default))


def _get_config(provider_name: str) -> tuple[dict[str, Any], dict[str, Any], list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    try:
        config = llm_provider_config.get_llm_provider_config(provider_name)
        safe_config = llm_provider_config.sanitize_provider_config(config)
    except llm_provider_config.LLMProviderConfigError as exc:
        config = {}
        safe_config = {}
        _append_unique(blocking, exc.error_code or BLOCK_CONFIG_INVALID)
    return config, safe_config, blocking, warnings


def check_api_key_presence(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return only API key metadata, never the API key value."""

    env_name = _text((config or {}).get("api_key_env_name"))
    return {
        "api_key_env_name": env_name,
        "api_key_present": bool(env_name and os.environ.get(env_name)),
    }


def check_provider_config(provider_name: str) -> dict[str, Any]:
    blocking: list[str] = []
    warnings: list[str] = []
    provider_registered = True
    provider_type = provider_governance.provider_type_for(provider_name)
    try:
        provider = alignment_providers.get_alignment_provider(provider_name)
        provider_type = provider.provider_type
    except alignment_providers.AlignmentProviderError:
        provider_registered = False
        _append_unique(blocking, BLOCK_PROVIDER_NOT_REGISTERED)

    config, safe_config, config_blocking, config_warnings = _get_config(provider_name)
    for item in config_blocking:
        _append_unique(blocking, item)
    for item in config_warnings:
        _append_unique(warnings, item)

    if provider_type == "external_llm":
        base_url = _text(safe_config.get("base_url"))
        if not base_url or base_url == "[invalid-url]":
            _append_unique(blocking, "provider_base_url_invalid")
        if not _text(safe_config.get("model_name")):
            _append_unique(blocking, "provider_model_missing")
    if safe_config:
        if int(safe_config.get("timeout_seconds") or 0) <= 0:
            _append_unique(blocking, "provider_timeout_invalid")
        if int(safe_config.get("max_prompt_chars") or 0) < 500:
            _append_unique(blocking, "provider_max_prompt_chars_invalid")
        if int(safe_config.get("max_output_chars") or 0) < 500:
            _append_unique(blocking, "provider_max_output_chars_invalid")

    api_key = check_api_key_presence(config)
    return {
        "provider_registered": provider_registered,
        "provider_name": provider_name,
        "provider_type": provider_type,
        "config_present": bool(safe_config),
        "config": safe_config,
        "api_key_env_name": api_key["api_key_env_name"],
        "api_key_present": api_key["api_key_present"],
        "blocking_reasons": blocking,
        "warnings": warnings,
    }


def check_policy_readiness(policy: Any, course: str | None = None) -> dict[str, Any]:
    data = _safe_policy_summary(policy)
    blocking: list[str] = []
    warnings: list[str] = []
    if not data:
        _append_unique(blocking, BLOCK_PROVIDER_POLICY_MISSING)
        return {
            "policy_present": False,
            "policy": {},
            "blocking_reasons": blocking,
            "warnings": warnings,
        }

    if _raw_policy_bool(policy, "allow_auto_approve", False):
        _append_unique(blocking, BLOCK_AUTO_APPROVE_FORBIDDEN)
    if not _raw_policy_bool(policy, "require_human_review", True):
        _append_unique(blocking, BLOCK_HUMAN_REVIEW_REQUIRED)
    if _raw_policy_bool(policy, "allow_production_result", False):
        _append_unique(blocking, BLOCK_PRODUCTION_RESULT_FORBIDDEN)

    allowed_courses = provider_governance.normalize_list(data.get("allowed_courses", []))
    blocked_courses = provider_governance.normalize_list(data.get("blocked_courses", []))
    course_name = _text(course)
    if not allowed_courses:
        _append_unique(blocking, BLOCK_COURSE_SCOPE_MISSING)
    if course_name and course_name in blocked_courses:
        _append_unique(blocking, BLOCK_COURSE_BLOCKED)
    elif (
        course_name
        and allowed_courses
        and "*" not in allowed_courses
        and course_name not in allowed_courses
    ):
        _append_unique(blocking, BLOCK_COURSE_NOT_ALLOWED)

    budget = check_budget_limits(data)
    for item in budget["blocking_reasons"]:
        _append_unique(blocking, item)
    for item in budget["warnings"]:
        _append_unique(warnings, item)

    return {
        "policy_present": True,
        "policy": data,
        "blocking_reasons": blocking,
        "warnings": warnings,
    }


def check_budget_limits(policy: Any) -> dict[str, Any]:
    data = _safe_policy_summary(policy)
    blocking: list[str] = []
    warnings: list[str] = []
    if int(data.get("max_calls_per_day") or 0) <= 0:
        _append_unique(blocking, BLOCK_USAGE_LIMIT_MISSING)
    if int(data.get("max_calls_per_month") or 0) <= 0:
        _append_unique(warnings, "provider_monthly_usage_limit_missing")
    if data.get("max_estimated_cost_per_call") in (None, ""):
        _append_unique(blocking, BLOCK_COST_LIMIT_MISSING)
    if data.get("max_estimated_cost_per_day") in (None, ""):
        _append_unique(warnings, "provider_daily_cost_limit_missing")
    return {"blocking_reasons": blocking, "warnings": warnings}


def check_human_review_gate(policy: Any) -> dict[str, Any]:
    ok = _raw_policy_bool(policy, "require_human_review", True)
    return {"ok": ok, "reason": "" if ok else BLOCK_HUMAN_REVIEW_REQUIRED}


def check_auto_approve_forbidden(policy: Any) -> dict[str, Any]:
    ok = not _raw_policy_bool(policy, "allow_auto_approve", False)
    return {"ok": ok, "reason": "" if ok else BLOCK_AUTO_APPROVE_FORBIDDEN}


def check_external_call_default_disabled(policy: Any, config: dict[str, Any] | None) -> dict[str, Any]:
    data = _safe_policy_summary(policy)
    cfg = llm_provider_config.sanitize_provider_config(config or {})
    return {
        "external_calls_enabled": bool(data.get("allow_external_calls", False) and cfg.get("enabled")),
        "policy_allows_external_calls": bool(data.get("allow_external_calls", False)),
        "config_enabled": bool(cfg.get("enabled")),
        "replay_only": bool(data.get("replay_only", True) or cfg.get("replay_mode", False)),
    }


def _dry_run_input(course: str | None = None) -> dict[str, Any]:
    course_name = _text(course) or "Provider Preflight Course"
    return {
        "english_term": "preflight test term",
        "chinese_term": "预检测试术语",
        "course": course_name,
        "chapter": "Preflight",
        "english_evidence": [{
            "chunk_uid": "preflight-en-chunk",
            "source_uid": "preflight-en-source",
            "source_title": "Preflight English Source",
            "course": course_name,
            "chapter": "Preflight",
            "language": "en",
            "trust_level": "teacher_verified",
            "quality_status": "native_text_ok",
            "snippet": "Preflight bounded English evidence snippet.",
            "score": 0.8,
        }],
        "chinese_evidence": [{
            "chunk_uid": "preflight-zh-chunk",
            "source_uid": "preflight-zh-source",
            "source_title": "Preflight Chinese Source",
            "course": course_name,
            "chapter": "Preflight",
            "language": "zh",
            "trust_level": "teacher_verified",
            "quality_status": "native_text_ok",
            "snippet": "预检使用的有界中文证据片段。",
            "score": 0.78,
        }],
        "risk_labels": ["bilingual_alignment_not_verified"],
        "retrieval_version": "preflight-replay-v1",
        "replay_response_type": "valid",
    }


def run_replay_dry_run(provider_name: str, course: str | None = None, replay_response_type: str = "valid") -> dict[str, Any]:
    del provider_name
    input_data = _dry_run_input(course)
    input_data["replay_response_type"] = replay_response_type or "valid"
    try:
        normalized = alignment_verification.validate_alignment_verification_input(input_data)
        provider = alignment_providers.get_alignment_provider(llm_provider_config.REPLAY_EXTERNAL_PROVIDER_NAME)
        output = provider.verify_alignment(normalized)
    except Exception as exc:
        return {
            "status": "failed",
            "provider_response_status": "dry_run_failed",
            "error_code": getattr(exc, "error_code", "provider_replay_dry_run_failed"),
            "error_message": str(exc),
        }
    if output.get("error_code") or output.get("verification_status") == "failed":
        return {
            "status": "failed",
            "provider_response_status": output.get("provider_response_status", "failed"),
            "error_code": output.get("error_code", "provider_replay_dry_run_failed"),
            "error_message": output.get("error_message", ""),
        }
    return {
        "status": "passed",
        "provider_response_status": output.get("provider_response_status", "replayed"),
        "prompt_version": output.get("prompt_version", ""),
        "parser_version": output.get("parser_version", ""),
        "output_schema_version": output.get("output_schema_version", ""),
    }


def _estimated_cost(provider_name: str, policy: dict[str, Any], config: dict[str, Any], course: str | None) -> dict[str, Any]:
    prompt_chars = min(
        int(policy.get("max_prompt_chars") or config.get("max_prompt_chars") or llm_provider_config.DEFAULT_MAX_PROMPT_CHARS),
        llm_provider_config.DEFAULT_MAX_PROMPT_CHARS,
    )
    output_chars = min(
        int(policy.get("max_output_chars") or config.get("max_output_chars") or llm_provider_config.DEFAULT_MAX_OUTPUT_CHARS),
        llm_provider_config.DEFAULT_MAX_OUTPUT_CHARS,
    )
    try:
        return llm_provider_config.estimate_alignment_call_cost(
            {"prompt_chars": prompt_chars, "expected_output_chars": output_chars, "course": _text(course)},
            provider_name,
            config={**config, "max_estimated_cost": policy.get("max_estimated_cost_per_call")},
        )
    except Exception:
        return {"estimated_cost": 0.0, "cost_is_estimate": True}


def build_preflight_report(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "preflight_uid": result.get("preflight_uid", ""),
        "provider_name": result.get("provider_name", ""),
        "provider_type": result.get("provider_type", ""),
        "policy_uid": result.get("policy_uid", ""),
        "course": result.get("course", ""),
        "check_status": result.get("check_status", "failed"),
        "overall_ready": bool(result.get("overall_ready", False)),
        "external_calls_enabled": bool(result.get("external_calls_enabled", False)),
        "replay_only": bool(result.get("replay_only", True)),
        "api_key_present": bool(result.get("api_key_present", False)),
        "api_key_env_name": result.get("api_key_env_name", ""),
        "policy_summary": result.get("policy_summary", {}),
        "check_results": result.get("check_results", {}),
        "blocking_reasons": result.get("blocking_reasons", []),
        "warnings": result.get("warnings", []),
        "replay_dry_run_status": result.get("replay_dry_run_status", "not_run"),
        "estimated_cost_per_call": result.get("estimated_cost_per_call"),
        "max_estimated_cost_per_call": result.get("max_estimated_cost_per_call"),
        "max_calls_per_day": result.get("max_calls_per_day") or 0,
        "max_calls_per_month": result.get("max_calls_per_month") or 0,
        "require_human_review": bool(result.get("require_human_review", True)),
        "allow_auto_approve": False,
        "allow_production_result": bool(result.get("allow_production_result", False)),
    }


def run_provider_preflight(
    session: Any,
    preflight_model: Any,
    policy_model: Any,
    provider_name: str,
    *,
    course: str | None = None,
    actor: Any = None,
    include_replay_dry_run: bool = True,
    replay_response_type: str = "valid",
    execution_key: str | None = None,
    now_fn=None,
    commit: bool = True,
    evaluation_context: Any = None,
) -> tuple[Any, dict[str, Any]]:
    provider = _text(provider_name)
    course_name = _text(course)
    provider_check = check_provider_config(provider)
    raw_policy = provider_governance.get_effective_provider_policy(
        session,
        policy_model,
        provider,
    )
    policy_data = _safe_policy_summary(raw_policy)
    policy_check = check_policy_readiness(raw_policy, course_name)
    config = provider_check.get("config", {})
    external_check = check_external_call_default_disabled(policy_data, config)
    dry_run = {"status": "not_run"}
    if include_replay_dry_run:
        dry_run = run_replay_dry_run(provider, course_name, replay_response_type=replay_response_type)

    blocking: list[str] = []
    warnings: list[str] = []
    for group in (provider_check, policy_check):
        for item in group.get("blocking_reasons", []):
            _append_unique(blocking, item)
        for item in group.get("warnings", []):
            _append_unique(warnings, item)
    if include_replay_dry_run and dry_run.get("status") != "passed":
        _append_unique(blocking, BLOCK_REPLAY_DRY_RUN_FAILED)
    if not include_replay_dry_run:
        _append_unique(warnings, "replay_dry_run_not_run")

    estimated_cost = _estimated_cost(provider, policy_data, config, course_name)
    per_call_limit = policy_data.get("max_estimated_cost_per_call")
    if per_call_limit not in (None, "") and float(estimated_cost.get("estimated_cost") or 0.0) > float(per_call_limit):
        _append_unique(blocking, "provider_cost_limit_exceeded")

    evaluation_external_allowed = (
        bool(external_check.get("external_calls_enabled", False))
        and is_trusted_formal_real_provider_evaluation_context(
            evaluation_context,
            provider_name=provider,
        )
    )
    overall_ready = (
        bool(provider_check.get("provider_registered"))
        and bool(policy_check.get("policy_present"))
        and not blocking
        and bool(policy_data.get("require_human_review", True))
        and not bool(policy_data.get("allow_auto_approve", False))
        and not bool(policy_data.get("allow_production_result", False))
        and int(policy_data.get("max_calls_per_day") or 0) > 0
        and int(policy_data.get("max_calls_per_month") or 0) > 0
        and per_call_limit not in (None, "")
        and policy_data.get("max_estimated_cost_per_day") not in (None, "")
        and dry_run.get("status") == "passed"
        and (
            not bool(external_check.get("external_calls_enabled", False))
            or evaluation_external_allowed
        )
    )
    if blocking:
        check_status = "failed"
    elif warnings:
        check_status = "warning"
    else:
        check_status = "passed"

    result = {
        "provider_name": provider,
        "provider_type": provider_check.get("provider_type", provider_governance.provider_type_for(provider)),
        "policy_uid": policy_data.get("policy_uid", ""),
        "course": course_name,
        "requested_by": _actor_id(actor),
        "check_status": check_status,
        "overall_ready": overall_ready,
        "external_calls_enabled": bool(external_check.get("external_calls_enabled", False)),
        "replay_only": bool(policy_data.get("replay_only", True)),
        "api_key_present": bool(provider_check.get("api_key_present", False)),
        "api_key_env_name": provider_check.get("api_key_env_name", ""),
        "policy_summary": policy_data,
        "check_results": {
            "provider_config": provider_check,
            "policy_readiness": policy_check,
            "external_call_default_disabled": external_check,
            "budget": check_budget_limits(policy_data),
            "human_review_gate": check_human_review_gate(policy_data),
            "auto_approve_forbidden": check_auto_approve_forbidden(policy_data),
            "replay_dry_run": dry_run,
            "audit_record_available": True,
            "network_called": False,
        },
        "blocking_reasons": blocking,
        "warnings": warnings,
        "replay_dry_run_status": dry_run.get("status", "not_run"),
        "estimated_cost_per_call": estimated_cost.get("estimated_cost"),
        "max_estimated_cost_per_call": per_call_limit,
        "max_calls_per_day": policy_data.get("max_calls_per_day") or 0,
        "max_calls_per_month": policy_data.get("max_calls_per_month") or 0,
        "require_human_review": bool(policy_data.get("require_human_review", True)),
        "allow_auto_approve": False,
        "allow_production_result": bool(policy_data.get("allow_production_result", False)),
    }
    run = create_preflight_run(
        session,
        preflight_model,
        result,
        execution_key=execution_key,
        now_fn=now_fn,
        commit=commit,
    )
    result["preflight_uid"] = getattr(run, "preflight_uid", "")
    return run, build_preflight_report(result)


def create_preflight_run(
    session: Any,
    preflight_model: Any,
    result: dict[str, Any],
    *,
    execution_key: str | None = None,
    now_fn=None,
    commit: bool = True,
) -> Any:
    run = preflight_model(
        execution_key=_text(execution_key) or None,
        provider_name=result.get("provider_name", ""),
        provider_type=result.get("provider_type", ""),
        policy_uid=result.get("policy_uid", ""),
        course=result.get("course", ""),
        requested_by=result.get("requested_by", ""),
        check_status=result.get("check_status", "failed"),
        overall_ready=bool(result.get("overall_ready", False)),
        external_calls_enabled=bool(result.get("external_calls_enabled", False)),
        replay_only=bool(result.get("replay_only", True)),
        api_key_present=bool(result.get("api_key_present", False)),
        api_key_env_name=result.get("api_key_env_name", ""),
        policy_summary=_dumps_json(result.get("policy_summary", {})),
        check_results=_dumps_json(result.get("check_results", {})),
        blocking_reasons=_dumps_json(result.get("blocking_reasons", [])),
        warnings=_dumps_json(result.get("warnings", [])),
        replay_dry_run_status=result.get("replay_dry_run_status", "not_run"),
        estimated_cost_per_call=result.get("estimated_cost_per_call"),
        max_estimated_cost_per_call=result.get("max_estimated_cost_per_call"),
        max_calls_per_day=int(result.get("max_calls_per_day") or 0),
        max_calls_per_month=int(result.get("max_calls_per_month") or 0),
        require_human_review=bool(result.get("require_human_review", True)),
        allow_auto_approve=False,
        allow_production_result=bool(result.get("allow_production_result", False)),
        created_at=now_fn() if now_fn else "",
    )
    session.add(run)
    if commit:
        session.commit()
    else:
        session.flush()
    return run


def serialize_preflight_run(run: Any) -> dict[str, Any]:
    return {
        "id": getattr(run, "id", None),
        "preflight_uid": getattr(run, "preflight_uid", ""),
        "provider_name": getattr(run, "provider_name", ""),
        "provider_type": getattr(run, "provider_type", ""),
        "policy_uid": getattr(run, "policy_uid", ""),
        "course": getattr(run, "course", ""),
        "requested_by": getattr(run, "requested_by", ""),
        "check_status": getattr(run, "check_status", ""),
        "overall_ready": bool(getattr(run, "overall_ready", False)),
        "external_calls_enabled": bool(getattr(run, "external_calls_enabled", False)),
        "replay_only": bool(getattr(run, "replay_only", True)),
        "api_key_present": bool(getattr(run, "api_key_present", False)),
        "api_key_env_name": getattr(run, "api_key_env_name", ""),
        "policy_summary": _loads_json(getattr(run, "policy_summary", "{}"), {}),
        "check_results": _loads_json(getattr(run, "check_results", "{}"), {}),
        "blocking_reasons": _loads_json(getattr(run, "blocking_reasons", "[]"), []),
        "warnings": _loads_json(getattr(run, "warnings", "[]"), []),
        "replay_dry_run_status": getattr(run, "replay_dry_run_status", ""),
        "estimated_cost_per_call": getattr(run, "estimated_cost_per_call", None),
        "max_estimated_cost_per_call": getattr(run, "max_estimated_cost_per_call", None),
        "max_calls_per_day": getattr(run, "max_calls_per_day", 0) or 0,
        "max_calls_per_month": getattr(run, "max_calls_per_month", 0) or 0,
        "require_human_review": bool(getattr(run, "require_human_review", True)),
        "allow_auto_approve": False,
        "allow_production_result": bool(getattr(run, "allow_production_result", False)),
        "created_at": getattr(run, "created_at", ""),
    }


def list_preflight_runs(
    session: Any,
    preflight_model: Any,
    provider_name: str,
    *,
    filters: dict[str, Any] | None = None,
) -> tuple[list[Any], int, int, int]:
    filters = filters or {}
    page = max(int(filters.get("page") or 1), 1)
    per_page = min(max(int(filters.get("per_page") or 20), 1), 100)
    query = session.query(preflight_model).filter_by(provider_name=_text(provider_name))
    if filters.get("course"):
        query = query.filter(preflight_model.course == _text(filters.get("course")))
    total = query.count()
    items = query.order_by(preflight_model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return items, total, page, per_page


def get_preflight_run(session: Any, preflight_model: Any, preflight_uid: str) -> Any | None:
    return session.query(preflight_model).filter_by(preflight_uid=_text(preflight_uid)).first()
