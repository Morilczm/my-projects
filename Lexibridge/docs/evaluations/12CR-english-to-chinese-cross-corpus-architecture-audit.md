# Task 12C-R — English-to-Chinese Cross-Corpus Alignment Architecture Audit

Status: `CROSS_CORPUS_ALIGNMENT_ARCHITECTURE_AUDIT_COMPLETED`

## Executive conclusion

The production system can ingest an English course source and a separately
uploaded Chinese reference source as independent governed `KnowledgeSource`
and `KnowledgeChunk` records. Language and source-role filtering are real and
provenance can be persisted into a `ConceptAlignmentCard`.

The core cross-corpus alignment path is nevertheless incomplete. Given an
English-only course source, production has no cross-language discovery query,
no mechanism that identifies a standard term from monolingual Chinese prose,
and no pre-Provider semantic pairing step. Candidate discovery passes the
English term unchanged into lexical search over Chinese or mixed-language
chunks. It can then produce a Chinese candidate only from:

1. an existing `ConceptAlignmentCard` with the same English term;
2. an existing legacy term/terminology record with the same English term; or
3. a Chinese/mixed chunk that repeats the English term in an inline bilingual
   surface form.

Therefore, when the English course material is English-only and no prior
English-to-Chinese mapping exists, the current Formal Workflow cannot produce
a standard Chinese term from an independent monolingual Chinese source.
The dominant missing capability is
`CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_MISSING`.

The frozen benchmark does not validate the intended core architecture. Its two
English and two Chinese source records are physically distinct, but all four
are generated from the same gold rows and parallel templates. Every Chinese
definition contains the exact English gold term in the form
`English term 即 Chinese definition`. Historical Chinese retrieval hit@3 =
1.0000 is consequently a bilingual keyword/template self-match, not evidence
of cross-language semantic retrieval.

The next task should first rebuild the benchmark with English-only course
material and an independently authored monolingual Chinese reference source.
Production retrieval, term identification, and pairing repairs should not be
selected against the current leaking fixture.

Task 12C-R changed no production files and made zero Provider requests.

## Product target and audited production path

The intended product path is:

```text
English course material
→ governed English source/chunks
→ English technical-term extraction and bounded admission
→ independent governed Chinese source retrieval
→ Chinese standard-term identification
→ English/Chinese concept-scope comparison
→ evidence qualification
→ ConceptAlignmentCard with EN/ZH provenance
```

The current implemented path is:

```text
English source/chunks
→ English candidate extraction
→ unchanged English-term lexical search over zh/mixed chunks
→ existing exact mapping OR inline bilingual regex candidate
→ score/UID/text selection
→ lexical EN/ZH evidence-presence gate
→ needs-review draft
→ optional later Provider verification
```

The second path is not a complete implementation of the first.

## Production call graph

| # | Route/job/service | Function | Input DTO | Output DTO | Persistence |
| ---: | --- | --- | --- | --- | --- |
| 1 | `POST /api/documents/upload` | `backend/app.py::upload_document` | multipart file/course/language/source metadata | upload/job response | `Document`, `IngestionJob`, `BackgroundJob` |
| 2 | `document_ingestion` job | `backend/app.py::process_document_ingestion_job` | job payload + `Document` | ingestion result | parse records, `KnowledgeSource`, `KnowledgeChunk` |
| 3 | `POST /api/document-alignment-runs` | `create_document_alignment_run` | `StartDocumentAlignmentWorkflowCommand` | `StartDocumentAlignmentWorkflowResult` | workflow run + formal background job |
| 4 | Formal worker bootstrap | `bootstrap_document_alignment_workflow_items` | `BootstrapDocumentAlignmentItemsCommand` | `BootstrapDocumentAlignmentItemsResult` | `DocumentAlignmentWorkflowItem` |
| 5 | English extraction/governance | `extract_chunk_scoped_term_candidates` | governed chunk snapshots | `ChunkScopedTermCandidateExtractionResult` | admitted items and explicit overflow metadata |
| 6 | Per-item preparation | `prepare_document_alignment_item` | `PrepareDocumentAlignmentItemCommand` | `PrepareDocumentAlignmentItemResult` | no preparation commit |
| 7 | Chinese candidate generation | `generate_chinese_term_candidates` | English term, course/chapter, governed models | `ChineseTermCandidateResult` | none |
| 8 | Chinese-source discovery | `find_candidates_from_bilingual_chunks` → `search_evidence` | unchanged English term + `zh/mixed` filters | `EvidenceSearchResult` | none |
| 9 | Inline candidate extraction | `extract_chinese_candidates_from_text_around_english_term` | retrieved snippet + exact English term | regex candidate dictionaries | none |
| 10 | Candidate selection | `select_primary_chinese_candidate` | ranked candidates | one candidate | candidate reference enters prepared input |
| 11 | EN/ZH evidence retrieval | `retrieve_bilingual_evidence` | English term + selected Chinese string | `BilingualEvidenceResult` | none |
| 12 | Draft creation | `create_or_reuse_prepared_concept_card_draft` | prepared terms/evidence refs | `PreparedConceptCardDraftResult` | `ConceptAlignmentCard` |
| 13 | Later verification | `execute_document_alignment_item_verification` | `ExecuteDocumentAlignmentItemVerificationCommand` | verification result | verification run/card fields |

