"""AI-specific usage and cost estimation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta


AI_EVENT_BY_TASK = {
    "term_extraction": "ai_term_extraction_call",
    "term_alignment": "ai_alignment_call",
    "evidence_check": "ai_evidence_check_call",
    "feedback_classification": "ai_feedback_classification_call",
    "evaluation_judge": "ai_evaluation_judge_call",
}


def estimate_ai_cost(input_tokens, output_tokens, input_rate=0.0, output_rate=0.0):
    try:
        input_tokens = max(0, int(input_tokens or 0))
        output_tokens = max(0, int(output_tokens or 0))
        input_rate = float(input_rate or 0)
        output_rate = float(output_rate or 0)
    except (TypeError, ValueError):
        return 0.0
    return round((input_tokens / 1000.0) * input_rate + (output_tokens / 1000.0) * output_rate, 8)


def daily_window(now=None):
    now = now or datetime.utcnow()
    return now - timedelta(days=1)


def monthly_window(now=None):
    now = now or datetime.utcnow()
    return now - timedelta(days=30)


def check_ai_quota(records, daily_call_limit=None, monthly_call_limit=None, daily_cost_limit=None, new_cost=0.0):
    ai_records = [record for record in records if str(getattr(record, "action_type", "")).startswith("ai_")]
    daily_cutoff = daily_window()
    monthly_cutoff = monthly_window()
    daily_calls = 0
    monthly_calls = 0
    daily_cost = 0.0
    for record in ai_records:
        created_at = getattr(record, "created_at", "") or ""
        try:
            created = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            created = datetime.utcnow()
        units = int(getattr(record, "units_used", 1) or 1)
        if created >= monthly_cutoff:
            monthly_calls += units
        if created >= daily_cutoff:
            daily_calls += units
            # UsageRecord in the Local MVP does not persist AI cost metadata yet.
            daily_cost += 0.0
    if daily_call_limit is not None and daily_calls + 1 > int(daily_call_limit):
        return False, "QUOTA_EXCEEDED", "AI daily call quota exceeded."
    if monthly_call_limit is not None and monthly_calls + 1 > int(monthly_call_limit):
        return False, "QUOTA_EXCEEDED", "AI monthly call quota exceeded."
    if daily_cost_limit is not None and daily_cost + float(new_cost or 0) > float(daily_cost_limit):
        return False, "QUOTA_EXCEEDED", "AI daily cost quota exceeded."
    return True, "", "allowed"


def summarize_ai_calls(call_logs):
    summary = {
        "total_calls": 0,
        "success_calls": 0,
        "error_calls": 0,
        "estimated_cost": 0.0,
        "by_provider": {},
        "by_task_type": {},
    }
    for log in call_logs:
        summary["total_calls"] += 1
        status = getattr(log, "status", "")
        if status == "success":
            summary["success_calls"] += 1
        else:
            summary["error_calls"] += 1
        provider = getattr(log, "provider_name", "") or "unknown"
        task_type = getattr(log, "task_type", "") or "unknown"
        summary["by_provider"][provider] = summary["by_provider"].get(provider, 0) + 1
        summary["by_task_type"][task_type] = summary["by_task_type"].get(task_type, 0) + 1
        summary["estimated_cost"] += float(getattr(log, "estimated_cost", 0.0) or 0.0)
    summary["estimated_cost"] = round(summary["estimated_cost"], 8)
    return summary
