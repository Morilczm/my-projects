# Task 14D — PDF.js Direct Concept Capture

## Status

- Technical status: `PDFJS_DIRECT_CONCEPT_CAPTURE_CONTRACT_CLOSED`
- Quality status: `PDFJS_DIRECT_CONCEPT_CAPTURE_BASELINE_ESTABLISHED`
- Baseline commit: `213b9beca5a939ac0152be34b82ea4a85a825fd5`
- PDF.js: `pdfjs-dist@6.2.108`
- Runtime delivery: self-hosted, same-origin, Apache-2.0
- Database migration: not required

This task changes only the student PDF input experience. It does not redesign
the concept learning result. The product output remains a concept learning
card; that presentation is the next ordered interface phase.

## Before and after

Before:

```text
authenticated PDF Blob -> browser iframe
page-aware governed chunks -> separate right-side parsed-text column
student selects parsed text -> existing ConceptQuery
```

After:

```text
authenticated PDF Blob
  -> self-hosted PDF.js worker
  -> same-page canvas + selectable TextLayer
  -> student directly selects text on the visual PDF page
  -> deterministic mapping to one governed chunk/span
  -> server revalidates source access, text and offsets
  -> existing ConceptQuery / alignment / private learning record
```

The iframe and simultaneous parsed-text selection column were removed. The
governed parsed-text view is now a fallback shown only when the original PDF
or PDF.js page cannot be used safely.

## Runtime and supply-chain contract

The repository vendors 202 PDF.js files (5.6 MiB): the minified main module,
worker, CMaps, standard fonts, WASM assets, license and a hash manifest.
Runtime resources are loaded only from the LexiBridge origin. The package is
pinned rather than loaded from a CDN.

Primary runtime hashes:

- vendor manifest: `7f7d4a17da3e1854c626184b36d864325d8e42ee9ba285db57696e2f46bcac48`;
- `pdf.mjs`: `e0be3863c23c8af2305b16548febd58e7f8874a460253317d7771cddbc1c0f6d`;
- `pdf.worker.mjs`: `0613f41490dd6aaceed7a93fbbd38c85e6d6aa60474b6588c6e7709cfbe18cb3`;
- license: `0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594`.

XFA and dynamic evaluation support are disabled. The reader module does not
fetch or inspect credentials; it receives the existing authenticated Blob URL
from the main application.

## Selection mapping contract

The browser text layer is an interaction surface, not authoritative evidence.
A selection must map to one `selectable=true` reader item with governed
source/page/block/chunk/span provenance.

The mapper:

- normalizes PDF whitespace and English case while retaining original
  character offsets;
- tolerates omitted layout whitespace between PDF text nodes only when the
  compact form still identifies one unique governed span;
- limits the raw selection to 180 characters;
- maps repeated same-page text only through a unique occurrence order;
- rejects missing, ambiguous, overlong, outside-layer and not-ready inputs;
- never chooses a different chunk, page, candidate or top-k substitute.

The output reuses the existing `source_uid`, `chunk_uid`, `selected_text`,
`selection_start` and `selection_end` ConceptQuery fields. The backend then
re-reads the authorized chunk and repeats exact validation. No server trust is
transferred to the frontend mapper.

## Shared workspace and privacy result

Personal and Managed Course materials use the same PDF.js reader, mapper,
ConceptQuery service and result path. Browser acceptance proved both paths:

| Contract | Personal | Managed Course |
| --- | --- | --- |
| authenticated PDF Blob | pass | pass |
| local PDF.js canvas/text layer | pass | pass |
| direct text selection | pass | pass |
| governed chunk/span mapping | pass | pass |
| existing alignment result | pass | pass |
| private/non-official result | pass | pass |

The Student file route still enforces exact personal ownership or active
course membership. Other Students and non-Student roles cannot use it. No
complete PDF, course source, Blob URL, credential or storage path is retained
in evaluation artifacts.

## Browser acceptance

Full Chromium E2E status: `PASS`.

- Student: 76 steps passed; Personal and Managed Course direct PDF selection,
  alignment and private notebook passed.
- Instructor: 7 steps passed; Reviewer navigation remained hidden and
  Reviewer prefetch count remained zero.
- Reviewer: 15 steps passed; review and fake draft flow passed without
  publication.
- Console errors: 0 across all flows.
- Page errors: 0 across all flows.
- External dependency requests: 0.
- The three explicit `example.invalid` probes were blocked as expected.

## Verification

- RED-first contract: six failures before the PDF.js modules and text-layer
  UI existed.
- Direct reader, mapping, ConceptQuery, workspace, access and privacy tests:
  `49 passed`.
- Full pytest with controlled loopback permission: `1741 passed, 7 skipped`.
- `dev_check`: pass; embedded pytest reported `1741 passed, 7 skipped`, then
  temporary-database migration and backend API smoke passed.
- Browser E2E: Student/Instructor/Reviewer pass.
- Release safety: pass.
- `git diff --check`: pass.

An initial sandbox-restricted pytest invocation could not bind loopback fake
HTTP servers and therefore was not used as the validation result. The same
suite passed completely under the project's controlled loopback test policy.

## Frozen boundaries and safety

- Parser and Docling routing: unchanged.
- KnowledgeChunk construction: unchanged.
- Retrieval, Chinese candidate generation, pairing, qualification and
  readiness: unchanged.
- Prompt and Provider transport: unchanged.
- Application external API requests: 0.
- Real Provider requests: 0.
- Real credentials read: false.
- Private course fixtures used: false.
- Model/cache tracked: false.

Frozen Cross-Corpus V2 hashes remain:

- manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`;
- gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`;
- English bundle: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`;
- Chinese bundle: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`.

Accident database before/final:

- SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`;
- size: 1015808;
- mtime: 1785496597;
- WAL/SHM: absent/absent.

## Artifacts

- `14D-pdfjs-runtime-manifest.json`:
  `2e5aba6036fb99d1e4d00629d5fc7e69f09923bdd57913c6bd93296866b9b47e`;
- `14D-selection-mapping-matrix.csv`:
  `afaefda31e8065134c13258680b4f644d0f9e444ab92ef8604d2659f49997798`;
- `14D-browser-e2e-result.json`:
  `656adbcbe34d0e29b2bf9928eb660ac5197210be15b13c9a8d921c6aa0c87060`.

## Next ordered step

Redesign the student result as a focused concept learning card: bilingual
term identity, bounded context, evidence, why-they-align, alternatives,
uncertainty and personal learning actions. Keep the PDF reader as the input
surface and do not move scoring, qualification or Provider decisions into the
card UI.
