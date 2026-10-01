# Task 12I-C-A — Real Provider Structured Output Contract Repair

## Executive conclusion

Technical status: `REAL_PROVIDER_STRUCTURED_OUTPUT_CONTRACT_CLOSED`.

Quality status:
`REAL_PROVIDER_STRUCTURED_OUTPUT_OFFLINE_BASELINE_ESTABLISHED`.

The DeepSeek production request now forces JSON Object mode, the Formal Prompt
has a new immutable structured-output version, the response model is checked
against an explicit compatibility policy, and the structured parser remains
fail closed. All verification used injected fake/replay transports. No
credential was read and no network or real Provider request was made.

## Exact 12I-B failure contract

The 12I-B request reached the registered DeepSeek chat-completions endpoint and
received a valid HTTP 200 JSON envelope. The envelope's selected choice carried
`finish_reason=stop` and model `deepseek-v4-flash`, but
`choices[0].message.content` was not a JSON document accepted by
`alignment-parser-v1`. The stable failure was
`provider_non_json_output`.

The request payload did **not** contain `response_format` or `max_tokens`.
The Prompt did already contain a JSON-only instruction and a complete schema
example, so the observed non-JSON output cannot be attributed to a missing
Prompt instruction alone. The response body is unavailable by design and was
neither restored nor inferred.

The transport already read only `choices[0].message.content`; it did not use
`reasoning_content`. It also recorded `finish_reason`, but did not previously
reject `finish_reason=length`. The parser already rejected prose, mixed
prose/JSON, malformed JSON, empty output, arrays, and Markdown fences.

## Production request and Prompt contract

The production path remains:

`GuardedLLMAlignmentProvider`
→ `alignment_prompting.build_alignment_prompt`
→ `DeepSeekHTTPTransport._build_request`
→ injected/production HTTP executor
→ response envelope extraction
→ structured alignment parser.

For the registered provider `deepseek-alignment-v1`,
`DeepSeekHTTPTransport` now unconditionally serializes:

```text
response_format = {"type": "json_object"}
max_tokens = 1000
stream = false
```

Caller request options are ignored for these server-owned fields, so an
ordinary API cannot disable JSON mode or raise the output-token ceiling.
The 1000-token ceiling preserves the previous controlled-smoke budget and is
above the contract minimum of 512 tokens.

The production Formal Prompt moves from
`formal_alignment@alignment-v1` to
`formal_alignment@alignment-json-v2`. The legacy version remains addressable
for historical replay/audit, but the real DeepSeek adapter forces the new
version and ignores a caller attempt to select the legacy version.

Only structured-output wording changed: the new version requires exactly one
JSON object, uses the literal word `JSON`, supplies the parser-aligned schema,
forbids surrounding explanation, and forbids Markdown code fences. Term
semantics, evidence standards, business scoring, and teaching-content
requirements were not changed.

## Parser and provenance behavior

The real structured path uses
`alignment-parser-json-v2` with schema
`alignment-output-json-v2`. It performs strict whole-document JSON parsing and
schema validation. It does not search for a JSON substring and does not strip
fences. A missing `content` field cannot be replaced with
`reasoning_content`.

The structured schema includes bounded English and Chinese evidence citations.
Every returned `(source_uid, chunk_uid)` must belong to the corresponding
input evidence allowlist. Unknown provenance fails closed as
`provider_schema_invalid`. `finish_reason=length` fails in transport as
`response_truncated` before parsing.

## Response model identity

Model policy
`deepseek-formal-model-compatibility@1.0.0` records both requested and resolved
identities. The requested alias remains `deepseek-chat`; the only accepted
response identities are:

- `deepseek-chat`
- `deepseek-v4-flash`

This explicitly covers the 12I-B observation without silently accepting
arbitrary models. `deepseek-v4-pro` and all other identities fail closed as
`response_model_not_allowed`. The system does not automatically change the
requested model.

## Pricing policy

Pricing is repository-pinned rather than fetched dynamically:
`deepseek-chat-pricing@2025-02-08`, effective `2025-02-08`, currency USD.
The fixed per-1000-token values are:

- cache-hit input: `0.00007`
- cache-miss input: `0.00027`
- output: `0.00110`

Preflight ceiling comparison uses the cache-miss input rate as the conservative
case. The pricing identity is the requested billable alias `deepseek-chat`,
while the resolved response identity remains separately audited. If any
required price is absent, cost is `null`, pricing is unavailable, and the
production external provider fails closed; missing pricing is never reported
as zero.

## Sanitized diagnostics

No response text or preview is retained. The safe output-shape audit contains
only:

- content presence and a coarse length bucket;
- first non-whitespace character class;
- JSON-object shape and outer-fence booleans;
- finish reason and response model;
- one-way response SHA-256;
- schema-validation stage and stable parser reason.

The diagnostic contains no original character, prefix, suffix, excerpt, full
Prompt, request body, response body, credential, or authorization header.

## Offline verification and safety

The new RED tests first demonstrated missing JSON mode, version/model policy,
truncation handling, pricing metadata, and shape-only diagnostics. After the
minimal implementation, fake/replay tests cover JSON serialization, strict
parsing, provenance allowlists, model compatibility, pricing-unavailable
behavior, and zero-network execution.

Task 12I-B remains the only real request. This task made:

- real Provider requests: `0`
- external API requests: `0`
- real credentials read: `false`
- second smoke attempt: `false`

The frozen V2 corpus/gold, retrieval, Chinese identification, pairing,
qualification, readiness, Prompt semantics, Provider transport endpoint, and
model request identity were not changed.

Validation results:

- structured-output and related targeted regression: `132 passed`;
- full pytest: `1491 passed`, `56 warnings`;
- `scripts/dev_check.py`: passed, including its independent 1491-test run,
  migration, and API smoke;
- `scripts/check_release_safety.py`: passed;
- `git diff --check`: passed.

Artifact SHA-256:

- `12ICA-provider-output-contract-manifest.json`:
  `180f5285ca6b4376889e64f08e9d15cd75e801643566975453e3419665462097`

Frozen Cross-Corpus V2 hashes remain:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

The accident database remains unchanged at SHA-256
`9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`,
size `1015808`, mtime `1785496597`, with WAL/SHM absent.

## Next recommendation

Do not infer live quality from the offline contract tests. A separately scoped
and separately authorized evaluation may later decide whether to run another
single-request smoke using `alignment-json-v2`. This task does not grant that
authorization and performs no real request.
