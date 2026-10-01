# Task 12A Frozen Candidate Extraction Failure Diagnosis and Benchmark Audit

## Status

`CANDIDATE_FAILURE_DIAGNOSIS_COMPLETED`

Task 12A was diagnostic only. Production parsing, OCR, chunking, candidate
extraction, normalization, binding, retrieval, Prompt, Provider transport,
schema, frozen corpus, and frozen gold were not changed. Real Provider
requests: `0`.

## Executive conclusion

Fresh production ingestion of the frozen synthetic corpus reproduced `25/25`
benchmark coverage, `3` exact matches, `22` missing, and `0` ambiguous
bindings. The `3/25` result is not a PDF parsing failure: all 25 English and
Chinese gold terms survived source, parsed text, and KnowledgeChunk layers.

The dominant failure is a source-level candidate boundary/admission failure.
The English mechanics source produced 63 raw occurrences and 55 canonical
candidates. The production formal boundary permits 50 items, fails closed, and
returns no candidates for that entire source. This accounts for 20 missing
concepts. The electricity source produced 34 raw occurrences and 26 canonical
candidates and passed the boundary; `electric charge` and `electric field`
were present in source/parse/chunks but absent from final candidates, accounting
for two candidate-extraction failures. Electric potential, potential
difference, and capacitance matched exactly.

Task 12B should first address the all-or-nothing candidate-set overflow and its
noise/boundary behavior, then address short two-word terms such as `electric
charge` and `electric field`. This recommendation is a diagnosis, not a
production change.

## Benchmark audit

All 25 concepts were audited against both frozen sources after ingestion.
Terms, source IDs, actual source forms, aliases, definition context, and
evidence resolution are recorded in the benchmark-audit artifact.

| Audit status | Count |
| --- | ---: |
| `BENCHMARK_SOURCE_VALID` | 24 |
| `BENCHMARK_ALIAS_INCOMPLETE` | 1 |
| Other benchmark defects | 0 |

`physics-24` is alias-incomplete because the Chinese source explicitly says
potential difference is also called `电压`, while the gold accepts only `电势差`
(and does not enumerate `voltage`). The exact gold term is nevertheless present
and the production binder matched it, so this recorded benchmark defect does
not explain any missing binding. Gold and corpus were not modified and the item
remains in the denominator.

Every source supplies a definition sentence. The synthetic evidence labels
resolve deterministically to real ingested source/chunk records through the
existing frozen marker mapping; no full source text is stored in 12A artifacts.

## Failure matrix

| Population | Concepts | Binding | Primary attribution |
| --- | --- | --- | --- |
| Mechanics missing | physics-01–physics-20 | 20 missing | 20 `CANDIDATE_BOUNDARY_DEFECT` |
| Electricity missing | physics-21–physics-22 | 2 missing | 2 `CANDIDATE_EXTRACTION_DEFECT` |
| Matched controls | physics-23–physics-25 | 3 matched | 3 `NO_DEFECT_MATCHED` |

For the 20 mechanics items, “boundary” denotes the earliest production
candidate-layer failure: noisy/over-broad extraction creates 55 canonical
candidates, exceeding the 50-item formal boundary and discarding the complete
candidate set. It does not mean parsing or chunking lost each individual term.

For the two electricity failures, bounded approximate analysis found partial
tokens such as `Electric`, but no reasonable normalized exact, containment,
token-order, or high-overlap candidate. These are not normalization or binder
failures.

## Attribution counts

Counts among the 22 missing rows:

| Attribution | Count |
| --- | ---: |
| Parser | 0 |
| Chunking | 0 |
| Candidate extraction | 2 |
| Candidate boundary | 20 |
| Candidate fragmentation | 0 |
| Normalization | 0 |
| Binder | 0 |
| Ambiguous binding | 0 |
| Benchmark defect causing missing | 0 |
| Temporarily undetermined | 0 |

Layer survival across all 25 was source `25`, parsed text `25`, and chunk `25`.
Candidate/boundary failure affected 22; normalization and binder introduced no
additional failures. The sole benchmark alias defect is independent of the
22-item missing set.

## Survivor bias and benchmark validity

Task 11N removed the major denominator survivor bias: missing production
candidates no longer disappear, and all 25 rows receive terminal results. The
3-item Provider-ready/called subset remains conditionally selected by successful
production extraction and exact binding, so its Provider outcomes cannot be
generalized to all 25. The 6-item gold-valid-evidence subset is a separate
post-retrieval quality subset and must not be confused with either population.

The four populations are:

1. all-25 end-to-end denominator;
2. 3-item exact-matched subset;
3. the same 3-item Provider-called subset in 11J-R5;
4. 6-item gold-valid-evidence subset.

This benchmark supports conclusions about deterministic ingestion and
candidate behavior on the frozen synthetic physics TXT fixture, denominator
preservation, and the observed candidate boundary failure. It does not estimate
quality across real courses or general PDFs.

Representativeness is narrow: it contains single-word terms and compound
phrases, but no meaningful coverage of hyphenated terms, abbreviations,
formula-named terms, or genuine parenthetical English terms. It contains no
born-digital PDF, scanned PDF, PPT export, two-column layout, table, or formula
page. Therefore `3/25` cannot be attributed to PDF extraction and cannot be
presented as representative of all course PDFs.

## Test-first and safety evidence

- RED: both new test modules failed collection before the evaluation-only
  diagnosis module existed.
- GREEN: `8 passed`.
- The tests cover parsing, chunking, extraction, boundary, fragmentation,
  Unicode/case diagnostics, alias defects, absent benchmark terms, fixed
  25-row output, Provider prohibition, immutability, and artifact sanitation.
- Approximate matching is diagnostic only and never changes production binding
  or scoring.
- No credential was requested or read.
- Real Provider requests: `0`.

## Artifacts

- `12A-candidate-failure-matrix.json`:
  `5413078f87c8062aeb8c35c5515ca96dfc8b952f91cfff10c216305824e71e72`
- `12A-candidate-failure-matrix.csv`:
  `edd907af07e0d52e6ec3781209c2c4bff391d058c9ee3284dfebe434347fa611`
- `12A-benchmark-audit.json`:
  `a9ca62531e0e2bd1cbdd98d28bd0cffc4229d22d5c031cfb52358c6f78ee9931`

Artifacts contain bounded candidate summaries and opaque IDs only. They contain
no full source text, API key, credential, private file, local absolute path, or
accident-database content.
