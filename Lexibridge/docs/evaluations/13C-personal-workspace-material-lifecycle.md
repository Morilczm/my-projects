# Task 13C — Personal Workspace Material Lifecycle & Private Evidence Corpus

## Status

- Technical status: `PERSONAL_WORKSPACE_MATERIAL_LIFECYCLE_CLOSED`
- Quality status: `PERSONAL_EVIDENCE_CORPUS_BASELINE_ESTABLISHED`
- Baseline: `dac1aaa18dd078e6e433016032a2201ce7857a14`
- Task 13B ancestor: `146dae39c1c5cc7d9c82688ecb2cc176ac785bad`
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

This is a synthetic engineering baseline. It is not a real-student product
validation.

## Read-only production audit

Before Task 13C, the production call graph was:

`/api/documents/upload` → local/S3 storage abstraction →
`DocumentParseRecord`/`DocumentParseBlock` → Task 12J-A layout-aware chunks →
`KnowledgeSource`/`KnowledgeChunk` → `student_personal_kb`.

The Student Task 13B path separately read active, searchable
`KnowledgeSource` objects:

`/api/student/concept-materials` → bounded source chunks →
`/api/student/concept-queries` → existing bilingual evidence workflow →
`StudentConceptQuery` → `PersonalLearningRecord`.

The parser/index path already existed and was reused. The actual gaps were:

1. async personal ingestion did not propagate `authorization_status`,
   `license_status`, or student-search flags, so personal chunks could be
   persisted but invisible to the student's ConceptQuery;
2. no student-owned list/detail/delete lifecycle API existed;
3. deleting/inactivating a source made a historical Task 13B result disappear
   instead of preserving it as `SOURCE_UNAVAILABLE`;
4. the existing Personal Upload page was a generic document form rather than a
   focused Student My Workspace PDF lifecycle.

No second parser, chunker, index, retrieval service, alignment flow, card flow,
or review flow was created.

## Architecture changes

### Domain reuse and migration decision

`PersonalMaterial` is implemented as a product/service contract over the
existing `Document` aggregate. `Document` already stores owner, scope, filename,
hash, MIME/storage metadata, upload time, parse status, parse UID, errors, and
soft-deletion time. `DocumentParseRecord`, `KnowledgeVersion`,
`KnowledgeSource`, and `KnowledgeChunk` already supply parsing, version and
provenance records.

Consequently:

- no `PersonalMaterial` duplicate table was created;
- no database migration was required;
- `PersonalMaterialVersion` reuses `KnowledgeVersion`;
- evidence binding reuses `KnowledgeSource.document_id`,
  `KnowledgeChunk.source_uid`, and the existing Task 13B query binding.

### After call graph

`My Workspace` → existing `/api/documents/upload` in the `13C` personal PDF
contract → existing storage → existing background ingestion worker → existing
Task 12J-A parser/layout chunk adapter → private governed `KnowledgeSource` and
`KnowledgeChunk` → `student_personal_kb` → existing Task 13B material selector
and ConceptQuery → existing `PersonalLearningRecord`.

Student lifecycle reads and deletion use:

- `GET /api/student/personal-materials`
- `GET /api/student/personal-materials/{material_id}`
- `DELETE /api/student/personal-materials/{material_id}`

All three routes require the Student role and owner identity. Legacy generic
upload formats remain accepted through the compatibility upload route for
existing callers; the Task 13C Student product contract and My Workspace UI are
PDF-only.

## Personal evidence corpus

Personal governed sources now carry:

- `scope_type=personal`
- `visibility=private`
- `knowledge_base_type=student_personal_kb`
- `authorization_status=allowed_for_private_use`
- `license_status=restricted`
- `allow_student_search=true`
- `allow_derivative_cards=false`

Search permission and visibility remain independent: the source is searchable
only after the Task 13B owner scope check. Another student's private source and
private course data are never added to `allowed_source_uids`.

The selection order is:

1. eligible Chinese evidence owned by the Student in the active workspace;
2. platform-governed evidence only as an explicitly enabled fallback when the
   workspace has no eligible Chinese evidence.

