# Task 12J-A — Layout-Aware Course Material Ingestion to Cross-Language Evidence Retrieval

## Executive conclusion

**Technical status:** `LAYOUT_AWARE_INGESTION_RETRIEVAL_CONTRACT_CLOSED`

**Quality status:** `LAYOUT_AWARE_INGESTION_RETRIEVAL_BASELINE_ESTABLISHED`

The existing upload, parse-quality, governed knowledge, and Task 12D retrieval
abstractions are now connected by a concept-preserving layout-to-chunk adapter.
The implementation does not create a second RAG system, change the qualified
embedding model, or call a translation or real Provider.

## Exact root cause and production call graph

The production upload path already invoked layout parsing and governed
ingestion, but `build_knowledge_chunks_from_parse_blocks` created one
`KnowledgeChunk` per parse block. Layout was therefore preserved mainly as
diagnostic block metadata: a title and its definition became separate chunks,
fixed block boundaries—not concept boundaries—controlled evidence construction,
and multi-block page/heading/span provenance did not exist at the chunk level.

Before:

```text
POST /api/documents/upload
→ app.upload_document
→ app.create_parse_record_for_saved_file
→ document_parse_quality.parse_document_with_quality
→ document_parse_quality._parse_pdf_with_layout
→ DocumentParseRecord + DocumentParseBlock
→ knowledge_ingestion.ingest_parse_record_to_governed_knowledge
→ knowledge_governance.build_knowledge_chunks_from_parse_blocks
→ one parse block = one KnowledgeChunk
→ KnowledgeChunk persistence
→ bilingual_evidence_workflow.retrieve_cross_language_chinese_evidence
→ cross_language_retrieval.rank_chinese_passages
→ evidence DTO → Formal preparation
```

After:

```text
POST /api/documents/upload
→ unchanged storage, parse selection, OCR and quality gates
→ governed layout blocks
→ _layout_chunk_payloads
   → deterministic reading order
   → header/footer/page-number/figure removal
   → duplicate block-UID removal
   → heading-started section boundaries
   → bounded section splitting and overlap
   → aggregate page/block/span provenance
→ build_knowledge_chunks_from_parse_blocks
→ existing KnowledgeSource/KnowledgeChunk persistence and dedup
→ existing governed Chinese-only Task 12D retrieval
→ existing evidence DTO and Formal preparation
```

The retrieval path reads active governed `KnowledgeChunk` rows directly and
uses the existing qualified multilingual embedding adapter at query time.
There is no new vector database or parallel index.

## Audited production behavior

- Route: `POST /api/documents/upload`.
- Storage: the existing storage service writes the accepted upload and returns
  its hash and storage metadata.
- Parser selection and OCR: `parse_document_with_quality` keeps the existing
  native/OCR/layout routing and quality gate.
- Layout normalization: `_parse_pdf_with_layout` persists page, bbox locator,
  layout type, provider, and risk flags in `DocumentParseBlock`.
- Persistence: `ingest_parse_record_to_governed_knowledge` creates or reuses a
  governed `KnowledgeSource`, then `create_knowledge_chunks` persists chunks and
  retains the existing content-hash duplicate status.
- Retrieval: `retrieve_cross_language_chinese_evidence` filters governed active
  Chinese sources/chunks and calls `rank_chinese_passages`.
- Formal input: `prepare_document_alignment_item` consumes the existing
  bilingual evidence workflow; it does not call `translate_provider`.

## Layout backend and fallback

The default deterministic rule-based layout backend uses embedded PDF text and
classifies title, text, list, table, formula, caption, header/footer, and page
number blocks. The optional DocLayout ONNX backend remains configuration-bound
and is not downloaded by tests or CI.

If layout analysis is unavailable, the pre-existing native parser fallback is
retained. The resulting chunks keep source locators and are explicitly marked
with `layout_fallback_native`; the fallback does not silently claim
layout-derived provenance.

## Chunk contract

The adapter uses these fixed bounds:

- maximum chunk length: 1,200 characters;
- overlap for an oversized section: 120 characters;
- minimum preferred split boundary: 12 characters.

A title/heading starts a section and is joined with following definition,
list, table, and formula blocks until the next heading. Obvious section
boundaries are never crossed. Header/footer, page-number, and figure noise do
not become primary evidence. Oversized sections are split deterministically at
bounded sentence/newline/space boundaries.

