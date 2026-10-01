# Governed Docling Parser Adapter

## Purpose

LexiBridge keeps one document-ingestion pipeline. Docling is an optional,
offline parser behind the existing layout provider contract; it is not a new
RAG system, KnowledgeChunk implementation, or retrieval index.

The adapter policy is `conditional-docling-parser@1.0.0` and the worker
interchange contract is `docling-layout-worker@1.0.0`.

## Production flow

```text
upload / background ingestion / Personal Workspace material
  -> parse_document_with_quality
  -> cheap local PDF class router
       -> simple digital PDF: existing native PyMuPDF path
       -> multi-column PDF: existing path (Docling excluded)
       -> scanned PDF: bounded offline Docling adapter
       -> simple vector-table PDF: bounded offline Docling adapter
  -> existing formula-region detector
  -> existing DocumentParseRecord and DocumentParseBlock persistence
  -> existing heading-aware KnowledgeChunk builder
  -> existing governed index and multilingual retrieval
```

The upload API does not accept a parser override. Deployment configuration is
the only way to enable the conditional adapter.

## Why the route is conditional

Task 14B found Docling 2.117.0 to be the best eligible open-source candidate,
but not a universal replacement:

- it improved controlled retrieval for concept-preserving chunks;
- it parsed scanned fixtures and retained the simple table;
- it failed the controlled multi-column reading-order gate;
- formula semantics still require LexiBridge's existing FormulaRegion route.

The default remains the existing parser. Set `LAYOUT_PROVIDER` to
`conditional_docling` only in an environment that supplies the isolated
runtime and model directory.

## Local-only runtime contract

Required configuration:

- `DOCLING_PARSER_PYTHON`: absolute executable path to an isolated runtime;
- `DOCLING_MODEL_ROOT`: absolute path to pre-provisioned Docling artifacts.

The application does not install or download Docling models at request time.
The worker receives `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, disables
Docling remote services, and blocks non-loopback socket connections. The
subprocess environment is an allowlist and does not propagate API keys or
authorization values.

## Bounds and failure behavior

Defaults:

| Bound | Value |
| --- | ---: |
| input file | 50 MiB |
| pages | 50 |
| execution timeout | 120 seconds |
| worker JSON output | 16 MiB |
| layout blocks | 10,000 |
| text per block | 20,000 characters |

The adapter validates page, bbox, page dimensions, block type, text length,
output size, worker version, and external-request count. Missing or invalid
provenance fails closed. Runtime unavailability, timeout, malformed output,
network attempts, or parser failure return stable local reason codes and fall
back through the existing layout/native safety path.

## Provenance and downstream invariants

Docling blocks are normalized to the existing `LayoutBlock` contract. The
existing parse service creates its normal source locator:

```text
page:<n>;bbox:<x0>,<y0>,<x1>,<y1>
```

Table blocks retain `block_type=table`. Scanned documents record
`docling_ocr_completed` and `quality_status=ocr_text_ok` without starting a
second Tesseract pass. FormulaRegion detection runs after parser selection and
remains the formula provenance authority.

No schema migration is required. `DocumentParseRecord`, `DocumentParseBlock`,
`DocumentChunk`, `KnowledgeSource`, and `KnowledgeChunk` remain the single
production objects.

## Non-goals

This adapter does not change PDF reading or text selection UI, the multilingual
embedding model, retrieval, pairing, qualification, readiness, Provider
transport, or concept-card presentation. Those remain separate ordered tasks.
