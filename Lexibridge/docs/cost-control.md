# Cost Control

LexiBridge AI records usage events and estimates local costs for expensive actions.

## Usage Events

- `document_parse_page`
- `ocr_page`
- `formula_ocr_call`
- `ai_term_extraction_call`
- `ai_alignment_call`
- `knowledge_search`
- `evaluation_item`
- `pdf_export`

## Quotas

The Local MVP reuses `SubscriptionPlan` and `UsageRecord`.

Tracked limits:

- monthly pages
- monthly AI/search calls
- monthly formula OCR calls
- monthly exports

If a user exceeds a limit, feature code should return `QUOTA_EXCEEDED`.

## Estimation

The estimates are intentionally approximate. They are used for local review, not real billing.

Cost control helper:

```text
backend/services/cost_control.py
```

Production must replace estimates with provider invoices or metered billing records.
