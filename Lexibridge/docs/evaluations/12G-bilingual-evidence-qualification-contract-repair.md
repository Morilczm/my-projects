# Task 12G — Bilingual Evidence Qualification Contract Repair

## Executive conclusion

Technical status: `BILINGUAL_EVIDENCE_QUALIFICATION_CONTRACT_CLOSED`.

Quality status: `BILINGUAL_EVIDENCE_QUALIFICATION_QUALITY_INSUFFICIENT`.

The production-selected top-1 bilingual pair now enters a deterministic,
provider-free qualification policy with governed English and Chinese
provenance. All 11 evidence-qualification-eligible V2 concepts receive a
decision and are `QUALIFIED`; none are missing a decision. The policy also
qualifies six production top-1 pairs that the scorer identifies as upstream
retrieval, identification, or pairing errors. Qualification deliberately does
not replace those pairs and cannot use gold to correct them. That false-positive
result is why quality is insufficient even though the contract is closed.

No existing evidence threshold, retrieval behavior, Chinese identification,
pair score, reranker weight, Prompt, or Provider behavior changed.

## Original call chain and exact root cause

Production entry:

`POST /api/evidence/bilingual`
→ `backend/app.py::retrieve_bilingual_evidence_api`
→ `backend/services/bilingual_evidence_workflow.py::build_bilingual_evidence_query`
→ `retrieve_bilingual_evidence`
→ cross-language retrieval
→ Chinese term identification
→ `bilingual_semantic_pairing.rank_bilingual_pairs`
→ optional bounded BGE reranking
→ `BilingualEvidenceResult`
→ `document_alignment_item_preparation.prepare_document_alignment_item`
→ `PreparedFormalItemVerificationInput`
→ Formal verification/provider readiness.

Before Task 12G, the top-1 pair existed in
`BilingualEvidenceResult.bilingual_pair_candidates`. Formal preparation used
its candidate UID to select a Chinese term, but there was no pair-aware
qualification input, policy execution, decision, stable reason mapping, or
qualification identity in the Formal input. Formal preparation only checked
that English and Chinese evidence-reference sets were non-empty.
`EVIDENCE_QUALIFICATION_MISSING` was therefore emitted by the V2 evaluation
runner as a placeholder; no production qualification decision had run.

The exact root cause was a missing adapter and policy contract between the
production-selected pair and Formal readiness, not a threshold rejection.

## Input and output contract

`backend/services/bilingual_evidence_qualification.py` consumes:

- the selected English candidate, bounded context, source/chunk/span, language,
  status, and quality;
- the selected Chinese candidate, bounded definition context,
  source/chunk/span, retrieval and extraction rank/score, language, status, and
  quality;
- top-1 pair rank, bi-encoder score, reranker score, final score, top-1/top-2
  margin, fixed backend/model revisions, representation hashes, and pair
  provenance.

It never receives the gold Chinese term, aliases, required propositions,
benchmark concept ID, evidence labels, mappings, or Provider output.

The result contains `QUALIFIED`, `REVIEW_REQUIRED`, or `REJECTED`, a
non-probabilistic qualification score, auditable components and thresholds,
stable reason/risk codes, dual provenance hashes, pair metadata, deterministic
result ID, and policy identity.

## Provenance and source governance

Hard gates validate:

- English and Chinese source/chunk/span completeness;
- actual English-term binding to the English span;
- actual Chinese-candidate binding to the Chinese span;
- active/governed source and acceptable quality state;
- English/Chinese language scope;
- production pair rank 1;
- bounded context presence.

V2 requires physically independent `en` and `zh` source UIDs. Production
retains the existing governed bilingual fallback: a same-source `mixed`
document is permitted only when both sides carry the existing
`bilingual_reference` role. Withdrawn, rejected, wrong-language, or
provenance-free inputs fail closed.

## Policy and thresholds

Policy ID/version:
`governed-bilingual-evidence-qualification@1.0.0`.

The existing production evidence floor remains `0.35` and was not changed.
Task 12G adds a separate conservative policy, fixed with benchmark-external
synthetic tests before the one-shot V2 run:

- evidence score floor: `0.35`;
- pair semantic floor: `0.35`;
- top-1/top-2 margin review floor: `0.05`;
- aggregate qualification floor: `0.65`;
- minimum bounded context: `12` characters.

Score weights:

- English span validity `0.10`;
- Chinese span validity `0.10`;
- provenance completeness `0.15`;
- source governance `0.15`;
- bi-encoder semantic score `0.25`;
- bounded margin support `0.10`;
- retrieval-rank support `0.075`;
- extraction score `0.075`.

A hard governance/semantic failure is `REJECTED`. A valid input below only the
margin gate is `REVIEW_REQUIRED`. All gates and aggregate score passing is
`QUALIFIED`. Unknown or execution failures never become qualified. The score is
not a probability.

## Stable fail-closed reasons

The policy implements:

- `EVIDENCE_QUALIFICATION_INPUT_INCOMPLETE`;
- `EVIDENCE_PROVENANCE_INCOMPLETE`;
- `EVIDENCE_SOURCE_NOT_ELIGIBLE`;
- `EVIDENCE_LANGUAGE_SCOPE_INVALID`;
- `EVIDENCE_PAIR_NOT_TOP1`;
- `EVIDENCE_PAIR_SCORE_INSUFFICIENT`;
- `EVIDENCE_PAIR_MARGIN_INSUFFICIENT`;
- `EVIDENCE_CONTEXT_INSUFFICIENT`;
- `EVIDENCE_QUALIFICATION_POLICY_UNAVAILABLE`;
- `EVIDENCE_QUALIFICATION_EXECUTION_FAILED`.

