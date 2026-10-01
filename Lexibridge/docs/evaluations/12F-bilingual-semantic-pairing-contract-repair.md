# Task 12F — Bilingual Semantic Pairing Contract Repair

## Executive conclusion

Technical status: `BILINGUAL_SEMANTIC_PAIRING_CONTRACT_CLOSED`

Quality status: `BILINGUAL_SEMANTIC_PAIRING_QUALITY_INSUFFICIENT`

Task 12F connected a bounded, deterministic English-to-Chinese semantic pair
ranker to the production bilingual-evidence workflow. It consumes the Chinese
candidate pool already produced by Task 12E and uses the qualified, offline
`intfloat/multilingual-e5-small` model at revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. It does not translate terms,
rerun retrieval, rerun Chinese extraction, or use benchmark gold.

The frozen V2 evaluation produced a pairing-eligible denominator of 14.
Correct-pair accuracy is 6/14 at top1 and 12/14 at top3, with MRR 0.6476.
This proves that real English-to-Chinese semantic pairing now executes, while
the 0.4286 top1 result remains insufficient for broad production claims.

## Exact root cause and call graph

Before Task 12F:

`POST /api/evidence/bilingual`
→ `build_bilingual_evidence_query`
→ `retrieve_bilingual_evidence`
→ cross-language retrieval
→ `identify_standard_chinese_terms`
→ extraction-score ordering / `select_primary_chinese_candidate`
→ Formal preparation.

There was no semantic pair comparison. The selection function only sorted
Chinese candidates by extraction score and stable identifiers. It did not
consume English definition context, Chinese definition context, or a
cross-language representation. Therefore correct lower-ranked Chinese
candidates could not be promoted by conceptual similarity.

After Task 12F:

`POST /api/evidence/bilingual`
→ `build_bilingual_evidence_query`
→ `retrieve_bilingual_evidence`
→ governed cross-language retrieval
→ governed Task 12E candidate pool
→ `rank_bilingual_pairs`
→ explicit `bilingual_pair_candidates`
→ Formal preparation consumes the top semantic pair only when the cross-corpus
fallback path is used
→ existing evidence qualification.

The implementation extends the existing workflow and does not create a second
retrieval, extraction, or card-generation pipeline.

## Pairing-eligible denominator and upstream attribution

All 25 V2 concepts remain in the matrix:

| Population | Count | Treatment |
|---|---:|---|
| All concepts | 25 | Original denominator retained |
| English uniquely matched / missing / ambiguous | 18 / 3 / 4 | Missing and ambiguous remain upstream failures |
| Retrieval-eligible | 18 | Task 12D denominator |
| Identification-eligible | 15 | Correct Chinese evidence appears in retrieval top3 |
| Pairing-eligible | 14 | Correct Chinese term exists in the bounded production candidate pool |

The three English misses, four English ambiguities, three retrieval misses, and
one Chinese identification miss are not counted as pairing failures. Only the
14 concepts whose correct Chinese candidate reached pairing input are scored
for pairing accuracy.

## Representation contract

English representation:

```text
query:
term: <English term>
discipline: <discipline>
context: <bounded English definition/context>
```

Chinese representation:

```text
passage:
term: <Chinese candidate>
discipline: <discipline>
context: <bounded Chinese definition/context>
```

Contexts are capped at 800 characters. The qualified adapter adds the E5
`query: ` and `passage: ` prefixes, returns L2-normalized 384-dimensional
vectors, and uses cosine-equivalent dot product. Results store representation
hashes, not full private contexts.

## Candidate pool contract

The pairer consumes Task 12E serialized candidates without re-extraction. The
pool is bounded to 20 candidates per English concept, which is no larger than
the existing production candidate limit. Each input retains candidate UID,
source/chunk provenance, definition snippet, extraction method, extraction
score/rank, and retrieval rank. A correct term absent from this pool is
classified as `UPSTREAM_CHINESE_TERM_IDENTIFICATION_MISSING`.

## Score components, ranking, and tie-break

The fixed, non-gold-tuned formula is:

```text
final =
  0.85 * semantic cosine
  + 0.08 * bounded extraction score
  + 0.05 * (1 / retrieval rank)
  + 0.02 * structural prior
```

Semantic similarity is the dominant signal. The structural prior uses generic
production extraction methods such as heading, definition subject, and list
item. Scores are similarity/ranking signals, not probabilities.

Stable ordering is:

1. final score descending;
2. semantic score descending;
3. extraction rank ascending;
4. retrieval rank ascending;
5. source UID ascending;
6. chunk UID ascending;
7. normalized Chinese term ascending.

Every result exposes all score components, backend/model metadata, ranks,
representation hashes, and source/chunk provenance.

## Fail-closed behavior

The pairer returns stable controlled failures for:

