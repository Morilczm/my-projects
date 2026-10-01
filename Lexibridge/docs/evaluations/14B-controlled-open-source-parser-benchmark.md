# Task 14B Controlled Open-source Parser Benchmark

## Status

- Technical status: `CONTROLLED_OPEN_SOURCE_PARSER_BENCHMARK_CLOSED`
- Quality status: `CONDITIONAL_PARSER_INTEGRATION_CANDIDATE_ESTABLISHED`
- Baseline: `6cca8cb0881226c6031f3adafff0d89c1146d584`
- Selected integration candidate: `docling@2.117.0`
- Selected role: `conditional_complex_document_parser_candidate`
- Production parser changed: false
- Production adapter authorized: false

## Decision

Docling is the best eligible candidate in this controlled comparison, but it
did not pass every document-class gate and must not replace the current parser
globally. It is recommended for the next adapter task only for:

- scanned English and Chinese PDFs;
- simple table PDFs with a preserved row/column shape.

The following classes remain excluded from Docling routing until their
individual gates are repaired and rerun:

- multi-column PDFs: reading-order accuracy was `0.8214`;
- mixed-layout table PDFs: the table was not retained;
- formula PDFs without composition with the existing `FormulaRegion` path:
  formula structure retention was `0.0`.

The current native parser remains the simple-document fallback. The next task
must introduce per-document quality routing through the existing parser and
KnowledgeChunk contracts; it must not create a second ingestion or retrieval
system.

MinerU is not eligible. Its installed `3.4.4` metadata reports the non-standard
`LicenseRef-MinerU-Open-Source-License`, its multi-column score was lower, and
its Chinese headings were commonly merged into paragraph bodies. That reduced
the retrieval Chinese corpus to two chunks and prevented a downstream gain.

## Why This Is Not Merely A Strict Threshold Problem

The rejected cases have observable structural failures:

- Docling and MinerU interleaved content across columns in the synthetic
  two-column PDF.
- Both candidates detected the simple table, but neither retained the table in
  the mixed-layout blocker.
- Neither candidate emitted a governed `formula` block for the raster formula
  fixture.
- MinerU merged nine Chinese term headings with their definitions as ordinary
  paragraphs, so the existing heading-aware KnowledgeChunk builder produced
  two broad chunks rather than eleven concept-preserving chunks.

These are content and provenance defects, not arbitrary policy failures. A
global replacement would therefore make some real documents worse despite the
higher aggregate score.

## Controlled Corpus

The corpus contains eleven repository-independent, runtime-generated synthetic
PDFs (fifteen pages total):

- single-column born-digital English;
- two-column born-digital English;
- scanned English;
- scanned Chinese;
- mixed-layout blocker;
- simple table;
- raster formula;
- negative/no-term document;
- three-page repeated header/footer document;
- two-page English retrieval concepts;
- two-page independent Chinese retrieval evidence.

The retrieval pair contains ten concepts in physics, mechanics, control
engineering, and applied mathematics, including three intentionally confusable
groups. The Chinese PDF contains no complete English gold term. Fixtures do
not contain private course material, inline bilingual answers, aliases, or
Provider output.

## Execution Contract

Each parser ran in an isolated process and normalized to a common evaluation
block contract. Candidate model artifacts and caches remained under
repository-external temporary storage and are not tracked by Git.

| Parser | Runtime | Local model policy | License gate |
|---|---|---|---|
| current native/Tesseract/FormulaRegion | project runtime | existing project configuration | pass |
| Docling 2.117.0 | isolated Conda environment | explicit pre-provisioned artifacts, offline mode | pass (MIT metadata) |
| MinerU 3.4.4 | isolated Conda environment | local pipeline, CPU, offline mode | blocked (non-standard license) |

No parser was allowed to call an external API. MinerU's local CLI used only a
loopback endpoint; the network audit observed zero external hosts and zero
external parser requests.

## Parser Metrics

| Metric | Current | Docling | MinerU |
|---|---:|---:|---:|
| Parse success | 0.8182 | 1.0000 | 1.0000 |
| Reading order (mean where defined) | 0.7778 | 0.9802 | 0.9762 |
| Heading-definition integrity | 1.0000 | 1.0000 | 1.0000 |
| Page provenance completeness | 0.8182 | 1.0000 | 1.0000 |
| Block provenance completeness | 0.8182 | 1.0000 | 1.0000 |
| BBox provenance completeness | 0.0000 | 1.0000 | 1.0000 |
| Table retention (simple + mixed) | 0.0000 | 0.5000 | 0.5000 |
| Formula structure retention | 0.0000 | 0.0000 | 0.0000 |
| Repeated header/footer filter | 0.0000 | 1.0000 | 1.0000 |
| Duplicate body blocks | 0 | 0 | 0 |
| Median runtime | 32.42 ms | 5,049.68 ms | 10,366.44 ms |
| Peak RSS | 76.83 MB | 2,446.58 MB | 1,830.62 MB |

