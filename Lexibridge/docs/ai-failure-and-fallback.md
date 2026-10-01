# AI Failure and Fallback

## Failure Principles

AI provider failure must not crash document parsing, OCR, retrieval, or student search. It must be represented as structured state:

- `AI_PROVIDER_NOT_CONFIGURED`
- `AI_PROVIDER_FAILED`
- `AI_INVALID_RESPONSE`
- `QUOTA_EXCEEDED`

## Fallback Rules

When a live provider fails:

1. The failure is recorded in `AICallLog`.
2. The related run or card receives risk flags.
3. Local heuristic fallback may be used only if configured.
4. Fallback output cannot be `auto_approved`.

Mock/local fallback must include risk flags such as `mock_ai` or `local_heuristic_ai`.

## Alignment Impact

AI output is only one input to card generation. Evidence scores, prompt/model eligibility, OCR status, formula evidence status, and risk flags still control final status.

If AI returns `exact_match` but Chinese evidence is missing, the final state remains `no_zh_evidence` / `needs_more_evidence`.

If the AI response does not match the prompt schema, the system returns `AI_INVALID_RESPONSE` and the card remains in QC rather than being approved.