It does not fall back to a Provider, gold, aliases, a different pair, lexical
matching, or an unknown-as-qualified state.

## Formal readiness wiring

`BilingualEvidenceResult` now carries a sanitized qualification result. Formal
item preparation blocks a semantic-pair path unless the decision is
`QUALIFIED`, returning
`DOCUMENT_ALIGNMENT_EVIDENCE_QUALIFICATION_REQUIRED` with stable policy
reasons. A qualified result ID, decision, and policy version are carried by
`PreparedFormalItemVerificationInput`, included in the verification input and
its deterministic fingerprint. Ordinary API callers cannot submit a decision,
score, or threshold override.

This task does not invoke or repair Provider readiness. Provider-ready remains
zero.

## V2 denominators and before/after

The frozen population remains:

- all concepts: 25;
- English matched/missing/ambiguous: 18/3/4;
- retrieval eligible: 18;
- identification eligible: 15;
- pairing eligible: 14;
- evidence-qualification eligible: 11, recalculated as correct
  production-selected top-1 pairs with complete dual provenance.

Upstream metrics are unchanged:

- retrieval hit@1/hit@3/MRR:
  `0.7222 / 0.8333 / 0.7778`;
- Chinese candidate top1/top3/MRR:
  `0.4667 / 0.8000 / 0.6378`;
- pair top1/top3/MRR:
  `0.7857 / 1.0000 / 0.8690`.

Qualification changed from no production decision to:

- eligible: 11;
- qualified: 11;
- review-required: 0;
- rejected: 0;
- no-decision: 0;
- eligible qualification rate: 1.0000;
- pair margin min/median/max:
  `0.060378 / 0.629762 / 2.013095`;
- evidence-qualified: 11;
- provider-ready: 0.

## False-qualification and confusion audit

The scorer reports six false qualifications outside the eligible denominator.
They retain their earliest upstream attribution and are not counted as
qualification failures:

- three production top-1 pairing misses;
- additional incorrect top-1 selections caused by upstream retrieval or
  identification misses.

This is a credible safety signal: structural provenance plus the existing pair
scores do not independently prove bilingual concept correctness. Gold cannot
be used by production to suppress these cases, and qualification must not
replace the selected pair.

Selected confusion groups:

- electric field / electric field strength: upstream retrieval miss; selected
  `力`; margin `0.035466`; `REVIEW_REQUIRED`; not falsely qualified;
- electric potential / electric potential energy: selected `电势`; margin
  `0.140919`; `QUALIFIED`;
- angular velocity / angular acceleration: selected `角速度`; margin
  `1.013022`; `QUALIFIED`;
- momentum / angular momentum: upstream English binding ambiguous; no
  qualification decision;
- mass / weight: selected `冲量`; upstream pairing miss; margin `0.266320`;
  incorrectly `QUALIFIED`, retained as a false-qualification finding.

## Gold isolation and safety

- corpus, gold, aliases, and required propositions were unchanged;
- policy code does not read them;
- V2 gold is read only by the scorer to determine eligibility and false
  qualifications;
- external API requests: 0;
- real Provider requests: 0;
- model and cache files remain repository-external and untracked;
- the accident database remains byte-for-byte unchanged.

## Validation

RED was the missing qualification module/runner import. The initial five-file
GREEN set passed 14 tests. The required Task 12G plus 12D/12E/12F regression
set passed 46 tests. Related workflow, Formal preparation, verification,
retrieval, draft, and API tests passed after preserving the existing
`selected_chinese_candidate` behavior.

Final validation:

- required targeted suite: 47 passed;
- related workflow/Formal/API suite: 100 passed;
- full pytest: 1418 passed, 56 existing warnings;
- `dev_check`: passed, including its independent 1418-test run, migration, and
  backend smoke check;
- release safety: passed;
- `git diff --check`: passed.

The 56 warnings remain the existing SQLAlchemy `Query.get` legacy warnings and
PDF/SWIG deprecation warnings; Task 12G introduced no warning category.

Artifact SHA-256:

- results:
  `d3d91ed2ee9d48ad784d1e136a2b0d3b928e666dc8881072cfcbd777f1daef8f`;
- matrix:
  `995083557eace61c2fc8bc155436378ab8bde4a04c5524f144eed02b226e2b73`;
- confusion audit:
  `29e8dfeaac1cc5cb326b2df2a15d7d3ca12de282fbd105fdcb6a87bed0fac4ea`;
- policy manifest:
  `4031a09d9d1dd8f11311562024e24f4db11880ba0cbe065cfc035589e5024481`.

Frozen V2 hashes remain:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`;
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`;
- gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`;
- manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`.

Accident database before/final:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`;
- size: `1015808`;
- mtime: `1785496597`;
- WAL/SHM: absent/absent.

## Next step

For the 11 correctly selected and qualified pairs, the next mechanical gate is
Provider readiness. However, the six false qualifications mean it is not safe
to interpret `QUALIFIED` as semantic correctness across the full population.
Before enabling real Provider execution, the project should define how Formal
readiness consumes this qualified subset while retaining upstream failure
attribution and explicitly gating known incorrect top-1 pairs. This task does
not begin that work.
