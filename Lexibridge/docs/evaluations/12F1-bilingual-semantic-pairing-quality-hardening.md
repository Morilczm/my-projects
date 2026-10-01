# Task 12F.1 — Bilingual Semantic Pairing Quality Hardening

## Executive conclusion

Technical status: `BILINGUAL_RERANKING_CONTRACT_CLOSED`

Quality status: `BILINGUAL_RERANKING_QUALITY_IMPROVED`

Task 12F.1 added a bounded, offline cross-encoder reranking stage over the
unchanged Task 12E/12F candidate pool. Pair top1 improved from 6/14 (0.4286)
to 11/14 (0.7857), top3 improved from 12/14 (0.8571) to 14/14 (1.0000), and
MRR improved from 0.6476 to 0.8690. Retrieval and Chinese candidate
identification metrics did not change.

The dominant earliest failure moved from `BILINGUAL_SEMANTIC_PAIRING_MISS`
to `EVIDENCE_QUALIFICATION_MISSING`: pairing misses fell from 8 to 3, while
11 correctly top-ranked pairs now reach the existing evidence qualification
boundary.

## Pre-change pairing miss audit

All 14 pairing-eligible concepts were audited with their English context,
bounded Chinese pool, extraction/retrieval ranks, bi-encoder semantic score,
auxiliary priors, final score, correct rank, strongest error, and margin.

The eight Task 12F misses separated into:

| Category | Count | Concepts |
|---|---:|---|
| `TERM_SCOPE_CONFUSION` | 5 | displacement, gravitational potential energy, work, torque, potential difference |
| `AUXILIARY_PRIOR_DOMINANCE` | 3 | mass, mechanical energy, conservation of mechanical energy |
| `CONTEXT_DILUTION` | 0 | — |
| `REPRESENTATION_TRUNCATION` | 0 | — |
| `NEAR_SYNONYM_CONFUSION` | 0 | — |
| `RANK_TIE_DEFECT` | 0 | — |
| `OTHER_PAIRING_RANK_DEFECT` | 0 | — |

For the three prior-dominance cases, the correct candidate's original
bi-encoder score was already higher than the leading wrong candidate, but the
retrieval/extraction priors moved it below the wrong item. The other five
misses were genuine near-scope semantic inversions, not score ties.

No candidate absent from the bounded pool was classified as a pairing miss.

## Reranker qualification

Qualified backend:

- model: `BAAI/bge-reranker-v2-m3`
- exact revision: `79c481748842b7efa0a12db59915db91731f0b93`
- license: Apache-2.0
- architecture: `XLMRobertaForSequenceClassification`
- model size: approximately 0.6B parameters / 2.29 GB repository bundle
- runtime: Transformers 4.48.3 + PyTorch 2.5.1 CPU
- remote custom code: disabled
- fixed-revision offline loading: verified
- repository-external cache: verified

The official model configuration declares 24 XLM-R layers, hidden size 1024,
and 8194 positional embeddings. Production deliberately applies a smaller
controlled 512-token pair budget. The official model card describes this model
as a multilingual query/passage reranker and provides the standard
sequence-classification loading path without remote custom code.

Model files were prepared through one explicit management operation. Ordinary
application startup and pytest do not download them. The fixed snapshot loaded
successfully with `local_files_only=True`, `trust_remote_code=False`, and
offline environment controls.

Controlled file hashes:

- `config.json`:
  `13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a`
- `model.safetensors`:
  `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`

## Two-stage production contract

Stage one is unchanged:

`multilingual-e5-small`
→ existing bounded Task 12E candidate pool
→ Task 12F bi-encoder and auxiliary component scores.

Stage two:

English term + discipline + bounded English definition
+
Chinese candidate + discipline + bounded Chinese definition
→ fixed BGE cross-encoder raw relevance score
→ deterministic reranking of the complete existing pool.

The reranker does not call retrieval, identify Chinese terms, expand the pool,
or consume only the original top3. The mass candidate was extraction rank 5
and was still scored by the cross-encoder.

## Input and privacy contract

English input contains only:

- canonical English term;
- discipline;
- bounded English definition/context.

Chinese input contains only:

- existing Chinese candidate;
- discipline;
- bounded Chinese evidence context.

Character context bounds from Task 12F remain 800 per side. Token governance is
independently bounded at 192 English tokens and 316 Chinese tokens, with a
512-token pair ceiling including model special tokens. Artifacts store
representation hashes and bounded candidate labels, not complete private
contexts.

Gold Chinese terms, aliases, benchmark concept IDs, required propositions, and
gold evidence labels are not supplied to the production reranker.

## Score and deterministic ranking

The frozen, non-gold-tuned formula is:

```text
final score =
  1.000 * raw cross-encoder relevance
  + 0.050 * original bi-encoder cosine
  + 0.010 * bounded extraction prior
  + 0.005 * retrieval-rank prior
  + 0.005 * structural prior
```

The raw cross-encoder score is the dominant signal. It is not labelled or
interpreted as a probability.

Stable ordering:

