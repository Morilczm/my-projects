# Task 12I-A — Governed Provider Execution Contract and Zero-Request Dry Run

## Executive conclusion

Technical status: `PROVIDER_EXECUTION_CONTRACT_CLOSED`.

Quality status: `PROVIDER_EXECUTION_DRY_RUN_BASELINE_ESTABLISHED`.

A bounded execution service now consumes only readiness `READY` inputs,
constructs a deterministic request, invokes an injected deterministic fake
transport, applies the existing strict response contracts, and returns a
sanitized execution audit result. The service has no real transport selector,
credential loader, live health probe, or network client. Real Provider
requests, external network requests, and real credential reads were all zero.

## Existing execution call chain and root cause

The production Formal chain is:

`PreparedFormalItemVerificationInput`
→ `evaluate_formal_prepared_readiness`
→ safe draft/approved-card handling
→ `provider_governance.evaluate_provider_request`
→ `provider_preflight.run_provider_preflight`
→ `provider.verify_alignment`
→ `alignment_output_parser`
→ safe verification, usage, and audit persistence.

Task 12H already placed readiness before Provider execution, so
`REVIEW_REQUIRED` and `NOT_READY` cannot reach the existing transport through
the production composition. The remaining gap was a self-contained execution
contract: request bounding, prompt pinning, budget-before-transport,
idempotency, deterministic fake failure modes, parser result hashes, and
execution reason mapping were distributed across Provider implementations and
Formal persistence rather than represented as one auditable admission unit.

The new `services/provider_execution.py` is that unit. Task 12I-A exercises it
only with `DeterministicFakeProviderTransport`; existing real Provider
transport and execution code are unchanged.

## Prompt, request, and admission contracts

Approved identities are fixed:

- V2: `term_alignment@v1`;
- production Formal: `formal_alignment@alignment-v1`.

No Prompt text or version changed, and no silent `main`, `latest`, or fallback
version exists.

Execution requires:

- readiness `READY` under `governed-provider-readiness@1.0.0`;
- qualification `QUALIFIED` under
  `governed-bilingual-evidence-qualification@1.1.0`;
- affirmative execution admission;
- privacy, provenance, and budget gates;
- the fixed fake Provider/model;
- bounded EN/ZH terms, contexts, evidence provenance, token/cost/timeout/retry
  budgets, idempotency key, and audit correlation ID.

Review, not-ready, policy mismatch, provider mismatch, Prompt mismatch, or any
failed hard gate blocks before transport. The request contains no gold,
aliases, required propositions, benchmark concept ID, complete source,
credential value, or authorization header.

## Fake transport and parsing

The fake transport supports valid output, malformed JSON, missing fields,
natural-language output, timeout, retryable failure, and non-retryable
failure. It records zero network calls and zero credential reads.

`term_alignment@v1` responses are checked against the existing
`TERM_ALIGNMENT_SCHEMA` required fields and validator. Formal
`alignment-v1` responses reuse `alignment_output_parser`, version
`alignment-parser-v1` / `alignment-output-v1`. Arbitrary natural language,
invalid JSON, or missing schema fields cannot produce success.

## Budget, retry, and idempotency

Token and cost bounds are evaluated before transport. Timeout and retry limits
are capped at 120 seconds and three retries. A non-retryable error receives one
attempt. A timeout or retryable error receives at most `retry_budget + 1`
attempts and then fails closed.

The dry-run ledger binds idempotency key to deterministic request hash. The
same key and payload returns `REUSED` without a second transport call; the same
key with a different payload returns
`PROVIDER_EXECUTION_IDEMPOTENCY_CONFLICT`. No fake request is treated as real
billable usage.

## Execution audit result

The result contains Provider/model and Prompt identities,
qualification/readiness IDs, idempotency/request/response hashes, parse
status, bounded fake usage, estimated cost, retry/request counts, stable reason
codes, audit correlation ID, and source/chunk provenance. It does not retain
full Prompt text, source text, raw response, or credentials. Existing Formal
database persistence remains unchanged; the V2 dry run emits sanitized
evaluation artifacts only.

## V2 zero-request dry run

The runner recomputed readiness from the frozen 25-row Task 12H matrix; the
number three is not embedded in runner logic.

- READY denominator: 3
- requests constructed: 3
- fake transport calls: 3
- fake execution successes: 3
- parse successes: 3
- review/not-ready blocked before request: 22
- review/not-ready executions: 0
- budget denied: 0
- idempotency conflicts: 0
- false executions: 0
- external network requests: 0
- real Provider requests: 0
- real credential reads: 0

This establishes execution-contract behavior only. It does not validate a
real Provider, Provider output quality, credential configuration, Prompt
quality, or Concept Alignment Card content.

## Upstream preservation and next boundary

Task 12H readiness remains 3 READY / 15 REVIEW_REQUIRED / 7 NOT_READY with
false-ready 0. Frozen retrieval, Chinese candidate, pairing, qualification,
corpus, gold, aliases, and Prompt content were not changed. The next boundary
is a separately authorized real-Provider execution qualification; Task 12I-A
does not begin that work.

## Verification

- Task 12I-A and 12D–12H targeted regression: 82 passed.
- Full pytest: 1466 passed, 56 warnings.
- `scripts/dev_check.py`: passed, including its own 1466-test run, migration,
  and backend API smoke test against an external temporary database.
- `scripts/check_release_safety.py`: passed.
- `git diff --check`: passed.
- Model/cache tracked: false.
- External API used: false.
- Real Provider requests: 0.
- Real credentials read: false.
- Accident database remained byte-for-byte and metadata identical; WAL and
  SHM remained absent.

Frozen Cross-Corpus V2 hashes:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Artifact hashes:

- `12IA-provider-execution-results.json`:
  `967f37c73a888b6319ca06b8f1430f6c76ceb9e241b780d115fdbfda5ab314b2`
- `12IA-provider-execution-matrix.csv`:
  `7f7258735b80bbfe8ab1a76ecaa1d02eab72aa1bcbd504241798c8a1291cf9df`
- `12IA-provider-execution-gate-audit.json`:
  `3c4fe91f5634ed7a3269ae9ef560b50f452b02fbc8ce44914c23babee15261c4`
