# LexiBridge AI Provider Governance

## Scope

This document defines how LexiBridge AI manages model providers in the Local MVP / pilot-ready codebase. It does not claim production readiness without a live provider, production secrets management, monitoring, and repeated evaluation.

## Provider Modes

| Mode | Purpose | Auto Approval |
| --- | --- | --- |
| `none` | AI disabled or not configured. | Never |
| `mock` | Deterministic local demo/test flow. | Never |
| `local_heuristic` | Low-confidence local fallback when no live model is available. | Never |
| `live` | Configured external provider such as DeepSeek or OpenAI-compatible API. | Only after evidence and evaluation gates |

## Provider Registry

`AIProviderConfig` records:

- `provider_name`
- `provider_mode`
- `default_model`
- `is_enabled`
- `is_default`
- feature flags such as JSON schema and vision support
- token limits, retry/timeout, and estimated token costs
- `health_status` and `last_healthcheck_at`

Only one enabled provider should be default. Production configuration must not use `mock`, `local_heuristic`, or `none` as the default provider.

## Healthcheck

`scripts/run_ai_provider_healthcheck.py` checks provider configuration and updates registry health. By default it performs a safe configuration check. Live probe mode may be used when a real key is configured.

Health states:

- `healthy`
- `degraded`
- `unhealthy`
- `unknown`

Provider failure must return structured `AI_PROVIDER_FAILED` or `AI_PROVIDER_NOT_CONFIGURED` errors instead of causing a Flask 500.

## Logging Boundary

AI call logs store hashes, metadata, token estimates, latency, status, and redacted previews. They do not store full prompts or responses by default. API keys, tokens, passwords, and long private content are redacted.

## Production Rules

Production must set:

- `AI_PROVIDER_MODE=live`
- `ALLOW_MOCK_AI=false`
- `ALLOW_LOCAL_HEURISTIC_AI=false`
- `AI_LOG_PROMPT_FULL=false`
- `AI_LOG_RESPONSE_FULL=false`
- `AI_LOG_REDACT_SECRETS=true`

Mock/local AI can support local demos, but must remain visibly marked and cannot produce `auto_approved` terminology cards.
