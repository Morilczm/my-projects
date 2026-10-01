# Task 11N Frozen Benchmark Enumeration and Production Bootstrap Consistency

## Status

`FROZEN_EVALUATION_BOOTSTRAP_CONSISTENCY_CLOSED`

Real Provider requests during Task 11N: `0`.

## Root cause

The 11L path begins at
`scripts/evaluations/bilingual_knowledge_quality/runner.py:
scan_formal_provider_readiness`. It iterates the caller-supplied frozen concept
order and invokes a supplied `prepare_item(concept_id)` callback. The API did
not enumerate or bind production extractor candidates itself. The 11L
diagnostic caller therefore constructed 25 Formal preparation inputs around
benchmark English terms. Production Chinese candidate generation, retrieval,
and the Formal sufficiency predicate were real, but the English item identity
was benchmark supplied.

The R4 path began at production upload/ingestion and
`bootstrap_document_alignment_workflow_items`, using
`extract_terms_from_text`. It then iterated only the resulting workflow items
and bound them to benchmark rows by stripped, case-insensitive exact English
term equality. No aliases, stemming, symbol normalization, morphology, or
accepted Chinese aliases participated. Only `physics-23` through `physics-25`
matched. The other 22 rows disappeared at enumeration/binding, before retrieval
or Formal preparation.

Thus the supported single root cause is:

> R4 treated production candidate output as the benchmark enumeration source.
> Unextracted concepts disappeared from the evaluation population, upgrading
> item-level candidate extraction failures into a global bootstrap blocker.

The two paths were independent item builders. In 11L the benchmark English term
entered the retrieval query and Formal input. No Provider request occurred. In
R4 only system candidates could become execution inputs, but missing benchmark
rows were not represented.

## Sanitized original comparison

| Concepts | Benchmark enumerated | Production candidate found | Binding | Retrieval | Formal preparation | Readiness | Disappearance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| physics-01–physics-20 | 11L yes / R4 envelope yes | no exact item | missing | R4 no | R4 no | upstream_not_ready | enumeration/binding |
| physics-21–physics-22 | 11L yes / R4 envelope yes | no exact item | missing | R4 no | R4 no | upstream_not_ready | enumeration/binding |
| physics-23–physics-25 | yes | yes | matched | attempted | attempted | system predicate result | none |

The full R4 missing set was `physics-01` through `physics-22`. Full source text
was neither recorded nor included in this comparison.

The fresh unified provider-free execution produced:

- benchmark coverage: `25/25`
- matched: `3`
- missing: `22`
- ambiguous: `0`
- provider ready: `3`
- provider not ready: `22`
- Provider requests: `0`

## Closed contract

The evaluation-only runner now separates:

1. `FrozenBenchmarkIdentity`: concept ID, frozen order, binding verification,
   scorer identity, and denominator only.
2. `ProductionCandidateBindingInput`: system candidate ID, term, and opaque
   system payload emitted by production extraction.
3. `FrozenEvaluationBootstrapRow`: the association and execution result.

`build_frozen_evaluation_bootstrap` always emits one row per benchmark identity
in frozen order. Exact binding returns `matched`, `missing`, or `ambiguous`.
Only a unique matched `ProductionCandidateBindingInput` reaches retrieval and
Formal preparation. The callback receives the production candidate object, not
the benchmark identity or gold object.

Missing and ambiguous bindings become:

- `execution_status=upstream_not_ready`
- `provider_called=false`
- `primary_attribution=CANDIDATE_EXTRACTION_DEFECT`
- `included_in_denominator=true`

They do not stop later rows. The deterministic selector accepts only the
bootstrap rows and chooses the first `provider_ready=true` row. The batch
continuation consumes the same rows, so readiness and execution share one
25-row universe. Scoring may read gold only after execution results are frozen.

## Test-first and safety evidence

- RED: `5 failed, 2 passed`; failures were the missing unified enumeration,
  binding, selector, and continuation APIs.
- GREEN: `7 passed`.
- Formal, policy, bridge, readiness, explanation, candidate, retrieval,
  bootstrap, and orchestration regression: `101 passed`.
- Tests prove 3 production matches still yield 25 rows, 22 item-level failures,
  ambiguous fail-closed behavior, first-ready selection, preflight reuse, and
  no benchmark binding field in the system execution payload.
- Real Provider requests: `0`.
- Ordinary production extraction, retrieval, Provider defaults, HTTP boundary,
  Prompt, transport, and Formal state machine are unchanged.
- Accident database SHA-256, size, mtime, and absent WAL/SHM state are
  unchanged.
- Release safety: passed.
