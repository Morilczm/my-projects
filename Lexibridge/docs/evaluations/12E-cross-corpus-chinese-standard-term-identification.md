# Task 12E — Cross-Corpus Chinese Standard-Term Identification

Technical status: `CHINESE_STANDARD_TERM_IDENTIFICATION_CONTRACT_CLOSED`

Quality status: `CHINESE_STANDARD_TERM_IDENTIFICATION_QUALITY_BASELINE_ESTABLISHED`

## Executive conclusion

Production can now identify bounded, ranked Chinese standard-term candidates
directly from independent monolingual Chinese evidence retrieved by Task 12D.
The extractor requires neither an English string inside the Chinese chunk nor
a gold/alias mapping. It uses Chinese document structure only: headings, list
items, definition subjects, “所谓” constructions, and “称为” constructions.

On frozen Cross-Corpus V2, 15 concepts were dynamically eligible because their
gold-bearing Chinese chunk entered retrieval top 3. Exact canonical Chinese
candidates were generated for 14/15, ranked top1 for 7/15 and top3 for 12/15;
candidate MRR was 0.6378. No complete definition fragment or generic-noun
candidate survived the diagnostic proxies.

Task 12D retrieval remained exactly unchanged at hit@1/hit@3/MRR
`0.7222/0.8333/0.7778`. Pair accuracy, evidence qualification, and Provider
readiness remain zero because this task deliberately does not implement
bilingual semantic pairing.

## Exact root cause

Before Task 12E, `chinese_term_candidates.py` had three candidate sources:

1. existing Concept Alignment Cards keyed by exact English term;
2. legacy terminology records keyed by exact English term;
3. bilingual chunks discovered through English lexical search and parsed with
   inline EN/ZH regular expressions.

There was no input contract for the Chinese top-k evidence returned by Task
12D and no monolingual Chinese term extractor. Consequently pure Chinese
chunks containing “电势描述……”, “角速度表示……” or similar definitions
produced zero candidates. In `generate_chinese_term_candidates`, the earliest
loss occurred before `merge_and_rank_chinese_candidates`: no candidate source
consumed the retrieved evidence.

## Production call graph

Before:

```text
English candidate
→ cross-language retrieval
→ Chinese top-k evidence
→ no consumer
→ Chinese candidate list empty
→ pairing/preparation not reached
```

After:

```text
POST /api/evidence/bilingual
→ build_bilingual_evidence_query
→ retrieve_bilingual_evidence
→ retrieve_cross_language_chinese_evidence
→ identify_standard_chinese_terms
→ extract_monolingual_chinese_term_spans
→ merge_and_rank_chinese_candidates
→ BilingualEvidenceResult.chinese_term_candidates
→ existing bilingual candidate preparation
```

The Formal item preparation path keeps its existing English-keyed candidate
sources first. When they return no candidate, it now invokes the existing
bilingual evidence workflow, consumes its retrieved-evidence candidate list,
and then uses the pre-existing primary-candidate preparation. No semantic
pairing rule was added or changed.

Production files are:

- `backend/services/chinese_term_candidates.py`;
- `backend/services/bilingual_evidence_workflow.py`;
- `backend/services/document_alignment_item_preparation.py`;
- route entrypoints in `backend/app.py` remain unchanged for Task 12E.

## Monolingual extraction contract

Input is a bounded list of already retrieved evidence dictionaries containing
source/chunk UIDs, Chinese snippet, retrieval score/rank, source status and
quality, role, block metadata when available, discipline, and provenance.
Gold Chinese terms, aliases, propositions, evidence labels, and benchmark IDs
are not accepted.

The output retains:

- candidate and normalized text;
- stable candidate UID;
- source/chunk UIDs;
- bounded original span and character offsets;
- extraction method;
- score and rank;
- source language;
- retrieval rank and score;
- discipline and provenance;
- risk/reason labels.

