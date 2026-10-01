# Task 12C.1 — Inline Bilingual Chinese Candidate Boundary Diagnosis

Status: `INLINE_BILINGUAL_CHINESE_CANDIDATE_DIAGNOSIS_COMPLETED`

## Executive conclusion

This diagnosis is scoped to the frozen synthetic **inline bilingual fixture
path**: an English term and its Chinese definition occur in the same fixture
fragment, and production applies an inline bilingual regex to that fragment.
It is not a complete or representative validation of the product's core
English-to-Chinese cross-corpus alignment path.

The result proves that the inline bilingual regex has a real greedy boundary
defect. It does not prove that independent Chinese-source term identification
or cross-corpus semantic alignment has the same dominant root cause. A
cross-corpus architecture audit is required before any production repair is
selected.

The product core path is materially broader: English course material produces
English technical terms; an independent Chinese knowledge source is retrieved;
a Chinese standard term is identified; the English and Chinese terms are
semantically aligned; and evidence qualification determines whether a concept
card may proceed. English course material normally need not contain a Chinese
term or Chinese definition.

Within the synthetic inline fixture, the current Task 12B.3 English pipeline
binds all 25 frozen concepts exactly, so the full benchmark population reaches
the inline Chinese diagnostic boundary. The historical Chinese top1 and top3
results were recomputed rather than reused. Both remain 0.0000.

The dominant and earliest failure **for this inline fixture path** is
`INLINE_BILINGUAL_CHINESE_CANDIDATE_BOUNDARY_DEFECT`. All 25 gold Chinese terms
exist in the same synthetic source fragments, parsed text, and chunks. The
candidate-source retrieval finds every gold-bearing fixture chunk within its
top three. The explicit bilingual pattern then captures up to 32 Chinese or
alphanumeric characters after `English term 即` without stopping at Chinese
definition predicates, emitting `术语 + 是/表示/描述/说明 + explanation`
instead of the exact term.

Production generated at least one Chinese candidate for every concept, but
generated zero exact or accepted-alias candidates. Pairing consequently
received 25 correct English inputs and zero correct Chinese inputs. There is
no independently observable pairing-selection defect in this population
because the correct Chinese candidate never reaches that layer.

Task 12C.1 and this correction added only evaluation scripts, tests, sanitized
artifact metadata, and documentation. Production quality was not modified,
and cross-corpus alignment was not validated.

## Current 25-item inline-fixture baseline

Every metric below is limited to the frozen synthetic inline bilingual
fixture. Chinese source presence of 25/25 means the fixture deliberately
contains the Chinese definition adjacent to the English term; it does not
measure presence in an independent Chinese textbook or knowledge base.

| Metric | Current result |
| --- | ---: |
| Benchmark coverage | 25/25 |
| English exact matched | 25/25 |
| Chinese gold term in source | 25/25 |
| Chinese gold term in parsed text | 25/25 |
| Chinese gold term in chunk | 25/25 |
| Concepts with at least one generated Chinese candidate | 25/25 |
| Exact Chinese candidate generated | 0/25 |
| Accepted-alias candidate generated | 0/25 |
| Chinese candidate top1 accuracy | 0.0000 |
| Chinese candidate top3 accuracy | 0.0000 |
| Chinese candidate MRR | 0.0000 |
| Bilingual pair top1 accuracy | 0.0000 |
| Bilingual pair top3 accuracy | 0.0000 |
| Operational evidence-qualified | 5/25 |
| Provider-ready | 5/25 |

No benchmark concept defines an additional accepted Chinese alias, so alias
generation and alias-source presence are not applicable to this fixture.

## Inline-fixture retrieval results

The production candidate-generation retrieval, queried with the system-derived
English candidate against the synthetic fixture's governed Chinese reference
chunks, produced:

- hit@1: 0.6000 (15/25);
- hit@3: 1.0000 (25/25);
- MRR: 0.8000;
- all gold-bearing chunks in the production retrieval scope: 25/25.

Ten concepts had their gold-bearing chunk at rank 2 because another governed
chunk containing the same English substring ranked equally or higher. This did
not prevent candidate generation because all gold-bearing chunks remained in
the production retrieval scope.

