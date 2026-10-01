# Task 12H — Provider Readiness Contract Evaluation and Formal Gate Wiring

## Executive conclusion

Status: `PROVIDER_READINESS_CONTRACT_CLOSED`.

Quality status: `PROVIDER_READINESS_BASELINE_ESTABLISHED`.

The Formal workflow now evaluates a deterministic, local-only Provider
readiness contract before Provider execution. The gate consumes the production
qualification decision and requires policy 1.1.0, complete bounded evidence,
provenance, production top1 pair metadata, source governance, privacy,
approved prompt identity, allowed Provider configuration, bounded budgets, and
audit/idempotency context. It performs no live probe, reads no credential
value, and makes no Provider request.

## Root cause and previous call chain

`PROVIDER_READINESS_NOT_EVALUATED` was emitted by
`scripts/evaluations/bilingual_evidence_qualification_safety_v2.py`, not by a
production readiness decision. Production preparation blocked non-qualified
new pair candidates, but `PreparedFormalItemVerificationInput` only validated
qualification when a qualification result ID happened to be present. The
subsequent provider governance/preflight path did not consume policy 1.1.0 as
an unconditional execution-admission input. The old preflight also checks
credential presence via environment lookup, which is intentionally not used by
the new readiness evaluator.

Before:

`qualification (conditionally present) → draft creation → provider policy → provider preflight → provider execution`

After:

`qualification 1.1.0 → protected draft/approved-card handling → governed readiness evaluation → READY only → provider policy/preflight/execution`

The production composition wires
`evaluate_formal_prepared_readiness` into the existing verification adapter;
no parallel Formal workflow or Provider transport was introduced.

The production call chain is:

- `POST /api/document-alignment-runs` in
  `routes/document_alignment_workflow_routes.py` calls
  `start_document_alignment_workflow` and persists the server-owned Provider
  and prompt selection.
- `run_formal_worker_once` in `backend/app.py` composes
  `build_document_alignment_processing_dependencies`.
- `prepare_document_alignment_item` returns
  `PreparedFormalItemVerificationInput`, including the qualification result.
- `execute_document_alignment_item_verification` safely creates/reuses a draft
  reference, then calls `evaluate_formal_prepared_readiness`.
- Only an admitted result proceeds to
  `validate_alignment_verification_input`,
  `provider_governance.evaluate_provider_request`,
  `provider_preflight.run_provider_preflight`, and finally the existing
  Provider adapter.

The readiness input/output are in-memory DTOs. Existing workflow execution,
preflight, verification, usage, and audit persistence objects remain
unchanged; no schema or migration was added.

## Input and output contracts

The pure input contract includes qualification identity/decision/reasons,
bounded EN/ZH evidence references, selected top1 pair metadata, provider and
prompt identities, privacy/provenance/source results, bounded token/cost/retry/
timeout budgets, and idempotency/audit context. It excludes gold, aliases,
required propositions, benchmark IDs, credential values, headers, and complete
source text.

Output decisions are `READY`, `REVIEW_REQUIRED`, and `NOT_READY`. Every
non-ready result has stable reason codes. The output records policy and prompt
versions, per-gate results, a deterministic readiness ID, and an explicit
execution-admission Boolean. Its score is a gate-completeness score, not a
probability.

## Policies, prompt, privacy, provenance, and budget

- Qualification: `governed-bilingual-evidence-qualification@1.1.0`.
- Readiness: `governed-provider-readiness@1.0.0`.
- V2 prompt registry identity: `term_alignment@v1`.
- Production Formal prompt identity remains the approved existing
  `alignment-v1`; prompt text was not changed.
- V2 uses `SYNTHETIC`; production local Formal preflight uses the existing
  `LOCAL_ONLY_PRIVATE` classification and admits it only for local transport.
- Both evidence sides and governed references are mandatory.
- Token, cost, retry, and timeout values must be positive/bounded as
  applicable; ordinary API input cannot override the decision or disable a
  gate.
- Provider configuration is supplied as sanitized server-owned metadata.
  Credential values and environment secret presence are not inspected.

## V2 denominators and decisions

The frozen 25-row matrix was retained. Qualification executed for 18 rows:
3 `QUALIFIED`, 15 `REVIEW_REQUIRED`, and 0 `REJECTED`. Seven upstream-excluded
rows have no qualification decision.

Provider-readiness eligibility is 3/25: exactly the three qualification-
qualified rows with complete Formal inputs. Results are:

- `READY`: 3
- `REVIEW_REQUIRED`: 15
- `NOT_READY`: 7
- missing readiness decisions: 0
- qualification-review mapped to READY: 0
- false-ready outside qualification approval: 0

All READY rows pass privacy, provenance, prompt, provider configuration,
budget, and audit gates. No top2/top3 pair substitution is performed.

## Upstream preservation

Frozen before/after metrics are unchanged:

- retrieval hit@1 / hit@3 / MRR: 0.7222 / 0.8333 / 0.7778
- Chinese candidate top1 / top3 / MRR: 0.4667 / 0.8000 / 0.6378
- bilingual pair top1 / top3 / MRR: 0.7857 / 1.0000 / 0.8690
- evidence false qualifications: 0

## Security and API boundary

Local readiness does not call provider health, model-list, completion,
translation, or embedding endpoints. It never reads
`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, or any credential value. Tests inject a
fake local configuration. Public route source contains no readiness-decision
field or gate-disable control. Existing Provider transport and Prompt content
are unchanged.

## Dominant next failure and limits

The readiness contract is closed, and 3 items are locally READY. This does not
mean a real Provider was called or a Concept Alignment Card was generated.
The next unevaluated boundary is controlled Provider execution admission with
real credentials and privacy authorization; that work is explicitly outside
Task 12H. The 15 review outcomes remain governed human-review work, not
Provider-ready inputs.

Artifacts are sanitized and contain opaque IDs and bounded gate metadata only.

## Validation and frozen hashes

- Task 12H targeted and related regressions: 95 passed.
- Full pytest: 1449 passed, 56 warnings.
- `dev_check`: passed, including its own 1449-test run and backend smoke.
- release safety: passed.
- real Provider requests / external API requests / real credential reads:
  0 / 0 / 0.
- V2 English / Chinese / gold / manifest:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`,
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`,
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`,
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`.
- Artifact SHA-256:
  results `3d14d7ed26bd09edb8f60196c2414e092ed8ddf8f569571d4cfd311cebed4023`;
  matrix `9889955584483ceb0720fa3489b9bbc29b30c2e0c757a6dc746f2871019ba450`;
  gate audit `c1568b41f5160d9999f26e61aaeeedbc17fed340f50ea70805f9bf7b732fa2b6`;
  policy manifest `5cf75002ae2965d607bc562f8675d0ab594990637117401587624de956c77f77`.