Every chunk carries:

- stable UUID5 chunk UID;
- source UID and language;
- page or page range;
- ordered layout block IDs;
- heading path (`source_section`);
- aggregate block type;
- bounded text and normalized content hash;
- chunk character span plus recoverable source block locators;
- parser/backend ID and version flags;
- quality/risk labels and formula block IDs.

Stable sorting and stable UID construction make repeated processing
deterministic. Duplicate block UIDs are removed before construction; existing
content-hash governance remains active at persistence.

## Translation and glossary boundary

The routed translation providers, Ollama adapter, and glossary remain outside
the Formal evidence path. Translation results now carry:

```text
generated=true
no_evidence=true
provenance_type=GENERATED_HINT
eligible_as_chinese_evidence=false
eligible_as_canonical_term=false
eligible_for_qualification=false
eligible_for_provider_readiness=false
```

The frozen legacy alignment route also propagates a bounded translation-hint
audit object and forces generated hints to pending quality control. A generated
translation or glossary suggestion cannot masquerade as an independent Chinese
source/chunk, become `QUALIFIED`, or become `READY`.

## Controlled fixture corpus

The evaluation creates PDF files only inside a repository-external temporary
directory and deletes them on completion:

- 2 synthetic English PDFs;
- 2 synthetic Chinese PDFs;
- 10 public physics concepts;
- 5 scope-confusion groups;
- no private course material;
- no complete English term string in the Chinese PDFs.

The groups are electric field/field strength, electric potential/potential
energy, angular velocity/angular acceleration, mass/weight, and
momentum/angular momentum. The deterministic CI backend distinguishes passages
only through shared public mathematical notation; it contains no English ↔
Chinese term dictionary, gold aliases, benchmark IDs, or document-order hint.
The production model contract remains
`intfloat/multilingual-e5-small` at revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`.

## Evaluation metrics

### Parsing

- sources succeeded/failed: 4/0;
- pages: 20;
- layout blocks: 64;
- parser: `pymupdf_layout_rule_based`;
- layout/OCR fallback count: 0.

### Chunking

- chunks: 20;
- average/median length: 72.25/69 characters;
- heading-definition integrity: 1.0000;
- cross-section contamination: 0;
- duplicate chunks: 0;
- provenance completeness: 1.0000;
- list/table/formula retention: true/true/true.

### Existing cross-language retrieval

- denominator: 10;
- hit@1: 1.0000;
- hit@3: 1.0000;
- MRR: 1.0000;
- no-result count: 0;
- correct evidence average rank: 1.0000.

These are deterministic synthetic integration metrics, not a replacement for
the frozen Cross-Corpus V2 quality baseline.

### Downstream smoke

- exact Chinese candidate generated: 10/10;
- bounded bilingual pair list generated: 10/10;
- evidence content-hash provenance retained: 10/10.

No qualification threshold, pairing weight, readiness policy, Prompt, or
Provider behavior was changed.

## Security and regression result

- external API used: false;
- real Provider requests: 0;
- real credentials read: false;
- private course material used: false;
- model/cache tracked: false;
- accident database accessed by tests/evaluation: false.
- targeted regression: 122 passed, 1 skipped;
- full pytest: 1,571 passed, 1 skipped;
- `scripts/dev_check.py`: passed;
- release safety: passed;
- `git diff --check`: passed.

The frozen V2 hashes remain:

- English: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Artifact hashes:

- `12JA-ingestion-results.json`:
  `43b547346d318a7ef173315fa835fd8de12815cbb16bd260574f3f99089e304c`
- `12JA-chunk-matrix.csv`:
  `9c5e1d3215d431d0e7dc9f62c82f5264f5206d1b29c626300982544a0c2275b3`
- `12JA-retrieval-results.json`:
  `49194407b90d92da7022c51265431a7728fb9fd7b4dd90e3b82a17aaed786036`
- `12JA-translation-boundary-audit.json`:
  `a3316e2445a207d3ecffadb4bab5069f45249d0215afb610a9da1adb9436ebee`

## Recommendation

The next task may evaluate the student-facing or teacher-facing experience
against this governed ingestion contract. It should not alter retrieval,
pairing, qualification, Prompt, or Provider policy merely to improve this
synthetic baseline.