For historical comparability, the second retrieval performed after selecting
the generated Chinese fragment produced hit@1 1.0000, hit@3 1.0000, and MRR
1.0000. This apparently perfect evidence retrieval may simply re-hit the same
synthetic Chinese definition chunk from which the overlong candidate was
copied. It is not evidence of independent Chinese-corpus retrieval quality and
cannot be extrapolated to that setting. The historical evidence hit@3 result
therefore coexists with zero Chinese candidate accuracy.

## Candidate morphology audit

Production emitted 30 post-dedup candidates across 25 concepts:

- candidate count per concept: 21 concepts produced one, three concepts
  produced two, and one concept produced three;
- average candidate length: 15.8333 characters;
- candidates containing a definition predicate: 30/30;
- definition-fragment ratio: 1.0000;
- candidates longer than 12 characters: 25/30;
- generic standalone candidates: 0/30;
- single-character candidates: 0/30;
- mixed Chinese/English candidates: 0/30;
- parenthesized English abbreviations: 0/30;
- symbol or unit candidates: 0/30;
- full-width ASCII candidates: 0/30;
- Unicode punctuation retained in candidate text: 0/30;
- post-dedup duplicate ratio: 0.0000;
- ranking inversion count: 0, because no correct candidate exists to be
  inverted;
- top1 and top3 precision proxies: both 0.0000.

Four concepts produced multiple candidates with identical 0.81 scores:
`velocity`, `force`, `momentum`, and `mechanical energy`. These are
overgeneration observations, but their earliest defect remains boundary
capture because every competing candidate is itself a definition fragment.
No simplified/traditional or full-width/half-width competition was observed
in the frozen fixture.

## Scoped attribution counts

| Primary attribution | Count | Denominator |
| --- | ---: | ---: |
| `INLINE_BILINGUAL_CHINESE_CANDIDATE_BOUNDARY_DEFECT` | 25 | 25 |
| All other attribution classes | 0 | 25 |

The original frozen row-level diagnostic label
`CHINESE_CANDIDATE_BOUNDARY_DEFECT` is retained in the artifacts to avoid
altering or rescoring the 25 historical rows. Its corrected interpretation is
the scoped label above: the generator did not merely fail to emit output in
the synthetic inline path; every item produced one or more candidates, and
the first divergence was
`extract_chinese_candidates_from_text_around_english_term`, where
`CHINESE_PATTERN` greedily included the definition predicate and explanation.
This attribution does not cover the independent cross-corpus architecture.

There were no benchmark fixture defects and no benchmark alias gaps.

## Ranking audit

There are no valid `CHINESE_CANDIDATE_RANKING_DEFECT` cases in this run.
Ranking defects require a correct candidate to be present but ranked below the
accepted cutoff. Here, exact and alias candidate presence is 0/25.

All bilingual-chunk candidates receive the same principal production features
in this synthetic corpus: exact English match, course match, Chinese reference
role, bilingual pattern, and governed source trust. The four multi-candidate
concepts therefore have equal 0.81 candidate scores. Retrieval score is
retained in diagnostic breakdown but is not included in the final candidate
score.

The primary selector orders by descending score, then candidate UID, then
case-folded Chinese text. This is deterministic within a persisted run, but
candidate UID includes source/chunk identity, so an equal-score selection can
change across fresh synthetic ingestions that receive new UUIDs. That behavior
did not hide a correct candidate in this benchmark because none was generated.

## Inline-fixture pairing audit

Pairing inputs and outcomes:

- correct English input present: 25/25;
- correct Chinese input present: 0/25;
- correct pair: 0/25;
- independent pairing defects: 0/25;
- truncation loss of a correct Chinese input: 0;
- source/chunk provenance retained: yes.

In this synthetic path, production candidate discovery uses exact English
lexical matching and proximity to the English term inside the same governed
Chinese/bilingual fixture chunk.
Candidate scoring uses source type, exact English match, course/chapter,
trust, source role, bilingual-pattern status, duplicate-source support, and
risk penalties. It does not use cross-language surface overlap, definition
similarity, retrieval rank, or abbreviation mapping.

The pairing/selection boundary observed here chooses the highest-scoring
generated candidate; it does not independently verify semantic equivalence.
There is no explicit pair-failure reason code. Instead, candidates carry
`candidate_not_alignment_verified`, and formal preparation may continue if
evidence exists. This observation does not validate how independent
English-source and Chinese-source candidates should be semantically aligned.