Translation, glossary and Ollama hints remain generated, non-evidence hints.
They are not indexed as private Chinese evidence and cannot directly yield a
qualified or official result.

## Data lifecycle

| Event | Material | Knowledge source | Query behavior |
| --- | --- | --- | --- |
| upload | `UPLOADED` | pending | `NOT_READY` |
| worker processing | `PARSING` | pending | `NOT_READY` |
| governed ingest | `READY` | active/private | allowed for owner |
| parse failure | `FAILED` | blocked or absent | `NOT_READY` |
| owner delete | `DELETED` | deprecated | future query blocked |

Deletion is owner-only and idempotent. It:

- soft-deletes the `Document`;
- deprecates the governed source and chunks;
- disables search/index/card derivation admission;
- records a `KnowledgeVersion` and audit record;
- removes the stored object through the existing storage abstraction;
- retains `StudentConceptQuery` and `PersonalLearningRecord`.

Historical results remain readable by their owner and report
`source_availability=SOURCE_UNAVAILABLE` and
`evidence_availability=UNAVAILABLE`. Machine history is not rewritten.

## Permission matrix

| Operation | Owner Student | Other Student | Instructor | Reviewer |
| --- | ---: | ---: | ---: | ---: |
| list/read personal material | yes | no | no | no |
| query personal material | yes | no | no | no |
| delete personal material | yes | no | no | no |
| read personal query/note | yes | no | no | no |

Personal data does not enter a course corpus or Reviewer queue. No Instructor or
Reviewer feature was added.

## Provenance and failure behavior

The reused ingestion path retains source UID, parse UID, layout block UID,
page, heading/source locator, content hash, parser identity/version, quality
labels and bounded text.

Owned material that is not searchable/ready returns a Student-facing
`NOT_READY` result rather than an internal error. A real personal source whose
chunk lacks page/block provenance also fails closed. Unauthorized identities
continue to receive a non-disclosing not-found response.

## Student browser slice

The Student navigation now has **My Workspace**. The page provides:

- a PDF-only upload form;
- private lifecycle status (`UPLOADED`, `PARSING`, `READY`, `FAILED`);
- page and evidence-chunk counts;
- a transition to the shared Task 13B ConceptQuery page;
- owner deletion.

The browser E2E uses a synthetic PDF and exercises:

login → My Workspace → upload → existing worker → READY → existing shared
ConceptQuery flow → private/non-official result → save note → mark understood.

The existing Managed Course, Instructor and Reviewer flows remain separate.

## Engineering baseline

- targeted backend/frontend tests: `48 passed`
- Student Browser E2E: pass
- full Browser E2E: Student, Instructor and Reviewer `PASS`
- Personal PDF upload/parse/chunk/index: pass
- owner/other Student/Instructor access boundaries: pass
- deletion and historical `SOURCE_UNAVAILABLE`: pass
- existing Task 13B shared flow: pass
- full pytest: `1627 passed, 5 skipped`
- `scripts/dev_check.py`: pass (independent full pytest, migration and backend smoke)
- `scripts/check_release_safety.py`: pass
- `git diff --check`: pass
- external application API requests: `0`
- real Provider requests: `0`

Frozen Cross-Corpus V2 hashes remain:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Artifact hashes:

- `13C-personal-material-contract.json`:
  `4a27975a988e265cabd4389687b926b9bd15d77bf3b76f6c2b5472cd4890e8b2`
- `13C-permission-matrix.json`:
  `76ae62b7a825d23c6c100087f70f89300f300fbdab50435a3faf679fa3cba9ea`
- `13C-material-lifecycle-matrix.csv`:
  `84ef5d72406760bb7f3ae7e7b6d756a3adda1eaa0f6382906a461be15059f4e8`
- `13C-browser-e2e-result.json`:
  `c407e2ad8ad57b0f7f8b3299488655ac2e02723b887958f74edfe1c6df9d9472`

Accident database before/final:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: `absent / absent`
