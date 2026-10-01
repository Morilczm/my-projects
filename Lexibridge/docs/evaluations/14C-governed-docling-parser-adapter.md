# Task 14C — Governed Docling Parser Adapter

## Status

- Technical status: `DOCLING_PARSER_ADAPTER_CONTRACT_CLOSED`
- Quality status: `DOCLING_PARSER_ADAPTER_OFFLINE_BASELINE_ESTABLISHED`
- Baseline commit: `0af9a40f96a1b25aa72ae31e8d8223da624cbd14`
- Selected parser: `docling@2.117.0`
- Routing policy: `conditional-docling-parser@1.0.0`
- Worker contract: `docling-layout-worker@1.0.0`

The task closes the production adapter contract established by the controlled
Task 14B comparison. It does not claim that Docling is a universal PDF parser,
nor that student-facing PDF selection and concept-card presentation are done.

## Before and after

Before:

```text
upload
  -> parse_document_with_quality
  -> native PyMuPDF or configured rule/ONNX layout provider
  -> OCR and FormulaRegion diagnostics
  -> DocumentParseBlock
  -> existing KnowledgeChunk
  -> existing retrieval
```

After:

```text
upload (course or personal; same route)
  -> parse_document_with_quality
  -> conditional-docling-parser@1.0.0
       -> ordinary digital: native PyMuPDF
       -> multi-column: current parser; Docling excluded
       -> scanned: isolated offline Docling
       -> simple vector table: isolated offline Docling
       -> unavailable/timeout/invalid/network: governed fallback
  -> existing FormulaRegion composition
  -> existing DocumentParseRecord / DocumentParseBlock
  -> existing KnowledgeChunk
  -> existing multilingual retrieval
```

No parallel ingestion, chunking, indexing, or retrieval system was created.
No database migration was required.

## Routing decision

| Document class | Production route | Reason |
| --- | --- | --- |
| simple digital PDF | existing native PyMuPDF | retain the fast, stable path |
| scanned PDF | Docling | passed the Task 14B scanned-fixture gate |
| simple vector-table PDF | Docling | retained the controlled table and improved chunks |
| multi-column PDF | existing path | Docling failed the controlled reading-order gate |
| formula content | selected parser plus existing FormulaRegion | Docling does not replace formula provenance |

The upload API cannot choose or disable the parser. The route is deployment
configuration plus deterministic document-class signals only.

## Adapter and isolation

`backend/services/docling_parser_adapter.py` performs local preflight,
document classification, subprocess isolation, bounds enforcement, and strict
output validation. `scripts/docling_parser_worker.py` is the only Docling
runtime entry point.

The worker:

- requires an absolute isolated Python executable;
- requires an absolute pre-provisioned model directory;
- disables remote services and remote model resolution;
- blocks non-loopback socket connections;
- receives no API key or authorization environment variables;
- writes only bounded layout JSON to a parent-owned temporary directory;
- never writes Markdown, full parser exports, or source text artifacts.

## Bounds and fail-closed reasons

Default resource limits are 50 MiB, 50 pages, 120 seconds, 16 MiB result JSON,
10,000 blocks, and 20,000 characters per block. The adapter rejects malformed
worker contracts, missing page/bbox provenance, out-of-page coordinates,
unknown block types, empty results, network attempts, and excessive outputs.

Stable reasons include:

- `DOCLING_RUNTIME_NOT_ABSOLUTE`;
- `DOCLING_RUNTIME_UNAVAILABLE`;
- `DOCLING_MODEL_ROOT_UNAVAILABLE`;
- `DOCLING_INPUT_SIZE_EXCEEDED`;
- `DOCLING_PAGE_LIMIT_EXCEEDED`;
- `DOCLING_TIMEOUT`;
- `DOCLING_EXTERNAL_REQUEST_DETECTED`;
- `DOCLING_OUTPUT_CONTRACT_INVALID`;
- `DOCLING_PROVENANCE_INVALID`;
- `DOCLING_PARSE_FAILED`.

## Provenance and quality semantics

Every admitted block has page, bbox, page dimensions, reading order, type, and
bounded text. The existing parse adapter serializes these as the existing
`page:<n>;bbox:...` locator. Tables remain table blocks. Parser identity is
audited as `docling_layout` with, for this acceptance,
`parse_quality_v1+docling@2.117.0`.

Scanned Docling output is recorded as `ocr_text_ok` with
`docling_ocr_completed`; the system does not run a second Tesseract pass.
FormulaRegion detection still runs and retains formula provenance.

## Controlled offline acceptance

Only synthetic Task 14B fixtures and the repository-external, pre-provisioned
Docling model directory were used.

| Fixture | Parser | Quality | Blocks | Chunks | Key result |
| --- | --- | --- | ---: | ---: | --- |
| single-column digital | `pymupdf_native` | `native_text_ok` | 1 | 1 | native route retained |
| simple table | `docling_layout` | `native_text_ok` | 1 | 1 | table type retained |
| scanned English | `docling_layout` | `ocr_text_ok` | 5 | 1 | OCR/layout provenance complete |

All admitted blocks had source locators. The worker observed zero external
requests. No application external API, LLM Provider, or credential was used.

## Verification

- Adapter/layout/parse targeted tests: `37 passed`.
- Combined parser, upload, OCR, KnowledgeChunk, Personal Material, retrieval,
  and Task 14B regressions: `98 passed, 1 skipped`.
- Full pytest: `1738 passed, 5 skipped`.
- `dev_check`: pass; its embedded pytest also reported `1738 passed, 5
  skipped`, followed by temporary-database migration and backend API smoke.
- Release safety: pass (standalone and within `dev_check`).
- `git diff --check`: pass.

## Frozen boundaries

- PDF reading UI and text selection: unchanged.
- KnowledgeChunk construction: unchanged.
- multilingual-e5-small model/revision: unchanged.
- retrieval, Chinese candidate generation, pairing, qualification, readiness,
  Prompt, and Provider transport: unchanged.
- Real Provider requests: `0`.
- Application external API requests: `0`.
- Real credentials read: `false`.
- Models/cache tracked: `false`.

Frozen Cross-Corpus V2 hashes remain:

- manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`;
- gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`;
- English bundle: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`;
- Chinese bundle: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`.

Accident database before/final:

- SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`;
- size: `1015808`;
- mtime: `1785496597`;
- WAL/SHM: absent/absent.

Artifact hashes:

- adapter contract: `191503af7ce47e67826c61c5720a847f783333533a5596fde2525843a8bed89d`;
- routing matrix: `5d93ae339caaebf7e8d9cc0b4e0a1339f9a4a0871cf87b2bef199c7dfce029e7`.

## Next ordered step

After this adapter change is reviewed and merged, implement PDF.js direct text
selection through the existing ConceptQuery span/provenance contract. Do not
combine that interface work with parser behavior changes. The concept learning
card remains the result/output phase after direct selection is closed.