## Evidence readiness audit

Five electricity concepts were operationally evidence-qualified and
Provider-ready:

- electric charge;
- electric field;
- electric potential;
- potential difference;
- capacitance.

The other 20 returned `DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT` during formal
preparation. None is classified as `EVIDENCE_READINESS_DEFECT`, because every
concept had already failed at the earlier Chinese boundary stage.

Operational readiness does not mean the pair is correct. All five ready items
still selected overlong Chinese definition fragments, so provider-ready 5/25
does not represent five correct Chinese term alignments. Real Provider
requests remained zero.

## Population funnel and survivor bias

Every layer retains the original denominator:

| Population/subset | Count | Original denominator |
| --- | ---: | ---: |
| All benchmark concepts | 25 | 25 |
| Gold-bearing Chinese chunk in production retrieval scope | 25 | 25 |
| Exact/accepted Chinese candidate generated | 0 | 25 |
| Correct candidate in top3 | 0 | 25 |
| Correctly paired | 0 | 25 |
| Operational evidence-qualified | 5 | 25 |
| Provider-ready | 5 | 25 |

The operational evidence-qualified and Provider-ready sets are not semantic
subsets of correctly paired items: preparation does not have access to
benchmark correctness and can ready an overlong candidate. Treating the five
ready electricity items as the Chinese-quality denominator would therefore
introduce strong conditional selection bias. The full funnel also describes
only the inline synthetic fixture, not an independent Chinese corpus.

Task 12B raised downstream English coverage from a small matched subset to all
25 fixture concepts, exposing the existing inline bilingual behavior across
that full population. It did not improve Chinese top1 or top3 accuracy. These
results do not establish whether an independent Chinese source would be
retrieved or whether its standard term would be identified and aligned.

## Recommended next task

The single dominant root cause **within the synthetic inline bilingual path**
is `INLINE_BILINGUAL_CHINESE_CANDIDATE_BOUNDARY_DEFECT`: the Chinese capture
following an English alias does not stop before `是`, `指`, `表示`, `称为`,
`定义为`, `描述`, `说明`, or similar definition predicates.

This result is insufficient to select a production repair for the core
English-to-Chinese path. The recommended next task is an
**English-to-Chinese cross-corpus alignment architecture audit** covering
independent Chinese-source retrieval, Chinese standard-term identification,
semantic alignment, provenance, and readiness boundaries. Only after that
audit should production repair scope be chosen.

This is a diagnosis and recommendation, not a production repair.

## RED/GREEN and validation

The RED run failed during collection because the evaluation-only diagnosis
module did not yet exist. After implementing the diagnostic runner:

- focused diagnostic GREEN: 10 passed;
- required targeted regression: 48 passed;
- release safety: passed.

The runner uses repository-external temporary SQLite storage and configures
the database before backend import. It does not read a DeepSeek credential or
call any Provider.

## Frozen inputs, database safety, and artifacts

Frozen hashes remained:

- Corpus:
  `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- Gold:
  `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`

The incident database remained unchanged before and after:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: 1015808
- mtime: 1785496597
- WAL: absent
- SHM: absent

Sanitized artifacts (all scoped to `inline_bilingual_fixture_path`; the JSON
artifacts explicitly mark `production_core_path_represented=false` and
`cross_corpus_alignment_validated=false`; the CSV retains its original rows):

- `12C1-chinese-candidate-matrix.json`:
  `261e5c576a682e2de5125eb2be5cf640b34b4ccb1a07011a6c5a1096e7b4a982`
- `12C1-chinese-candidate-matrix.csv`:
  `ad4f784318521bbaf23aa03f07ebbe69c004a2575a4be58d7f45369825332dd9`
- `12C1-bilingual-pairing-audit.json`:
  `498dce51ab76654d653c20b6547bd16ca0f80c5d53f07b4d03f59f0c28ce3b5a`

The artifacts contain bounded candidate summaries and governed identifiers,
not complete source text, credentials, private material, machine-absolute
paths, or incident database contents.

Task 12C.1 made no production change. This correction did not begin a
cross-corpus alignment implementation or Task 12C-R.
