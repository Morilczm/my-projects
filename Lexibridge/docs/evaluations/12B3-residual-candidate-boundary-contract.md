# Task 12B.3 — Residual Candidate Boundary Contract Closure

Status: `RESIDUAL_CANDIDATE_BOUNDARY_CONTRACT_CLOSED`

## Executive conclusion

Task 12B.3 closed the two residual English candidate-boundary defects with one
general rule. The production extractor already treated copular verbs as
definition boundaries, but did not give the same treatment to the lexical
definition predicates `measures` and `describes`. Consequently, exact
sentence-leading subjects were filtered while longer subject-plus-predicate
fragments survived.

The repair classifies those two general predicate forms as both definition
subject boundaries and n-gram action boundaries. It contains no benchmark
term, alias, score, or concept identifier. Candidate governance, the 50-item
limit, admission ordering, binding, retrieval, Chinese candidates, prompts,
providers, parsers, OCR, chunking, corpus, gold, and aliases were unchanged.

Frozen exact binding improved from 22/25 to 25/25. Boundary defects fell from
2 to 0, extraction missing remained 0, and the definition-fragment proxy fell
from 2 to 0.

## Pre-change production trace

### mass

- Source: `english-mechanics`, source character offset 359, source line 12.
- Parsed text: exact term present at the same character offset.
- Knowledge chunk: chunk index 6, chunk-local offset 0.
- Extractor input begins `Mass measures …`.
- Raw related candidates:
  - `Mass measures the amount`: 4 tokens, score 61, emitted.
  - `Mass measures`: 2 tokens, score 57, filtered by the 58 threshold.
  - `Mass`: 1 token, diagnostic score 53, filtered earlier by the short
    single-token guard because it was neither seeded nor structurally boosted.
- No exact canonical candidate reached admission, normalization, or binding.

The 53-point exact-term score consists of base 45 plus 8 for title case.
After the structural boundary boost of 12, the governed seeded minimum
confidence is 72.

### angular momentum

- Source: `english-mechanics`, source character offset 1368, source line 40.
- Parsed text: exact term present at the same character offset.
- Knowledge chunk: chunk index 20, chunk-local offset 0.
- Extractor input begins `Angular momentum describes …`.
- Raw related candidates:
  - `Angular momentum describes rotational`: 4 tokens, score 67, emitted.
  - `Angular momentum describes`: 3 tokens, score 61, emitted.
  - `Angular momentum`: 2 tokens, score 57, filtered by the 58 threshold.
  - `Angular`: 1 token, score 67 from repeated use, emitted as a shorter
    neighboring candidate.
- No exact canonical candidate reached admission, normalization, or binding.

The exact-term score consists of base 45 plus 12 for a multi-token phrase.
After the structural boundary boost of 12, the governed seeded minimum
confidence is 72.

Neither target was wrapped by a leading article or modifier. Neither exact
candidate was generated and later overflowed, normalized incorrectly, or
missed by the binder. The earliest failure was in
`extract_terms_from_text`: its definition-subject pattern recognized only
`is/are`, while `is_ngram_noise` did not treat `measures/describes` as
predicate boundaries. These are two effects of the same boundary contract.

## General repair

The existing sentence-leading definition-subject rule now recognizes
`measures` and `describes` in addition to `is` and `are`. The same lexical
predicate forms are action boundaries for n-gram generation, so the subject
is emitted exactly and subject-plus-predicate fragments are rejected.

The implementation is deterministic and remains bounded to a one-to-four
token sentence-leading subject that also passes existing noise checks. Tests
cover the benchmark shapes and unseen terms such as `magnetic moment` and
`specific heat`. Tests also verify that complete definition clauses and
copular predicates are not emitted, ordinary article-led prose does not cause
candidate explosion, provenance survives, canonical deduplication is
unchanged, and 55 candidates still produce 50 admitted plus 5 explicit
overflow candidates.

After repair:

- `mass`: exact original span `Mass`, canonical `Mass`, normalized `mass`,
  confidence 72, admitted and matched.
