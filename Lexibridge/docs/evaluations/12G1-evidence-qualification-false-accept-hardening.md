# Task 12G.1 — Evidence Qualification False-Accept Safety Hardening

Status:

- Technical: `EVIDENCE_QUALIFICATION_SAFETY_CONTRACT_CLOSED`
- Quality: `EVIDENCE_QUALIFICATION_FALSE_ACCEPTS_CLOSED`
- Policy: `governed-bilingual-evidence-qualification@1.0.0` → `governed-bilingual-evidence-qualification@1.1.0`

## Executive conclusion

Task 12G.1 closes the observed automatic false-accept path without changing
retrieval, Chinese term identification, bilingual pair selection, pair scores,
the existing evidence threshold, Prompt, or Provider behavior. The production
qualifier now requires both hard upstream/governance eligibility and an
independent, bounded semantic-equivalence consistency check over the already
selected top-1 pair. It never substitutes top-2/top-3.

On frozen Cross-Corpus V2, false qualifications fell from 6 to 0. Of the 11
correct production top-1 pairs, 3 remain `QUALIFIED` and 8 conservatively become
`REVIEW_REQUIRED`; none are rejected and none lack a decision. This is not an
“all review” shortcut: three correct pairs clear the frozen safety contract.
`mass → 冲量` changes from `QUALIFIED` to `REVIEW_REQUIRED`.

No gold term, alias, required proposition, benchmark ID, translation mapping,
external API, or Provider is used by production policy.

## Exact root cause and original call chain

Production entrypoint and call chain:

`POST /api/evidence/bilingual`
→ `backend/app.py:retrieve_bilingual_evidence_api`
→ `backend/services/bilingual_evidence_workflow.py:build_bilingual_evidence_query`
→ `retrieve_bilingual_evidence`
→ retrieval / Chinese candidate identification
→ `rank_bilingual_pairs`
→ production-selected top-1
→ `bilingual_evidence_qualification.qualify_workflow_top1`
→ `qualify_bilingual_evidence`
→ `document_alignment_item_preparation.prepare_document_alignment_item`
→ Formal readiness.

Policy 1.0.0 checked provenance, source governance, top-1 rank, bi-encoder
score, pair margin, retrieval support, and extraction support. It had two exact
gaps:

1. It did not carry an explicit upstream execution/readiness state into the
   qualification input.
2. Its semantic evidence was correlated with the already selected pair. A high
   reranker/final score plus valid provenance could therefore qualify a
   related-but-non-equivalent term. Provenance proved where the wrong pair came
   from; it did not prove bilingual equivalence.

The aggregate score consequently accepted all six wrong top-1 pairs.

## Baseline six false qualifications

The categories below are evaluation labels. Gold is used only by the frozen V2
scorer to identify that a decision is false; it is never passed to the policy.

| Category | Count | Cases |
|---|---:|---|
| `UPSTREAM_STATE_GATE_BYPASS` | 3 | angular-acceleration retrieval miss, angular-momentum retrieval miss, electric-potential-difference identification miss |
| `PAIR_UNCERTAINTY_NOT_PROPAGATED` | 0 | — |
| `TERM_SCOPE_FALSE_ACCEPT` | 3 | mass → 冲量, conservation of mechanical energy → 机械能, capacitance → 功 |
| `SCORE_COMPONENT_DOMINANCE` | 0 | — |
| `POLICY_REASON_MAPPING_DEFECT` | 0 | — |
| `OTHER_FALSE_ACCEPT_DEFECT` | 0 | — |

The first group records the earliest frozen-evaluation attribution. Production
does not consume that gold-derived label. The new equivalence consistency gate
independently places all six selected pairs into review.

## Policy 1.1 contract

Policy 1.0.0 remains available as an immutable legacy evaluator and manifest;
the production default is 1.1.0. Public request data cannot select 1.0.0 or
override decision, threshold, reason, or upstream safety state.

Hard eligibility gates require:

- governed English/Chinese source status, language scope, and independent V2
  provenance;
- valid source, chunk, and evidence-span bindings;
- production-selected pair rank 1;
- successful pair/reranker execution and complete model metadata;
- ready production upstream state with no fatal reason.

Semantic consistency gates require:

- the existing bi-encoder and reranker components not to conflict;
- the existing pair margin to meet policy;
- a bounded consistency check of the selected pair to meet the frozen
  semantic-equivalence floor;
- no missing/unknown consistency result.

The consistency input is:

```text
term: <English term>
discipline: <discipline>
context: <bounded English context>
```

and:

```text
术语: <Chinese candidate>
学科: <discipline>
语境: <bounded Chinese context>
```

Only the fixed Task 12F.1 reranker
`BAAI/bge-reranker-v2-m3@79c481748842b7efa0a12db59915db91731f0b93`
is reused. Exactly one already-selected pair is checked. The check does not
rerank, retrieve, re-extract, replace, or expand the candidate pool.

## Threshold calibration and decision mapping

The existing evidence threshold remains `0.35`; existing pair and reranker
scores and weights are unchanged.

The new consistency floor is `4.0`. It was frozen before V2 using original,
benchmark-external physics fixtures:

