# Task 12D — Cross-Language Retrieval Contract Repair

Technical status: `CROSS_LANGUAGE_RETRIEVAL_CONTRACT_CLOSED`

Quality status: `CROSS_LANGUAGE_RETRIEVAL_QUALITY_BASELINE_ESTABLISHED`

## Executive conclusion

The production bilingual-evidence workflow now has an explicit, bounded
English-to-Chinese semantic retrieval path. An English technical term,
discipline, and bounded English context are represented by the qualified local
`intfloat/multilingual-e5-small` model and compared with governed Chinese-only
`KnowledgeChunk` passages. The real offline Cross-Corpus V2 evaluation improved
retrieval-eligible hit@1/hit@3/MRR from `0/0/0` to
`0.7222/0.8333/0.7778`.

English-only queries therefore can retrieve independent monolingual Chinese
chunks without a shared complete technical-term string. No gold term, alias,
concept ID, translation mapping, external embedding API, DeepSeek call, or
Provider call was used.

The next earliest dominant failure is
`CHINESE_TERM_IDENTIFICATION_MISSING`: 15 of the 18 eligible concepts retrieve
a gold-bearing Chinese chunk in top 3, but production still has no independent
mechanism that identifies the standard Chinese term from that evidence.
Task 12D does not implement that downstream capability.

## Exact original failure chain

Before this change, `POST /api/evidence/bilingual` built a query containing
English and optional Chinese strings. `retrieve_bilingual_evidence` called
`retrieve_chinese_evidence` only when a Chinese term was already known; without
one it returned no Chinese evidence. The existing evidence search was lexical,
and the vector path retained a lexical-overlap gate. Consequently a pure
English term could not score a pure Chinese chunk. The qualified Task 12D.0
adapter existed but was not imported by the production workflow, and the
query did not carry English definition/context or discipline.

The defect was the missing production cross-language representation and
retrieval contract, not missing Chinese corpus content.

## Production call graph

Before:

```text
POST /api/evidence/bilingual
→ app.retrieve_bilingual_evidence_api
→ bilingual_evidence_workflow.build_bilingual_evidence_query
→ bilingual_evidence_workflow.retrieve_bilingual_evidence
→ retrieve_chinese_evidence (only if chinese_term exists)
→ evidence_retrieval.search_evidence
→ lexical phrase/token scoring
→ BilingualEvidenceResult
```

After:

```text
POST /api/evidence/bilingual
→ app.retrieve_bilingual_evidence_api
→ build_bilingual_evidence_query
  input: request JSON
  output: bounded internal query dictionary
→ retrieve_bilingual_evidence
→ retrieve_cross_language_chinese_evidence (when chinese_term is absent)
→ governed KnowledgeChunk/KnowledgeSource query
→ CrossLanguageRetrievalQuery + SemanticPassage DTOs
→ rank_chinese_passages
→ LocalMultilingualEmbeddingBackend
→ deterministic cosine-equivalent dot-product ranking
→ safe evidence dictionaries
→ BilingualEvidenceResult
→ Formal draft/readiness path
```

The production nodes are in `backend/app.py`,
`backend/services/bilingual_evidence_workflow.py`,
`backend/services/cross_language_retrieval.py`, and
`backend/services/local_multilingual_embedding.py`.

## Query contract

`CrossLanguageRetrievalQuery` contains the English candidate UID, canonical and
normalized English term, bounded English context, discipline, governed Chinese
source scope, bounded top-k, and bounded passage budget. Its semantic text is:

```text
term:
<canonical English term>

discipline:
<discipline>

context:
<bounded English definition/context>
```

Context is capped at 800 characters and the assembled query at 1,100
characters. The E5 adapter adds `query: `; passages receive `passage: `.
Only a SHA-256 query representation hash is retained in results and artifacts.
The API cannot supply a model path, model revision, arbitrary backend, unbounded
top-k, or a switch that disables Chinese filtering.

## Chinese passage contract and governance

Candidate passages are bounded to 200 and must be non-empty, Chinese, active,
inside the governed source scope, and not blocked, rejected, withdrawn, or
OCR-required. `KnowledgeSource` and `KnowledgeChunk` checks remain in force.
English chunks do not enter the semantic candidate set.

Each result preserves source UID, chunk UID, content hash, language, source
status, quality status, backend/model/revision, score, rank, bounded snippet,
retrieval method, and query hash. Full source and full query text are not
persisted.

## Backend and model contract

- Backend: `local_multilingual_e5_pytorch_cpu_v1`
- Model: `intfloat/multilingual-e5-small`
- Revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- Dimension: 384
- Runtime: Sentence Transformers 3.4.1 + PyTorch 2.5.1 CPU
- Representation: mean pooling, L2 normalization
- Similarity: dot product of normalized vectors (cosine-equivalent)
- External API: none

Activation is explicit through the governed backend configuration. The model
snapshot must already exist in the repository-external cache and is loaded
with `local_files_only=true` and remote custom code disabled. Missing
configuration, cache, model files, dependencies, or encoding readiness fails
closed with `LOCAL_MULTILINGUAL_EMBEDDING_BACKEND_UNAVAILABLE`; there is no
lexical, hash-embedding, external, or alternate-model fallback.

DeepSeek query translation was not selected because it would send private
course context to an external Provider, make retrieval Provider-dependent, and
violate this task's offline and zero-request boundaries.

## Lexical gate, ranking, and cache

The lexical-overlap requirement is bypassed only in the explicit multilingual
semantic path. Existing monolingual lexical retrieval remains unchanged.
Language, source, quality, candidate-count, and top-k gates remain enabled.