- `angular momentum`: exact original span and canonical
  `Angular momentum`, normalized `angular momentum`, confidence 72, admitted
  and matched.
- Predicate-bearing related fragments for both concepts: 0.

Benchmark-specific rules added: false.

## Torque overflow audit

Before Task 12B.3, `torque` was an exact production candidate with confidence
72. The Mechanics canonical set contained 62 candidates, and torque occupied
position 52 under the Task 12B.1 ordering key:

`(first_chunk_index, normalized_term, candidate_term)`.

With a 50-item limit, position 52 correctly received
`overflow_rejected / candidate_set_item_limit_exceeded`. This was expected
bounded governance behavior, not an extraction, ordering, normalization, or
binder defect.

Task 12B.3 did not change that ordering key, the limit, or the selection
implementation. The general boundary repair removed two invalid candidates
that previously appeared ahead of torque:

- `Angular momentum describes`
- `Angular momentum describes rotational`

The Mechanics canonical count therefore changed from 62 to 60, and torque
naturally moved from position 52 to position 50. It is now admitted with
`within_item_limit`. No torque-specific promotion, allowlist, score change,
gold lookup, upper-limit change, or ordering change was added. The first
overflow item is now position 51, and Mechanics remains bounded at 50 admitted
plus 10 explicit overflow candidates.

## Frozen quality comparison

| Metric | Task 12B.2 | Task 12B.3 |
| --- | ---: | ---: |
| Benchmark coverage | 25/25 | 25/25 |
| Canonical candidates | 90 | 88 |
| Admitted candidates | 78 | 78 |
| Explicit overflow candidates | 12 | 10 |
| Exact matched | 22 | 25 |
| Missing | 3 | 0 |
| Ambiguous | 0 | 0 |
| Exact-binding recall | 0.8800 | 1.0000 |
| Boundary defects | 2 | 0 |
| Extraction missing | 0 | 0 |
| Definition-fragment proxy | 2 | 0 |
| Exact-match/canonical precision proxy | 0.2444 | 0.2841 |
| Provider-ready | 5 | 5 |

The candidate set decreased by two rather than expanding, so no candidate
explosion occurred. Provider readiness did not change and no provider was
called.

## RED/GREEN and regression validation

The initial RED command produced 4 failures and 27 passes. Failures were
limited to absent exact definition subjects and predicate-bearing fragments;
provenance, deduplication, governance, and provider-isolation tests already
passed.

After the minimal production change:

- Focused GREEN: 32 passed.
- Required targeted regression: 62 passed.
- Related candidate, Formal, and API regression: 53 passed.
- Full pytest: 1313 passed, 56 warnings.
- `dev_check`: passed, including release safety, 1313 tests, temporary
  migration, and backend API smoke.
- Standalone release safety: passed.

The 56 warnings are the same categories and sources as Task 12B.2:

- 51 existing SQLAlchemy `Query.get()` legacy warnings, including 50 repeated
  by the frozen candidate diagnostic;
- 5 existing SWIG/PDF dependency deprecation warnings.

Task 12B.3 introduced no warning category or source. No warning was globally
filtered or hidden.

## Safety and artifacts

Frozen inputs remained:

- Corpus SHA-256:
  `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- Gold SHA-256:
  `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`

The incident database remained unchanged before and after:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: 1015808
- mtime: 1785496597
- WAL: absent
- SHM: absent

All evaluation and tests used repository-external temporary SQLite databases,
with database configuration established before backend import. No DeepSeek
credential was read. Real Provider requests: 0.

The sanitized artifact is
`docs/evaluations/artifacts/12B3-residual-candidate-boundary-results.json`,
SHA-256
`fa814fc0ac1884473e3415dbd124cf930e1951a718cd6ce8eac4fb13fc4eb175`.
It stores bounded traces and stable source/chunk positions, not complete source
text, credentials, private files, or machine-absolute paths.

Task 12B.3 did not begin Task 12C or any Chinese candidate, retrieval, Prompt,
Provider, PDF, or OCR optimization.