- density ↔ 密度 versus density ↔ 体积;
- magnetic flux ↔ 磁通量 versus magnetic flux ↔ 磁感应强度;
- thermal conductivity ↔ 热导率 versus thermal conductivity ↔ 比热容.

This is a safety calibration, not V2 optimization. V2 was run once after the
policy and synthetic tests were frozen.

Decision mapping:

- `QUALIFIED`: every hard and semantic-consistency gate passes.
- `REVIEW_REQUIRED`: the pair is plausible but margin, component agreement,
  equivalence consistency, or scope certainty is insufficient.
- `REJECTED`: hard upstream, provenance, governance, representation, or
  execution eligibility fails.
- Unknown, missing, and exceptions never map to `QUALIFIED`.

Stable new reasons include:
`EVIDENCE_UPSTREAM_STATE_NOT_READY`, `EVIDENCE_PAIR_UNCERTAIN`,
`EVIDENCE_SCORE_COMPONENT_CONFLICT`, and `EVIDENCE_TERM_SCOPE_RISK`.

## V2 before / after

Upstream metrics are exactly unchanged:

| Metric | Before | After |
|---|---:|---:|
| Retrieval hit@1 | 0.7222 | 0.7222 |
| Retrieval hit@3 | 0.8333 | 0.8333 |
| Retrieval MRR | 0.7778 | 0.7778 |
| Chinese candidate top1 | 0.4667 | 0.4667 |
| Chinese candidate top3 | 0.8000 | 0.8000 |
| Chinese candidate MRR | 0.6378 | 0.6378 |
| Pair top1 | 0.7857 | 0.7857 |
| Pair top3 | 1.0000 | 1.0000 |
| Pair MRR | 0.8690 | 0.8690 |

Qualification:

| Population | Before Q/R/R | After Q/R/R |
|---|---:|---:|
| Eligible correct top-1 (11) | 11 / 0 / 0 | 3 / 8 / 0 |
| Outside eligible, executed (7) | 6 / 1 / 0 | 0 / 7 / 0 |

- Missing eligible decisions: 0 → 0
- False qualifications: 6 → 0
- Correct pairs sent to review: 0 → 8
- Correct pairs qualified: 11 → 3
- Provider-ready: 0 → 0

## Confusion and safety audit

- electric field / electric field strength: upstream-invalid selected pair
  remains review; it is not repaired or substituted.
- electric potential / electric potential energy: the correct selected pair is
  reviewed under the same consistency floor.
- angular velocity / angular acceleration: correct angular velocity remains
  qualified; the wrong angular-velocity selection for angular acceleration is
  reviewed.
- momentum / angular momentum: the ambiguous English item remains upstream and
  has no fabricated qualification; the wrong torque selection is reviewed.
- mass / weight: `mass → 冲量` moves from `QUALIFIED` to
  `REVIEW_REQUIRED` with `EVIDENCE_TERM_SCOPE_RISK`.

There are no false qualifications in these groups and qualification never
changes the selected pair.

## Formal readiness and next failure

Formal readiness already requires decision `QUALIFIED`; it therefore fails
closed for both `REVIEW_REQUIRED` and `REJECTED`. Policy 1.1 result IDs,
reasons, source/chunk hashes, model metadata, and score components are carried
into the audit payload.

The false-accept prerequisite for a future Provider-readiness audit is now met
in V2, but Provider readiness remains `PROVIDER_READINESS_NOT_EVALUATED` and
provider-ready remains 0. Task 12G.1 does not begin that work.

## Safety and isolation

- Existing qualification threshold changed: false
- Retrieval / identification / pairing changed: false
- Gold / aliases / required propositions used by production: false
- External API requests: 0
- Real Provider requests: 0
- Model or cache tracked: false
- V2 corpus/gold changed: false

V2 frozen hashes:

- English bundle: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Artifact hashes:

- `12G1-qualification-safety-results.json`: `f342e6c6fa0649b083636f248f54ae3624e47ff6ea75da57812500287caa7d54`
- `12G1-qualification-safety-matrix.csv`: `196de8623ee7ba73c612b37d6db266caa432b47c0e040fcf9633d177bec20cc9`
- `12G1-false-qualification-audit.json`: `ab277f9865ead1f3d1ea0b38d9c244b70a50d53cfcdf92e0bf83bb3be5557eb4`
- `12G1-qualification-policy-v11-manifest.json`: `48c1b14828185c1456458659b7f8d411127c9e12e929c0f70aac16cda6842c47`

## Validation

- Task 12G.1 + 12D/12E/12F/12F.1/12G targeted regression:
  `96 passed`.
- Full pytest: `1437 passed, 56 warnings`.
- Warning analysis: 50 pre-existing SQLAlchemy `Query.get()` legacy
  warnings, 1 pre-existing provider-registry SQLAlchemy legacy warning, and 5
  pre-existing SWIG/PDF parser deprecation warnings. Task 12G.1 adds no warning
  category or source.
- `scripts/dev_check.py`: passed, including its independent full pytest,
  migration, and backend API smoke.
- `scripts/check_release_safety.py`: passed.
- `git diff --check`: passed.
- Accident database SHA-256, size, mtime, and absent WAL/SHM: unchanged.