At most 8 structural candidates are admitted per chunk and at most 50 per
query. These are fixed production bounds, not API-controlled unlimited values.

## Boundary rules

The extractor recognizes:

- governed heading/title text;
- bounded list-item labels before a colon;
- `X 是/指/表示/描述/说明/反映/衡量/定义为……`;
- related course-definition predicates such as `用于`, `等于`, `来自`,
  `给出`, `属于`, `包含`, `记录`, `刻画`, `比较`, and `适用于`;
- `所谓 X，是……`;
- `将……称为 X`;
- bounded `X 与……有关` relation subjects.

Extraction ends before the definition predicate. Complete sentences,
predicate-bearing fragments, pure numbers, formulas, units, punctuation,
pronouns, generic nouns, and conjunction phrases are rejected. This is a
general structural contract; benchmark terms do not appear in a production
allowlist.

## Normalization

Candidate display text uses Unicode NFC, trimmed punctuation, and collapsed
whitespace. Matching/ranking normalization uses NFKC, normalizing full/half
width punctuation and parentheses while preserving meaningful scope tokens
such as `角`, `强度`, and `能量`. No simplified/traditional conversion,
translation, canonical-gold substitution, or alias expansion occurs.

## Ranking

The existing candidate scoring abstraction was extended with:

- source-type base confidence;
- extraction-structure confidence;
- retrieval-rank bonus;
- governed source role/trust signals;
- candidate-length penalty;
- existing quality and review penalties.

Final deterministic order is:

```text
score DESC
→ retrieval rank ASC
→ source UID ASC
→ chunk UID ASC
→ normalized candidate text ASC
```

This ordering is bounded and independent of gold. Equal structural candidates
can remain tied; Task 12E does not pretend that structural confidence is
bilingual semantic compatibility.

## Provenance and safety

Every candidate retains its retrieved Chinese source/chunk identity, bounded
span, content hash provenance, retrieval rank, extraction method, and stable
candidate UID. Full sources are not written to artifacts. No schema,
migration, retrieval model, threshold, Prompt, Provider, or frontend field was
changed.

External API requests: 0. Real Provider requests: 0.

## Evaluation denominators

All 25 benchmark concepts remain present:

| Population/stage | Count |
| --- | ---: |
| All concepts | 25 |
| English matched | 18 |
| English missing | 3 |
| English ambiguous | 4 |
| Retrieval eligible | 18 |
| Chinese evidence returned | 18 |
| Identification eligible (correct chunk in top3) | 15 |
| Exact Chinese candidate generated | 14 |
| Exact candidate top1 | 7 |
| Exact candidate top3 | 12 |
| Correct bilingual pair | 0 |
| Evidence-qualified | 0 |
| Provider-ready | 0 |

The 3 English missing rows remain
`UPSTREAM_ENGLISH_EXTRACTION_MISSING`; the 4 ambiguous rows remain
`UPSTREAM_ENGLISH_BINDING_AMBIGUOUS`; the 3 retrieval misses remain
`UPSTREAM_CROSS_LANGUAGE_RETRIEVAL_MISS`. None is counted as a Chinese
identification failure.

Identification-eligible results:

| Metric | Before | After |
| --- | ---: | ---: |
| Exact candidate generated | 0/15 | 14/15 |
| Exact top1 | 0/15 | 7/15 |
| Exact top3 | 0/15 | 12/15 |
| Candidate MRR | 0.0000 | 0.6378 |
| No-candidate rows | 15 | 0 |
| Generic false positives | n/a | 0 |
| Definition fragments | 15 historical inline failures | 0 |

Earliest-stage counts across all 25:

- `BILINGUAL_SEMANTIC_PAIRING_MISSING`: 14;
- `CHINESE_TERM_RANKING_OR_EXTRACTION_DEFECT`: 1;
- `UPSTREAM_CROSS_LANGUAGE_RETRIEVAL_MISS`: 3;
- `UPSTREAM_ENGLISH_EXTRACTION_MISSING`: 3;
- `UPSTREAM_ENGLISH_BINDING_AMBIGUOUS`: 4.

