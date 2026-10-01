# AI Cost Control

## Usage Events

AI calls record usage through `UsageRecord` with action types such as:

- `ai_term_extraction_call`
- `ai_alignment_call`
- `ai_evidence_check_call`
- `ai_feedback_classification_call`
- `ai_evaluation_judge_call`

Each event stores user, course, provider, model, estimated tokens, and estimated cost metadata.

## Quotas

Configuration:

```env
AI_DAILY_CALL_LIMIT_PER_USER=100
AI_MONTHLY_CALL_LIMIT_PER_USER=1000
AI_DAILY_COST_LIMIT_PER_USER=5.00
```

If a user exceeds a call or cost limit, `call_ai_task()` returns:

```json
{
  "status": "error",
  "error_code": "QUOTA_EXCEEDED",
  "message": "AI usage quota exceeded."
}
```

## Token and Cost Estimates

The Local MVP uses approximate token counts for cost governance. This is sufficient for pilot budget guardrails, but production should replace it with provider-reported usage when available.

## Admin Summary

Admin endpoints expose aggregate usage and recent call logs without exposing prompts, responses, or keys:

- `GET /api/admin/ai/usage`
- `GET /api/admin/ai/calls`
