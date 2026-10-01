# Task 12I-B — Controlled Single-Request Real Provider Smoke

## Executive conclusion

Technical status: `REAL_PROVIDER_SMOKE_EXECUTION_CLOSED`.

Quality status: `REAL_PROVIDER_SMOKE_QUALITY_INSUFFICIENT`.

Exactly one authorized, zero-retry request reached the production DeepSeek
transport. The endpoint returned HTTP 200 after 4715 ms and reported bounded
usage, but its content was not valid JSON for the fixed production schema.
The production `alignment-output-v1` parser rejected it with
`provider_non_json_output`. No retry or second request occurred.

## Authorization and credential preflight

Before execution, the safe preflight reported only:

- `DEEPSEEK_API_KEY_SET=True`
- `LEXIBRIDGE_EXTERNAL_LLM_ENABLED=True`
- `LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVAL_ENABLED=True`
- `LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVALUATION_ID_OK=True`

The existing Formal real-provider policy validated the environment gate,
evaluation identity, isolated database, registered external provider,
allowlisted model, credential presence, and one-request budget. The
evaluation-only runner added the independent exact CLI confirmation:

`--execute-single-real-request --confirm-single-request I_AUTHORIZE_ONE_REAL_PROVIDER_REQUEST`

The credential was consumed only inside the existing Provider abstraction.
Its value, length, prefix, suffix, and authorization header were not logged or
stored.

## Production execution chain

The exercised chain was:

`Task 12H READY row`
→ deterministic first READY selection
→ production-observable EN/ZH evidence and selected pair
→ `alignment_prompting.build_alignment_prompt`
→ `GuardedLLMAlignmentProvider`
→ `DeepSeekHTTPTransport`
→ DeepSeek chat-completions endpoint
→ `alignment_output_parser.parse_alignment_provider_output`
→ sanitized execution audit.

Provider ID was `deepseek-alignment-v1`; requested model was
`deepseek-chat`. The configured endpoint was
`https://api.deepseek.com/chat/completions`. The response envelope reported
model `deepseek-v4-flash`; no automatic model replacement or second request
was attempted.

The Prompt remained `formal_alignment@alignment-v1`. Prompt text, Provider
transport, model configuration, retrieval, identification, pairing,
qualification, readiness, and thresholds were unchanged.

## Sample selection and gold isolation

The runner sorted the three READY evaluation rows by their stable opaque row
identifier and selected the first. The selected audit identifier is
`6f6945108e85f8ec6a1f`. The production English extractor supplied the first
candidate bound to the selected English chunk; the Chinese term was the
production-selected top-1 pair.

Selection and request construction read no gold, aliases, required
propositions, or expected answer. The benchmark concept ID was not serialized
into the request. Gold was not read after the response because parsing failed,
so no gold-dependent offline quality score was produced.

## Request and budget contract

- Request budget: 1
- Billable-attempt budget: 1
- Selected items: 1
- Concurrency: 1
- Retry budget: 0
- Timeout: 30 seconds
- Estimated input ceiling: 1200 tokens
- Output ceiling: 1000 estimated tokens / 4000 output characters
- Cost ceiling: USD 0.05
- Prompt characters: 2995
- Preflight estimated input tokens: 749
- Request hash:
  `5b737eb973c1fde0a332d505be590941fa4825b9848f6efc6c7526148141706d`
- Idempotency-key hash:
  `f30048a054dbb1ef8d7f846a2beb28330ddc0dc571526e5d3b0e5b5ee3a218bd`

A repository-external attempt marker was written before transport. Reusing
the runner state fails closed without a second call. Request and Prompt bodies
were never written to repository artifacts.

The Provider reported 770 prompt tokens, 323 completion tokens, and 1093 total
tokens. Both component ceilings passed. The repository's production
configuration has no calibrated DeepSeek pricing, so a trustworthy monetary
cost could not be calculated; `estimated_cost` is recorded as null rather
than treating the internal zero placeholder as a real cost. This is a quality
and audit limitation, not permission to retry.

## HTTP, parser, and schema result

- Real Provider requests before/after: 0 / 1
- HTTP status: 200
- Latency: 4715 ms
- Retry count: 0
- Finish reason: `stop`
- Response hash:
  `e80cd079d0a22bd7265735add1f7e4c8794fe5bb6675ada46c68740608df8425`
- Parser: `alignment-parser-v1`
- Output schema: `alignment-output-v1`
- Parse status: fail closed
- Stable reason: `provider_non_json_output`
- Smoke status: `REAL_PROVIDER_SMOKE_PARSE_FAILED`

The response body is not in Git, the report, logs, or artifacts. Arbitrary
natural language was not promoted to structured success.

## Evidence and provenance validation

Input evidence used the governed V2 provenance:

- English: `en-s04` / `en-s04-p04`
- Chinese: `zh-s12` / `zh-s12-p01`

All four audit identifiers belonged to the request's allowed provenance set.
The production-selected pair was not changed, no REVIEW_REQUIRED or NOT_READY
row entered the request, and no hallucinated provenance was recorded.

Because response parsing failed, unsupported-claim count, grounded-claim
count, and required-proposition coverage are not scored. The safe conclusion
is insufficient quality, not a successful alignment judgment.

## Upstream preservation and recommendation

Task 12H remains 3 READY / 15 REVIEW_REQUIRED / 7 NOT_READY with false-ready
zero. Frozen retrieval, Chinese candidate, pairing, qualification, readiness,
Prompt, corpus, and gold were not changed.

Do not send a second request under Task 12I-B. Before any separately
authorized future Provider evaluation, investigate why the fixed JSON-only
Prompt produced non-JSON content and why the response model identity differed
from the requested model. Prompt or Provider changes require a separate task.

## Verification and frozen hashes

- Real Provider requests: 1
- Targeted real-provider and Task 12I-A regression: 122 passed
- Full pytest: 1476 passed, 56 warnings
- `scripts/dev_check.py`: passed, including its independent 1476-test run,
  migration, and backend API smoke
- `scripts/check_release_safety.py`: passed
- `git diff --check`: passed
- Request/response body tracked: false
- Credential disclosed: false

Artifact SHA-256:

- `12IB-real-provider-smoke-manifest.json`:
  `a0f05a70429a2e2a87fc3828957222adca49f90a201bc8b89b987c34112367cc`
- `12IB-real-provider-smoke-result.json`:
  `46830334d57655715dfafc0952dd281444327092434a76bf6281b77513f5bd42`

Cross-Corpus V2 remained frozen:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

The accident database remained unchanged at SHA-256
`9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`,
size `1015808`, and mtime `1785496597`; WAL and SHM remained absent.