`Parse success` requires non-empty governed content, not merely a zero process
exit code. The current parser's scanned English and Chinese runs exited cleanly
but produced no eligible content, so both correctly fail that metric.

Aggregate values do not authorize routing. The selection manifest separately
retains critical per-fixture gates:

| Critical fixture | Current | Docling | MinerU |
|---|---:|---:|---:|
| Two-column reading order | 1.0000 | 0.8214 | 0.7857 |
| Scanned English content success | false | true | true |
| Scanned Chinese content success | false | true | true |
| Simple table retention | 0.0000 | 1.0000 | 1.0000 |
| Mixed-layout table retention | 0.0000 | 0.0000 | 0.0000 |
| Formula structure retention | 0.0000 | 0.0000 | 0.0000 |
| Repeated header/footer filter | 0.0000 | 1.0000 | 1.0000 |

## Existing-pipeline Retrieval Impact

Normalized blocks were converted through
`knowledge_governance.build_knowledge_chunks_from_parse_blocks` and ranked by
the existing fixed local backend:

- model: `intfloat/multilingual-e5-small`;
- revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`;
- backend: `local_multilingual_e5_pytorch_cpu_v1`.

No new embedding abstraction, model, vector database, translation step, or
gold mapping was introduced. Gold concept IDs were used only after ranking to
calculate metrics.

| Parser | EN chunks | ZH chunks | hit@1 | hit@3 | MRR | No result |
|---|---:|---:|---:|---:|---:|---:|
| Current | 2 | 2 | 0.1000 | 0.1000 | 0.1000 | 0 |
| Docling | 11 | 11 | 0.5000 | 0.6000 | 0.5500 | 0 |
| MinerU | 11 | 2 | 0.1000 | 0.1000 | 0.1000 | 0 |

Docling materially improves concept-preserving chunk construction and the
controlled downstream retrieval baseline, but `hit@3 = 0.6000` is not a claim
of broad product quality. It establishes a conditional adapter candidate only.

## Architecture Boundary

Before this task:

```text
PDF -> current parser/OCR/layout diagnostics -> parse blocks
    -> existing heading-aware KnowledgeChunk builder
    -> existing multilingual retrieval
```

This task adds only an offline comparison path:

```text
synthetic PDF
  -> isolated current / Docling / MinerU probe
  -> neutral evaluation blocks
  -> existing KnowledgeChunk builder
  -> existing multilingual retrieval
  -> metric and selection artifacts
```

Production remains unchanged. The ordered next task may add:

```text
production PDF
  -> existing parser adapter and document-quality router
       -> simple digital: current native parser
       -> scanned or validated simple-table: Docling candidate
       -> formula: compose existing FormulaRegion
       -> failed class gate: current fallback or fail closed
  -> existing parse blocks -> existing KnowledgeChunk -> existing retrieval
```

The PDF selection interface and concept learning card are deliberately not
changed here. Direct PDF text-layer selection remains an input mechanism; the
student-facing concept learning card remains the intended output and will be
implemented only after the parser adapter is closed.

## Safety

- Application external API used: false.
- External parser request count: 0.
- Real Provider requests: 0.
- Real credentials read: false.
- Private fixture used: false.
- Incident database accessed: false.
- Production parser changed: false.
- Production adapter changed: false.
- Model/cache tracked: false.
- Request/response/complete source bodies stored in artifacts: false.

## Artifacts

- `14B-controlled-parser-benchmark-results.json`
  - SHA-256: `293abe451b713f9f68d354f5dc8f6472760558a06104d7aba248e426429cad5d`
- `14B-controlled-parser-benchmark-matrix.csv`
  - SHA-256: `62908931e193141407e832323a5048d98e860cc4d9ed3426e6674324386ac6d0`
- `14B-parser-selection-manifest.json`
  - SHA-256: `7eddca05ac7c0aa72e6b5d4c28a567960768de5a339c17404cc22e65d6ec6232`

## Verification

- New and related parser/layout/chunk tests: `66 passed, 1 skipped`.
- Full pytest in the task runtime: `1722 passed, 5 skipped`.
- `dev_check` in the canonical runtime: `1720 passed, 7 skipped`; migration
  and backend API smoke passed. The two additional skips reflect optional
  layout-runtime availability in that separately pinned runtime, not failures.
- Release safety: pass.
- `git diff --check`: pass.
- Cross-Corpus V2 frozen hashes remain:
  - manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`;
  - gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`;
  - English bundle: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`;
  - Chinese bundle: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`.
- Accident database before/final:
  - SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`;
  - size: `1015808`;
  - mtime: `1785496597`;
  - WAL/SHM: absent/absent.

## Next Ordered Step

Add a bounded Docling adapter through the existing production parser contract,
with explicit document-class routing, existing FormulaRegion composition,
fallback/fail-closed behavior, offline model provisioning, resource bounds,
and no change to KnowledgeChunk or retrieval semantics. Do not begin the PDF.js
reader or concept-card redesign until that adapter task is merged and verified.
