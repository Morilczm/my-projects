# Task 12C-B — Leakage-Resistant Cross-Corpus Benchmark Rebuild

Status: `LEAKAGE_RESISTANT_CROSS_CORPUS_BENCHMARK_FROZEN`

## Executive conclusion

Cross-Corpus Benchmark V2 is frozen at
`evaluation/cross_corpus_v2/`. It contains four static English-only course
sources, four separately written monolingual Chinese reference sources, 25
scorer-only gold alignments, and 15 distractor concepts. No corpus text is
generated from gold.

The Chinese corpus contains zero complete gold English terms or aliases, the
English corpus contains zero gold Chinese terms, and no inline bilingual
delimiter occurs. Consequently production can no longer retrieve the correct
Chinese chunk through English keyword leakage.

With production unchanged, English exact-candidate presence is 22/25
(recall 0.8800); exact binding is 18 matched, 3 missing, and 4 ambiguous. For
the 18 uniquely bound concepts, the first downstream failure is
`CROSS_LANGUAGE_RETRIEVAL_MISS`. Chinese retrieval hit@1/hit@3/MRR, exact
Chinese candidate generation, bilingual pairing, evidence qualification, and
provider readiness are all zero.

The trustworthy next production priority is cross-language retrieval/query
construction. Chinese standard-term identification and semantic pairing remain
missing, but cannot be reached until independent Chinese evidence is found.

## Legacy benchmark retention

The original hashes remain unchanged:

- corpus: `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- gold: `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`

It is now explicitly documented under
`evaluation/legacy_inline_bilingual/` as regression-only, with
`production_core_path_represented=false`,
`cross_corpus_alignment_validated=false`,
`contains_inline_bilingual_leakage=true`, and
`retained_for_regression_only=true`. No legacy row was changed or rescored.

## V2 design

English and Chinese documents are static original short texts with different
source order, paragraph organization, prose, and topic splits. Opaque source
IDs (`en-sNN`, `zh-sNN`) and neutral filenames contain neither concept IDs nor
terms. Gold contains opaque IDs, accepted aliases, independent evidence
labels, confusion concepts, and semantic propositions; these fields are read
only by the scorer.

English sources model rotation, electricity, energy/interactions, and
translational mechanics. Chinese sources instead group rotation, foundational
motion, electrical indexing, and work/energy. Their ordering is deliberately
different and no paragraph-index mapping exists.

Distractors include angular acceleration, moment of inertia, centripetal
acceleration, electric field strength, electric potential energy, current
density, magnetic flux density, linear momentum, weight, speed, distance,
pressure, elastic potential energy, friction, and magnetic flux.

## Anti-leakage results

| Check | Result |
| --- | --- |
| English corpus contains CJK | false |
| Chinese corpus contains gold English term/alias | false |
| English corpus contains gold Chinese term/alias | false |
| Inline bilingual pattern | false |
| Gold or concept ID in source IDs/text | false |
| Corpus builder imports gold | false; corpus is static |
| Production receives gold/aliases/propositions | false |
| English/Chinese source order identical | false |
| Sources physically independent | true |
| English targets present | 25/25 |
| Chinese targets/aliases present | 25/25 |
| Distractors | 15 |

## Production baseline

The evaluation configures a repository-external temporary SQLite database
before backend import and invokes the existing production English extractor
and lexical cross-corpus discovery contract. No production file or threshold
was changed.

| Metric | Legacy inline | Cross-Corpus V2 |
| --- | ---: | ---: |
| Coverage | 25/25 | 25/25 |
| English exact candidate recall | 1.0000 | 0.8800 |
| English matched/missing/ambiguous | 25/0/0 | 18/3/4 |
| Chinese source-term presence | 25/25 | 25/25 |
| Chinese retrieval hit@1 | 0.6000 fixture discovery | 0.0000 |
| Chinese retrieval hit@3 | 1.0000 | 0.0000 |
| Chinese retrieval MRR | 0.8000 | 0.0000 |
| Exact Chinese candidate generated | 0/25 | 0/25 |
| Chinese candidate top1/top3/MRR | 0/0/0 | 0/0/0 |
| Bilingual pair top1/top3 | 0/0 | 0/0 |
| Evidence-qualified | 5/25 | 0/25 |
| Provider-ready | 5/25 | 0/25 |

Earliest-stage counts:

- `ENGLISH_EXTRACTION_MISSING`: 3
- `AMBIGUOUS`: 4
- `CROSS_LANGUAGE_RETRIEVAL_MISS`: 18

The zero retrieval score is expected and credible: production performs lexical
matching with an untranslated English term, while Chinese sources contain no
complete English gold term. This is not a benchmark defect.

## Funnel and interpretation

All 25 concepts remain in the denominator. Twenty-two have at least one exact
English candidate, but only 18 bind uniquely. Those 18 reach Chinese discovery
and fail before Chinese standard-term identification. No item reaches semantic
pairing or evidence readiness.

V2 can validate English-only input, independent Chinese sources, leakage-free
retrieval, standard-term identification, cross-corpus pairing, and the full
25-item funnel. It cannot validate OCR, the distribution of real university
textbooks, cross-discipline generalization, live knowledge updates, large-scale
retrieval performance, or teacher review accuracy.

V2 is a controlled architecture benchmark, not a claim of overall real-world
quality.

## Frozen hashes

- English corpus bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese corpus bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- V2 gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- V2 manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`
- frozen hash manifest:
  `4a2a8cbeae90a0a5d320c1d557aa0040d3cf9a5c1e991f90f795f495172d8033`

Artifacts:

- manifest: `550c7a51835c47d81f66fb3587e61ea70f551e94587fb11c6ab921d267b23c18`
- integrity: `25606ae6358f1d98df3582f6432250b440def37f1998bc7d72514679602a23cf`
- baseline: `c51295b0f51760711abc579ed2932549bbe2b0ff942ef9059d90b01582635e8a`
- concept matrix: `5c1eafb2c189907d9b7bb18507e36490bffdfa83940bc92520363a8fa1832fc8`

Artifacts contain opaque IDs, ranks, reason codes, scores, hashes, and bounded
terms only. They contain no full corpus, private material, credentials,
absolute machine paths, or incident database content.

Real Provider requests remained zero. Production quality was not modified.