- `LOCAL_MULTILINGUAL_EMBEDDING_BACKEND_UNAVAILABLE`;
- `BILINGUAL_PAIRING_CANDIDATE_POOL_EMPTY`;
- `BILINGUAL_PAIRING_REPRESENTATION_INVALID`;
- `BILINGUAL_PAIRING_EXECUTION_FAILED`.

It does not fall back to hash embeddings, lexical exact match, automatic
Chinese top1 selection, DeepSeek, OpenAI, or another external API. The ordinary
request DTO cannot select a model path, backend, gold term, aliases, or required
propositions.

## Gold isolation

Gold and accepted aliases are read only by the evaluation scorer after
production retrieval, candidate identification, and pair ranking complete.
Neither the pair representation nor ranking receives a concept ID, gold
Chinese term, alias list, evidence label, required proposition, or manual
mapping. No benchmark-specific promotion or exclusion was added.

## Frozen V2 before and after

| Metric | Before 12F | After 12F |
|---|---:|---:|
| Retrieval hit@1 / hit@3 / MRR | 0.7222 / 0.8333 / 0.7778 | 0.7222 / 0.8333 / 0.7778 |
| Identification exact generated | 14/15 | 14/15 |
| Candidate top1 / top3 / MRR | 7/15 / 12/15 / 0.6378 | 7/15 / 12/15 / 0.6378 |
| Pair top1 | 0 | 6/14 (0.4286) |
| Pair top3 | 0 | 12/14 (0.8571) |
| Pair MRR | 0 | 0.6476 |
| No pair in pairing-eligible set | 14 | 0 |
| Evidence-qualified | 0 | 0 |
| Provider-ready | 0 | 0 |

Retrieval and identification metrics did not regress. Evidence qualification
and Provider readiness remain unchanged because their contracts and thresholds
were outside this task.

## Confusion groups

- Electric field / electric field strength: not pairing-eligible because the
  correct evidence was missed upstream; no pair was fabricated.
- Electric potential / electric potential energy: electric potential ranked
  first; margin over the strongest alternative was 0.000596.
- Angular velocity / angular acceleration: angular velocity moved from
  extraction rank 2 to pair rank 1; margin 0.003097.
- Momentum / angular momentum: English binding is upstream ambiguous; no pair
  was fabricated.
- Mass / weight: mass remained pair rank 5 with margin -0.030299. This is a
  genuine semantic scope/ranking miss, not an identification or retrieval miss.

The very small margins and the mass result indicate likely future need for a
concept-scope reranker, but Task 12F adds no hard-coded exclusion or promotion.

## Performance and budget

The offline V2 run scored 119 bounded candidate pairs. Model cache and weights
remained outside the repository. The runner records query embedding, passage
embedding, and aggregate pairing time without recording local cache paths.
Ordinary pytest uses deterministic fake backends and performs no real model
load or download.

## New earliest failure stage and next task

Across all 25 concepts, the largest current earliest-failure class is
`BILINGUAL_SEMANTIC_PAIRING_MISS` (8). Six concepts reach correct pair top1 and
then stop at `EVIDENCE_QUALIFICATION_MISSING`. Therefore pairing quality remains
an explicit limitation, while the next architectural layer can now be audited
as an evidence-qualification contract on the correctly paired subset. Such a
next task must preserve the existing evidence thresholds unless separately
authorized.

## Scope and safety

- Real English-to-Chinese semantic pairing implemented: yes.
- Gold/alias mapping added: false.
- External Provider/API used: false.
- Retrieval modified: false.
- Chinese term identification modified: false.
- Evidence threshold modified: false.
- Real Provider requests: 0.

## Verification

- Task 12F targeted suite: 38 passed.
- Related retrieval, bilingual workflow, Formal, API, vector/hybrid, and
  release-safety regressions: 89 passed.
- Full pytest: 1388 passed, 56 existing warnings.
- Warning sources: existing SQLAlchemy `Query.get()` legacy warnings and
  PDF/SWIG deprecation warnings; Task 12F introduced no warning category.
- `dev_check`: passed, including its full pytest, migration, and backend smoke.
- Standalone release safety: passed.
- `git diff --check`: passed.
- Model/cache tracked: false.
- Accident database before/final:
  SHA-256 `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`,
  size 1,015,808, mtime 1,785,496,597, WAL/SHM absent.

Artifact SHA-256:

- results JSON:
  `47404ee1d2b177e166d81b47f00510e3ea6bfa04633aa9e7209a3f085ac2b692`
- concept matrix CSV:
  `8993364fffbf0cd63afe12024f36fddea8114570dd493c3c3131f9af18e3baf9`
- confusion audit JSON:
  `aaadb73882cf62843876d584cd43f9c76af38947bc18d77ebcec51d805a58f02`
- backend runtime JSON:
  `39fd9c650ceda68e6868ff09e86bed9802b1bafe0025e5da6466eff9b452845b`

Frozen V2 hashes remained:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`