The machine-readable version is
`12CR-production-alignment-callgraph.json`.

## Chinese source model

`KnowledgeSource` and `KnowledgeChunk` both have a `language` field. English
and Chinese sources are independent rows with independent `source_uid`,
`parse_uid`, document identity, quality state, and chunk identity. Production
roles include `english_course_material`, `chinese_reference_material`,
`bilingual_reference`, and private-material variants.

Teachers can upload a Chinese reference independently through
`POST /api/knowledge/upload` or the general document-upload path with
`language=zh`. Governed ingestion derives `source_role` from language and
stores the source and chunks independently. There is no bundled default
production Chinese corpus and no production synthetic Chinese source.

The Formal Workflow does not require the initiating English document itself to
contain Chinese. It does, however, require some governed source to make a
Chinese candidate available. With no Chinese source and no existing mapping,
candidate generation returns no candidate and preparation fails closed with
`DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE`.

Language filtering is effective rather than filename-based:

- candidate discovery searches `mixed/bilingual_reference` and
  `zh/chinese_reference_material` scopes;
- Chinese evidence retrieval prioritizes
  `language=zh, source_role=chinese_reference_material`;
- `should_include_chunk_as_evidence` checks both chunk and source metadata;
- English sources are not admitted as Chinese sources when those filters are
  applied.

An inline bilingual shortcut exists, but it is optional surface-pattern logic,
not an independent Chinese-term identifier.

Final card evidence can retain `source_uid`, `chunk_uid`, language,
source-role, parse, quality, and locator information. Provenance persistence is
implemented, although provenance alone cannot make a selected pair correct.

## Frozen benchmark integrity

Frozen identity remained:

- Corpus SHA-256:
  `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- Gold SHA-256:
  `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`

Integrity findings:

| Question | Finding |
| --- | --- |
| English sources | 2 |
| Chinese sources | 2 |
| Physically separate records | yes |
| Independently authored corpora | no |
| Parallel template mirror | yes |
| Inline `English term 即 Chinese definition` rows | 25/25 |
| English source contains Chinese gold terms | no |
| Chinese source contains English gold terms | 25/25 |
| Gold and corpus share generator constants | yes, same dataset module and `GOLD_ROWS` |
| Concept-specific source-ID leakage | no |
| Domain hints in source IDs | yes (`mechanics`, `electricity`) |
| Fixed-order mapping used by production | no |
| English keyword/template leakage | yes, 25/25 |
| Real English slide + independent Chinese textbook simulation | no |

The benchmark can support conclusions about synthetic English extraction,
source-language governance, and the inline bilingual regex behavior. It cannot
support conclusions about independent Chinese-textbook retrieval, monolingual
Chinese standard-term identification, cross-language semantic pairing, or
general course-PDF quality.

## Retrieval query construction

For all 25 concepts, Chinese candidate discovery constructs the same effective
query:

```text
query text: exact system-derived English candidate
query language: English
English context/definition used: no
translation: no
filters: language=zh or mixed; corresponding Chinese/bilingual source role
ranking: lexical phrase/token overlap plus source/course/trust features
```

There is no translation, bilingual dictionary expansion, multilingual
embedding, semantic reranking, or English-definition query. `search_evidence`
uses lexical phrase and token containment.

Every frozen Chinese definition repeats its English term. The exact English
query can therefore directly hit the gold-bearing Chinese fixture chunk. The
25-row audit preserves retrieved source/chunk IDs and ranks. The prior 12C.1
artifact did not persist raw retrieval scores. The new matrix therefore marks
each score as a deterministic reconstruction from the production
`lexical-v1` score inputs for the exact gold-bearing fixture chunk, rather than
misrepresenting it as a value persisted by 12C.1.

Historical candidate-source retrieval hit@1/hit@3/MRR =
0.6000/1.0000/0.8000 must be interpreted as English-keyword retrieval over a
bilingual synthetic template. It is not a valid cross-language semantic
retrieval measurement.

No production shortcut uses benchmark concept ID, source order, or a fixed
gold mapping. The leakage is in fixture content and shared template
construction, not in production reading scorer metadata.

## Chinese standard-term identification

Production mechanisms were audited as follows:

| Mechanism | Present? | Behavior |
| --- | --- | --- |
| Chinese heading/definition-subject extraction | no | no monolingual Chinese standard-term extractor |
| Structured dictionary/terminology store | partial | existing cards and legacy records can provide an exact English-keyed mapping |
| Inline bilingual regex | yes | requires English term and Chinese text in the same snippet |
| Model-generated candidate | no | candidate generation does not call a model |
| Source metadata term | no | metadata affects governance/scoring, not term identity |
| Arbitrary retrieved fragment used as term | no | current chunk path still requires the inline regex |

Candidate confidence is a deterministic source/trust/course/pattern score. It
is not semantic alignment confidence. Candidate provenance includes source and
chunk IDs, but the failure contract contains no independent monolingual
Chinese-term reason code beyond the generic unavailable result.

Direct answer: when courseware contains only English, production can generate
a Chinese standard term only if a previously stored English-keyed mapping
already exists or the independent Chinese source itself repeats the English
term in one of the supported bilingual patterns. From a normal monolingual
Chinese textbook alone, it cannot.

Status: `CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_MISSING`.

## Bilingual semantic pairing

Before Provider verification, pairing is candidate selection rather than
concept comparison. `select_primary_chinese_candidate` sorts by:

1. descending candidate score;
2. candidate UID;
3. case-folded Chinese text.

The score includes exact English lookup, course/chapter, source trust/role,
inline-pattern presence, repeat support, and penalties. It does not compare:

- English and Chinese definitions;
- concept scope;
- semantic embeddings;
- translation equivalence;
- discipline-specific neighboring concepts;
- abbreviation meaning.

Consequences:

- it cannot semantically distinguish `electric field` from
  `electric field strength`;
- it cannot semantically distinguish `angular velocity` from
  `angular acceleration`;
- when only one candidate exists, it is selected directly;
- `concept_scope` is carried into evidence workflow input but is not used to
  compare the two concepts;
- tie-breaking is deterministic within persisted identities;
- candidate absence and evidence absence fail closed, but an unsupported
  semantic pair has no pre-Provider fail-closed decision;
- no semantic pairing rationale is persisted at this stage;
- without a Provider, preparation can run and create a needs-review draft, but
  alignment remains explicitly unverified.

A later Provider verification boundary can assess alignment, but Task 12C-R
made no Provider request and that later possibility does not make the
candidate-selection step a semantic pairing mechanism.

Status: `CROSS_CORPUS_SEMANTIC_PAIRING_MISSING`.

## Evidence readiness and the 5/25 subset

The five provider-ready concepts are the electricity concepts. For each ready
item, preparation has:

- one system-derived English term;
- one selected Chinese candidate string;
- governed English evidence references;
- governed Chinese evidence references;
- source/chunk provenance;
- a persisted provider/model/prompt selection for a possible later call.

The callgraph artifact records, for each of those five items, the selected
English term, bounded Chinese candidate summary, candidate confidence,
candidate source/chunk refs, prepared English/Chinese evidence refs, and the
`prepared` readiness status. No source text is persisted in that audit.

Readiness does **not** require the selected Chinese term to match benchmark
gold and does not require pre-Provider semantic equivalence. In the frozen
fixture, all five selected Chinese strings are overlong inline definition
fragments. Thus provider-ready 5/25 means “structurally ready for later
verification,” not “five correct alignments.”

The five-item electricity source also fits within the frozen evidence limits
and source-chunk scope, whereas the larger Mechanics source is affected by
lexical top-k/source-ref selection. This makes readiness a conditional
structural subset. It must not replace the original 25-item denominator.

## Capability matrix

| Capability | Status |
| --- | --- |
| `ENGLISH_TERM_EXTRACTION` | `IMPLEMENTED_AND_VALIDATED` |
| `INDEPENDENT_CHINESE_SOURCE_INGESTION` | `IMPLEMENTED_NOT_VALIDATED` |
| `CROSS_LANGUAGE_QUERY_CONSTRUCTION` | `MISSING` |
| `CHINESE_SOURCE_FILTERING` | `IMPLEMENTED_AND_VALIDATED` |
| `CHINESE_EVIDENCE_RETRIEVAL` | `PARTIALLY_IMPLEMENTED` |
| `CHINESE_STANDARD_TERM_IDENTIFICATION` | `MISSING` |
| `BILINGUAL_SEMANTIC_PAIRING` | `MISSING` |
| `EVIDENCE_QUALIFICATION` | `PARTIALLY_IMPLEMENTED` |
| `PROVENANCE_PERSISTENCE` | `IMPLEMENTED_AND_VALIDATED` |
| `INLINE_BILINGUAL_FALLBACK` | `FIXTURE_ONLY` |

Status totals:

- `IMPLEMENTED_AND_VALIDATED`: 3
- `IMPLEMENTED_NOT_VALIDATED`: 1
- `PARTIALLY_IMPLEMENTED`: 2
- `FIXTURE_ONLY`: 1
- `MISSING`: 3
- `BLOCKED`: 0

The complete matrix records production function, relevant tests, evidence,
limitations, and next-step recommendation for every capability.

## Inline path versus core path

The inline path assumes that one chunk contains both the exact English term and
the adjacent Chinese expression. It is useful as an optional fallback for
bilingual reference material.

The core path must work when:

- the English source contains no Chinese;
- the Chinese source contains no English term;
- source structure and ordering differ;
- multiple neighboring Chinese concepts are retrievable;
- terminology must be identified from Chinese headings, definition subjects,
  or a governed lexicon;
- semantic equivalence must be tested using both contexts.

The frozen benchmark exercises the first path and not the second.

## Fixture leakage and survivor bias

Fixture leakage occurs because the exact English query is embedded in every
gold-bearing Chinese definition and because corpus/gold share generator
constants. It does not arise from production reading gold IDs or aliases.

All audit funnels retain the original denominator:

| Population | Count | Denominator |
| --- | ---: | ---: |
| English exact matched | 25 | 25 |
| Gold-bearing bilingual fixture chunk retrieved top3 | 25 | 25 |
| Correct standard Chinese term identified | 0 | 25 |
| Semantic pair established pre-Provider | 0 | 25 |
| Structurally provider-ready | 5 | 25 |

The provider-ready subset is conditionally selected by evidence preparation
and does not establish Chinese correctness. Reporting accuracy only on that
subset would introduce survivor bias.

## What is complete and what is missing

Implemented foundations:

- English document ingestion and deterministic term extraction;
- bounded candidate admission;
- independent governed English/Chinese source records;
- language/source-role filtering;
- lexical Chinese evidence lookup once a Chinese string is known;
- structural evidence gating;
- EN/ZH source/chunk provenance persistence;
- an inline bilingual fallback.

Missing core capabilities:

- cross-language discovery query construction;
- standard-term identification from independent monolingual Chinese material;
- semantic English/Chinese concept comparison before readiness;
- a benchmark capable of measuring those capabilities.

## Recommended next task

The single priority is:

**Rebuild the frozen benchmark to represent English-only course material plus
an independently authored monolingual Chinese knowledge source.**

The rebuilt benchmark should remove English gold terms from Chinese chunks,
avoid shared definition templates and order, include neighboring concepts, and
score retrieval, Chinese term identification, semantic pairing, readiness, and
provenance as separate stages. Only then should the project decide whether the
first production repair belongs in retrieval/query construction, Chinese
standard-term identification, or pairing.

## RED/GREEN and safety

RED failed at collection because the evaluation-only audit module did not
exist. The focused GREEN run passed 9 tests. The required targeted regression
passed 48 tests, and release safety passed.

The audit runner:

- configures a repository-external temporary SQLite database before importing
  the production app through the provider-free frozen diagnostic harness;
- reruns ingestion, candidate discovery, evidence preparation, and provenance
  tracing without executing verification;
- checks the incident database before and after but never uses it as the
  evaluation database;
- does not read `DEEPSEEK_API_KEY`;
- makes zero Provider requests;
- changes no production file, threshold, corpus, gold, alias, or schema.

The incident database remained identical before and after:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: 1015808
- mtime: 1785496597
- WAL: absent
- SHM: absent

## Artifacts

- `12CR-production-alignment-callgraph.json`  
  SHA-256:
  `5701ac5ddd1f3499dd431c07d30db1b75309fd9874710e9a62616f5bdf8e5043`
- `12CR-cross-corpus-capability-matrix.json`  
  SHA-256:
  `98b5202fd18ebda63382cf3cdf155574b6a5c02cdb4f6ada36e3ac9fc9028712`
- `12CR-benchmark-integrity-audit.json`  
  SHA-256:
  `6f5aeab7cd4158aad25f694366b3c436640a3c561fda1a302a05da2a65e4173a`
- `12CR-concept-flow-matrix.csv`  
  SHA-256:
  `68a462e944c3e8a6a5cff872baee51e1d629918ec10a45e64f256942f0e3e6eb`

Artifacts contain bounded query summaries and governed identifiers, not full
source text, credentials, machine-absolute paths, private files, or incident
database contents.