Results sort by score descending, then source UID ascending, then chunk UID
ascending. Scores are cosine similarities, not probabilities. The maximum
top-k is 10. Query and passage representation cache keys include representation
type, model ID, model revision, and content hash. Representation caching is
request-scoped; the model snapshot cache remains repository-external. Cache
misses do not change ranking semantics, and ordinary tests use an injected
deterministic fake backend without model loading or network access.

## Gold isolation

Production query construction, filtering, representation, and ranking do not
read V2 gold, accepted aliases, required propositions, evidence labels, or
concept IDs. The scorer alone uses gold to calculate ranks after retrieval.
No benchmark-specific exclusion, mapping, source ordering, or reranking was
added.

## Evaluation denominators

The all-25 population remains intact:

| Stage | Count |
| --- | ---: |
| Benchmark concepts | 25 |
| English matched | 18 |
| English extraction missing | 3 |
| English binding ambiguous | 4 |
| Retrieval eligible | 18 |
| Chinese evidence returned | 18 |
| Exact Chinese candidate generated | 0 |
| Correct bilingual pair | 0 |
| Evidence-qualified | 0 |
| Provider-ready | 0 |

The 3 missing concepts are labeled
`UPSTREAM_ENGLISH_EXTRACTION_MISSING`; the 4 ambiguous concepts are labeled
`UPSTREAM_ENGLISH_BINDING_AMBIGUOUS`. They stay in the matrix but are not
counted as retrieval misses.

For the retrieval-eligible 18:

| Metric | Before | After |
| --- | ---: | ---: |
| hit@1 | 0.0000 | 0.7222 |
| hit@3 | 0.0000 | 0.8333 |
| MRR | 0.0000 | 0.7778 |
| Average observed gold rank | n/a | 1.1333 |
| Median observed gold rank | n/a | 1 |
| No-result count | 18 | 0 |
| Gold-bearing chunk absent from top 3 | 18 | 3 |

Earliest-stage counts after integration are:

- `CHINESE_TERM_IDENTIFICATION_MISSING`: 15
- `CROSS_LANGUAGE_RETRIEVAL_MISS`: 3
- `UPSTREAM_ENGLISH_EXTRACTION_MISSING`: 3
- `UPSTREAM_ENGLISH_BINDING_AMBIGUOUS`: 4

## Confusion groups

| Group | Correct rank | top1/top3 | Margin | Interpretation |
| --- | ---: | --- | ---: | --- |
| electric field / electric field strength | outside top 3 | false/false | n/a | Retrieval scope confusion; later reranking may be useful |
| electric potential / electric potential energy | 1 | true/true | 0.00476284 | Correct, but close alternative |
| angular velocity / angular acceleration | 1 | true/true | 0.00998848 | Correct |
| momentum / angular momentum | upstream ambiguous | n/a | n/a | Not retrieval-eligible; not a retrieval miss |
| mass / weight | 1 | true/true | n/a | Correct |

No hard-coded pair exclusion or benchmark mapping was used. The modest score
margins and the three top-3 misses establish a baseline rather than a claim
that retrieval quality is complete.

## Downstream boundary

Retrieval now provides independent Chinese evidence, but it does not infer or
select a standard Chinese term. Therefore exact Chinese candidates, pairing,
evidence qualification, and provider readiness remain zero. Field completeness
is not treated as semantic alignment.

The next production task should be a narrowly scoped
**Chinese standard-term identification contract** over the retrieved Chinese
chunks. Semantic pairing, Prompt, and Provider work should remain later stages.

## Performance and resource limits

The current implementation embeds at most 200 governed Chinese chunks per
request and returns at most 10. It is suitable for the controlled V2 baseline,
not a large-scale vector-index performance claim. The real evaluation used the
pinned CPU model offline from an external cache. Future scale work may require
a persistent governed index, but must preserve model revision, content hashes,
source governance, deterministic ranking, and fail-closed behavior.

## Validation and safety

The test suite covers English-only to Chinese retrieval, absence of lexical
overlap, query/context contracts, Chinese-only and source governance filters,
fixed backend identity, deterministic ranking/ties, budgets, provenance,
fail-closed behavior, no fallback, production workflow integration, all-25 and
eligible-18 denominators, and gold isolation.

Real Provider requests: 0. External embedding API requests: 0. Model/cache
tracked: false. V2 and legacy fixtures were not modified. Accident database
integrity is verified separately before and after the complete validation.

Final results:

- targeted retrieval/Formal/safety suite: 82 passed;
- full pytest: 1,359 passed, 56 pre-existing warnings;
- `dev_check`: passed, including release safety, full pytest, temporary
  migration, and backend API smoke;
- standalone release safety: passed;
- `git diff --check`: passed.

The 56 warnings are the existing SQLAlchemy `Query.get()` legacy warnings and
PDF binding deprecation warnings; Task 12D introduced no new warning class.

Frozen V2 hashes:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Task 12D artifact hashes:

- retrieval baseline:
  `3172a7e4e97a1a90705abba638c919588d5ce40fe78efc23986b2bcc9842dc68`
- retrieval matrix:
  `05a48d81737af84a1015eda7892dc63bbc0e4582428a97b95e5e33f540232862`
- confusion audit:
  `7485acdde453983262ad94203df3aac0cb8d3d3c465da69960738eba84222224`
- backend manifest:
  `300278f947102cc0e0f8c3ce5b19c0b59e730cd7fd743ed9ce73f8a782aca7fa`

The accident database before/final state is identical: SHA-256
`9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`,
size 1,015,808 bytes, mtime 1,785,496,597, WAL absent, SHM absent.