## Retrieval preservation

| Retrieval metric (eligible 18) | Task 12D | Task 12E |
| --- | ---: | ---: |
| hit@1 | 0.7222 | 0.7222 |
| hit@3 | 0.8333 | 0.8333 |
| MRR | 0.7778 | 0.7778 |
| Chinese evidence returned | 18 | 18 |

The E5 model, revision, query construction, passage filtering, ranking,
top-k, and cache contract were not modified.

## Confusion groups

| Group | Result | Margin | Interpretation |
| --- | --- | ---: | --- |
| 电场 / 电场强度 | upstream retrieval miss | n/a | Neither term is scored as identification failure |
| 电势 / 电势能 | 电势 rank 1 | 0.0000 | Structural tie remains; semantic pairing is required |
| 角速度 / 角加速度 | 角速度 rank 2 | 0.0000 | Correct term present, structural tie |
| 动量 / 角动量 | upstream English ambiguous | n/a | Not identification-eligible |
| 质量 / 重量 | 质量 rank 5 | -0.0400 | Retrieval-rank signal favors other candidates; semantic pairing required |

No hard-coded exclusions were used. The score margins make the remaining
boundary explicit: structural candidate ranking cannot replace English-Chinese
concept comparison.

## False-positive analysis

The final eligible subset contains zero candidates in the configured generic
noun set and zero candidates containing definition predicates. Earlier
diagnostic forms such as pronoun-led subjects, conjunction phrases, trailing
adverbs, and “这一说法” fragments were removed through general boundary
rules, not benchmark-specific terms.

One frozen-scorer-eligible concept has no exact candidate. Its top-3 evidence
contains a surface occurrence used by the scorer but not an independent
definition subject; the extractor correctly refuses to manufacture a term
from that occurrence. This is retained as
`CHINESE_TERM_RANKING_OR_EXTRACTION_DEFECT`, not repaired through gold.

## Gold isolation

Production extractor, normalization, ranking, workflow, and Formal preparation
do not import or read V2 gold, aliases, evidence labels, required propositions,
or concept IDs. Gold is used only by the evaluation runner after production
candidate generation. No translation table or 25-item allowlist was added.

## Next failure and recommendation

The dominant next failure is `BILINGUAL_SEMANTIC_PAIRING_MISSING`. Correct
Chinese candidates now exist for 14 identification-eligible concepts, but the
system has not yet compared English definition/context with Chinese candidate
definition/context to choose the semantically corresponding scope.

The next task should therefore audit and implement a bounded bilingual
semantic-pairing contract. It must not compensate by changing retrieval,
candidate extraction, Prompt, Provider, or evidence thresholds.

## Validation

- RED: collection failed because the monolingual identification functions did
  not exist.
- Final targeted Chinese candidate/retrieval/Formal suite: 62 passed.
- Full pytest: 1,370 passed, 56 pre-existing warnings.
- `dev_check`: passed, including release safety, full pytest, temporary
  migration, and backend API smoke.
- Standalone release safety: passed.
- `git diff --check`: passed.

The warning set remains the existing SQLAlchemy `Query.get()` legacy warnings
and PDF binding deprecations; Task 12E introduced no new warning category.

Frozen V2 hashes:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Task 12E artifact hashes:

- results:
  `8f70dc9839be8da4c5b9dea0e3ff92a44c93c091e79b8f4c1fda56f5013d29b0`
- matrix:
  `39c25fdd6af2d48ec04e5c965a45cb5590a5db8b22593c6f4f020f4b254967f5`
- confusion audit:
  `ce192f4bb931eeaa9afc0ea3cf77a566bdadb8f5cb36990514a63281c6a7426b`

The accident database before/final state is identical: SHA-256
`9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`,
size 1,015,808 bytes, mtime 1,785,496,597, WAL absent, SHM absent.
