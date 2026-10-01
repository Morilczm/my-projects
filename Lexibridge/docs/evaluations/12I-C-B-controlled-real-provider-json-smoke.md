# Task 12I-C-B — Controlled Real Provider JSON Contract Verification

## Executive conclusion

- Technical status: `REAL_PROVIDER_JSON_SMOKE_EXECUTION_CLOSED`
- Quality status: `REAL_PROVIDER_JSON_SMOKE_QUALITY_BASELINE_ESTABLISHED`
- Execution status: `REAL_PROVIDER_JSON_SMOKE_SUCCEEDED`
- Exactly one real Provider request was sent. Retry count was zero, and no
  second request was attempted.
- The repaired JSON contract worked end to end: DeepSeek returned an
  unfenced JSON object, `alignment-parser-json-v2` parsed it, and
  `alignment-output-json-v2` validation passed.
- This task did not modify the Prompt, schema, parser, Provider transport,
  model policy, or any upstream retrieval/alignment component.

## Authorization and selection

All five authorization gates were true before execution:

- `DEEPSEEK_API_KEY_SET`
- `LEXIBRIDGE_EXTERNAL_LLM_ENABLED`
- `FORMAL_REAL_PROVIDER_EVAL_ENABLED`
- `FORMAL_REAL_PROVIDER_EVALUATION_ID_OK`
- CLI single-request confirmation

Only boolean states were printed. No credential value, length, prefix, suffix,
or authorization header was inspected or recorded.

The READY set was recomputed as three items. The runner sorted READY rows by
stable opaque production evaluation UID and selected the first:
`6f6945108e85f8ec6a1f`. This matched Task 12I-B; gold, aliases, required
propositions, and expected output quality were not used for selection.

The evaluation run ID, audit correlation ID, and idempotency key were newly
generated. The new idempotency hash differed from Task 12I-B.

## Frozen request contract

- Provider: `deepseek-alignment-v1`
- Requested model: `deepseek-chat`
- Prompt: `formal_alignment@alignment-json-v2`
- Response format: `{"type":"json_object"}`
- Parser: `alignment-parser-json-v2`
- Output schema: `alignment-output-json-v2`
- Maximum output tokens: 1000
- Input token ceiling: 1200
- Cost ceiling: USD 0.05
- Timeout: 30 seconds
- Request/billable-attempt/retry/concurrency budgets: `1/1/0/1`

The production request builder, Prompt registry, privacy/budget gates,
idempotency path, production transport, and production parser were used.
Neither the request body nor expanded Prompt was persisted.

## Real response result

- Real Provider requests: 1
- HTTP status: 200
- Retry count: 0
- Finish reason: `stop`
- Requested/resolved model: `deepseek-chat` / `deepseek-v4-flash`
- Compatibility: allowed by
  `deepseek-formal-model-compatibility@1.0.0`
- Input/output/total tokens: `920/295/1215`
- Pricing policy: `deepseek-chat-pricing@2025-02-08`
- Estimated cost: USD 0.0005729, cache-miss worst-case input pricing
- Cost ceiling passed: true

The Provider transport did not expose an internal latency measurement, so
`latency_ms` is explicitly `null` with reason
`provider_transport_latency_unavailable`; it is not reported as zero. The
outer command completed in approximately 9.8 seconds, which includes local
runner overhead and is not presented as Provider-only latency.

Safe output-shape diagnostics:

- content present: true
- content length bucket: `1024-4095`
- first non-whitespace character class: `object_open`
- looks like JSON object: true
- outer Markdown fence: false
- schema validation stage: `validated`
- stable parser reason: empty (success)

No response text, leading characters, reasoning content, or reconstructable
summary was retained.

## Parser, provenance, and isolated quality evaluation

The parser read the production content field and accepted one complete JSON
object. Schema validation passed, the production-selected pair was preserved,
and all cited source/chunk IDs belonged to the request's allowed provenance
set.

Only after parse/schema success did the isolated evaluator read frozen V2
gold. Results:

- selected pair preserved: true
- canonical Chinese term correct: true
- schema fields complete: true
- evidence citations valid: true
- hallucinated provenance count: 0
- draft structurally formable but not published: true
- unsupported-claim count, evidence-grounded-claim count, and required
  proposition coverage: not evaluated by this bounded smoke contract

Gold was not included in the request. No card was published and no formal
course data was written.

## Safety and regression verification

- Pre-request targeted suite: 112 passed
- Post-request targeted suite: 112 passed
- Full pytest: 1538 passed, 1 skipped
- `dev_check`: passed; its internal pytest also reported 1538 passed,
  1 skipped
- Release safety: passed
- `git diff --check`: passed
- Request/response bodies tracked: false
- Credential disclosed: false
- External API used: true, exactly once
- Real Provider requests: 1

The first sandboxed full-pytest attempt could not bind local loopback sockets.
The suite was rerun with loopback permission while explicitly removing the
DeepSeek credential and disabling real Provider flags; it then passed. This
environmental rerun did not perform an external request.

## Frozen V2 and accident database

V2 hashes remained:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

The accident database before/final identity remained:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: 1015808
- mtime: 1785496597
- WAL/SHM: absent/absent

## Sanitized artifacts

- `12ICB-real-provider-json-smoke-manifest.json`:
  `ebc4a3c4bac6b895a9e350cb52f38d4f2d28b8741029ffa8c9ddb4945a5e0b9f`
- `12ICB-real-provider-json-smoke-result.json`:
  `d0e21236d96cc4fbdad5ccb858d3714f74ca1cca9758a7ebd0b4523481ad6045`

## Recommendation

The strict real-Provider JSON output contract is now verified for one
controlled READY item. Stop here as required. Any expansion to additional
READY items, Prompt quality work, or card publication must be separately
authorized and must not reuse this task's request identity.