1. final score descending;
2. cross-encoder score descending;
3. extraction rank ascending;
4. retrieval rank ascending;
5. source UID ascending;
6. chunk UID ascending;
7. normalized Chinese term ascending.

All components are retained in the pair result for audit.

## Fail-closed behavior

Stable reasons:

- `BILINGUAL_RERANKER_BACKEND_UNAVAILABLE`
- `BILINGUAL_RERANKER_REVISION_MISMATCH`
- `BILINGUAL_RERANKER_INPUT_INVALID`
- `BILINGUAL_RERANKER_EXECUTION_FAILED`

There is no hash, lexical, original-top1, external API, or Provider fallback.
The request DTO cannot choose a reranker backend, path, model, gold term, or
alias mapping.

## Offline smoke and bounded runtime

An original, non-benchmark rotational-inertia smoke input was evaluated
offline. The corresponding Chinese passage scored 5.6589, above unrelated
electric-current (-3.3558) and velocity (-1.3129) passages.

The frozen V2 run scored 119 pairs in 7.83 seconds of cross-encoder execution
on CPU. This is suitable for the current bounded evaluation and small governed
pool, but not evidence of large-scale throughput.

## Frozen V2 before and after

| Metric | Before | After |
|---|---:|---:|
| Pairing eligible | 14 | 14 |
| Pair top1 | 6/14 (0.4286) | 11/14 (0.7857) |
| Pair top3 | 12/14 (0.8571) | 14/14 (1.0000) |
| Pair MRR | 0.6476 | 0.8690 |
| No pair | 0 | 0 |
| Pairing miss | 8 | 3 |
| Correct-pair evidence qualification missing | 6 | 11 |
| Retrieval hit@1 / hit@3 / MRR | 0.7222 / 0.8333 / 0.7778 | 0.7222 / 0.8333 / 0.7778 |
| Candidate top1 / top3 / MRR | 0.4667 / 0.8000 / 0.6378 | 0.4667 / 0.8000 / 0.6378 |
| Evidence-qualified | 0 | 0 |
| Provider-ready | 0 | 0 |

All-25 remains 25, with English matched/missing/ambiguous 18/3/4,
retrieval-eligible 18, identification-eligible 15, and pairing-eligible 14.

## Confusion groups

- Electric field / electric field strength: still upstream retrieval-missed;
  no pair was fabricated.
- Electric potential / electric potential energy: electric potential remains
  correct rank 1; margin increased to 0.140919.
- Angular velocity / angular acceleration: angular velocity remains correct
  rank 1; margin increased to 1.013022.
- Momentum / angular momentum: remains upstream English-binding ambiguous.
- Mass / weight: mass improved from rank 5 to rank 3 but remains a pairing
  miss; the cross-encoder reduced but did not eliminate broader mechanics
  context confusion.

The three remaining pairing misses are mass (rank 3), conservation of
mechanical energy (rank 2), and capacitance (rank 3). No hard-coded promotion
or exclusion was introduced.

## Next task

The dominant earliest failure is now
`EVIDENCE_QUALIFICATION_MISSING` (11), compared with three remaining pairing
misses. Under the Task 12F.1 acceptance rule, the next task may proceed to a
strict evidence-qualification contract audit/repair. It must not silently
raise or bypass existing evidence thresholds.

## Scope and safety

- Retrieval modified: false.
- Chinese term identification modified: false.
- English extraction modified: false.
- Evidence threshold modified: false.
- Prompt/Provider modified: false.
- Gold/alias mapping added: false.
- External API requests during runtime/evaluation: 0.
- Real Provider requests: 0.
- Model/cache tracked in Git: false.

## Artifact hashes

- results JSON:
  `5ab677f314ad91c22c15521ffb9e88e818ef5b5c563b3aa142dd8d84b042a5e0`
- matrix CSV:
  `a498a98659bb77354b4dd08fd53d965dc29640815216868fbfe0537a2697273f`
- confusion audit JSON:
  `856680ab20e1171d28fd8549f0c3c984479452cda0eb44a884128ba87377c744`
- backend manifest JSON:
  `3d1efc3a0b821eca5829754234df9e552698646fcd9c027e32bb0578c3cf11c3`

Frozen V2 hashes remain:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

## Verification

- Task 12F.1 and combined 12D/12E/12F targeted regressions: 58 passed.
- Related bilingual workflow, Formal, retrieval, vector/hybrid, API, and
  release regressions: 89 passed.
- Full pytest: 1401 passed, 56 existing warnings.
- Warning sources remain existing SQLAlchemy `Query.get()` legacy warnings and
  PDF/SWIG deprecation warnings; no Task 12F.1 warning category was added.
- `dev_check`: passed, including its full pytest, migration, and backend smoke.
- Standalone release safety: passed.
- `git diff --check`: passed.
- Model/cache tracked: false.
- External API requests during offline runtime/evaluation: 0.
- Real Provider requests: 0.
- Accident database before/final:
  SHA-256 `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`,
  size 1,015,808, mtime 1,785,496,597, WAL/SHM absent.
