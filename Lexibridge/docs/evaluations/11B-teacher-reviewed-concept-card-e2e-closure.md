# Task 11B: Teacher-reviewed Concept Card Publication E2E Closure

- Status: `TEACHER_REVIEWED_CONCEPT_CARD_E2E_CLOSED`
- Baseline commit: `74fb3d34f8de6dc66e1cb74a9cefafb94725281b`
- Branch: `feature/teacher-reviewed-concept-card-e2e-11b`
- Synthetic course: `Introductory Physics 11B`
- Production parser/provider changed: `False`
- Database schema changed: `False`

## Initial Breakpoints

| Breakpoint | Evidence | Resolution |
|---|---|---|
| Separate uploaded Chinese course material did not contribute explicit Chinese candidates | `backend/services/chinese_term_candidates.py::find_candidates_from_bilingual_chunks` only searched governed `mixed` bilingual chunks | Extended the governed search scopes to also inspect `zh` `chinese_reference_material` chunks for explicit bilingual patterns such as `动量（Momentum）` |
| Draft ConceptAlignmentCard evidence preserved only chunk IDs | `backend/services/concept_card_drafts.py::create_or_reuse_prepared_concept_card_draft` wrote `{"chunk_uid": ...}` only | Draft creation now enriches evidence refs from `KnowledgeChunk` and `KnowledgeSource` when called from Formal workflow processing |
| Upload-to-publication had no single synthetic E2E proof | Existing tests covered route slices and demo flow, but not separate EN/ZH upload through ingestion, Formal worker, review, publication, feedback, and teacher queue in one path | Added `tests/test_teacher_reviewed_concept_card_publication_e2e.py` |

## Implemented Workflow

```text
teacher creates course
→ teacher uploads synthetic EN source
→ teacher uploads synthetic ZH source
→ document ingestion background job creates governed KnowledgeSource / KnowledgeChunk
→ teacher starts Formal Alignment Workflow from EN source
→ Formal worker prepares items with EN evidence and explicit ZH candidate evidence
→ draft ConceptAlignmentCards enter needs_review
→ teacher edits and approves one card
→ teacher rejects one card
→ enrolled student sees only the approved card
→ student submits feedback on the approved card
→ teacher feedback queue returns that feedback
```

## Synthetic Scenario

English source:

```text
Momentum is defined as the product of mass and velocity.
Acceleration is defined as the rate of change of velocity.
```

Chinese source:

```text
动量（Momentum）是物体质量与速度的乘积。
加速度（Acceleration）是速度随时间变化的率。
```

The sources are created only inside pytest's isolated SQLite database. They are not seed data and are not written to production files.

## API And Service Paths

| Stage | Endpoint / Service | Evidence |
|---|---|---|
| Course creation | `POST /api/courses` | E2E test creates the synthetic course through the API |
| Document upload | `POST /api/documents/upload` | Upload returns queued ingestion jobs for EN and ZH text files |
| Ingestion worker | `run_background_job(job_id)` → `backend/services/knowledge_ingestion.py` | Creates active governed `KnowledgeSource` and `KnowledgeChunk` rows |
| Formal run admission | `POST /api/document-alignment-runs` | Creates a `DocumentAlignmentWorkflowRun` and formal background job |
| Formal worker | `run_formal_worker_once()` → `backend/services/document_alignment_processing_orchestrator.py` | Produces `needs_review` items and draft cards |
| Chinese candidate evidence | `backend/services/chinese_term_candidates.py::find_candidates_from_bilingual_chunks` | Finds explicit candidates in governed Chinese chunks |
| Draft evidence persistence | `backend/services/concept_card_drafts.py::create_or_reuse_prepared_concept_card_draft` | Stores bounded evidence provenance for EN and ZH chunk refs |
| Teacher review | `POST /api/concept-cards/<card_uid>/review` | Approve and reject transitions are verified through API |
| Teacher edit | `PATCH /api/concept-cards/<card_uid>` | Teacher edits the approved card content before approval |
| Student publication | `GET /api/student/concept-cards` and `GET /api/student/concept-cards/<card_uid>` | Enrolled student sees only approved card |
| Student feedback | `POST /api/student/concept-cards/<card_uid>/feedback` | Persists feedback against the approved card |
| Teacher feedback queue | `GET /api/concept-cards/student-feedback-queue` | Teacher sees feedback for the authorized course |

## Authorization Matrix

| Action | Teacher | Enrolled Student | Non-enrolled Student | Other Teacher | Admin |
|---|---:|---:|---:|---:|---:|
| Upload course source | yes | no | no | no | yes |
| Start Formal workflow | yes | no | no | no | yes |
| View draft review queue | yes | no | no | no | yes |
| Approve/reject card | yes, with course review permission | no | no | no | yes, subject to policy |
| View approved student card | yes through review/admin APIs | yes | no | no | yes |
| View draft/rejected as student | no | no | no | no | no |
| Submit student feedback | no | yes, approved enrolled cards only | no | no | no |
| View course feedback queue | yes, with course permission | no | no | no | yes |

## Evidence And Provenance

Approved ConceptAlignmentCards retain separate English and Chinese evidence arrays. Each item includes:

- `chunk_uid`
- `source_uid`
- `source_title`
- `course`
- `chapter`
- `language`
- `source_role`
- `trust_level`
- `quality_status`
- `quality_flags`
- bounded `snippet`
- `parse_uid`
- `parse_block_uid`

Page and bbox are not guaranteed by the simple text upload path; this task does not fabricate them. When parser/page metadata exists in the source chunk, the same evidence payload can carry `source_locator`, `parse_uid`, and `parse_block_uid`.

## Frontend Flow

The existing frontend already contains the real API contracts for this loop:

- Teacher review queue and actions in `frontend/index.html` call `/api/concept-cards/review-queue`, `/api/concept-cards/<card_uid>`, `/api/concept-cards/<card_uid>/reviews`, and `/api/concept-cards/<card_uid>/review`.
- Teacher feedback queue calls `/api/concept-cards/student-feedback-queue` and triage endpoints.
- Student Concept Card page calls `/api/student/concept-cards`, `/api/student/concept-cards/<card_uid>`, `/api/student/concept-cards/<card_uid>/state`, and `/api/student/concept-cards/<card_uid>/feedback`.
- `tests/test_frontend_contract.py` verifies these API strings, data-test IDs, approved-only student copy, evidence sections, feedback form, and teacher queue controls.

No frontend mock data or UI rewrite was added for 11B.

## Test Double Boundary

The E2E test uses real Flask routes, authorization checks, ORM persistence, upload ingestion jobs, Formal workflow admission, worker logic, review routes, publication queries, and feedback routes.

Allowed deterministic boundaries:

- User/course setup uses test helpers and API setup routes in the isolated test database.
- Formal alignment provider remains the existing local/mock Formal provider. No external Provider is called.
- Asynchronous queue transport is collapsed by directly invoking the real worker functions.

The test does not mock review logic, student visibility, feedback persistence, course authorization, `KnowledgeSource`, `KnowledgeChunk`, or ConceptAlignmentCard publication.

## Database Protection

- `backend/lexibridge.db` is the known incident database and is not accepted as a normal baseline.
- Tests run under pytest configuration that injects a temporary SQLite `DATABASE_URL` before importing the backend app.
- This task does not run `scripts/migrate_db.py`, seed scripts, or `dev_check.py`.
- The expected incident hash must remain `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa` during finalization.

## Privacy And Network

- Provider requests: `0`
- External document API requests: `0`
- Document egress: `0`
- Private course data: `0`
- Model downloads: `0`

All course content is synthetic.

## Test Results

| Command | Result | Notes |
|---|---|---|
| `backend/.venv-macos/bin/python -m pytest tests/test_teacher_reviewed_concept_card_publication_e2e.py -q` | `1 passed` | Full synthetic EN/ZH upload-to-publication API E2E |
| Related API/service/frontend contract regression suite | `151 passed` | Includes Concept Card review, student cards, feedback, Formal API, knowledge ingestion, bilingual evidence workflow, and frontend contract tests |
| Full pytest with verified local OCR runtime configured | `1207 passed, 6 warnings` | Warnings are existing SQLAlchemy legacy API and PyMuPDF/SWIG deprecation warnings |
| `backend/.venv-macos/bin/python scripts/check_release_safety.py` | `Release safety check passed.` | `dev_check.py` was intentionally not run for this task because it is explicitly forbidden by the task database-protection rules |

## Remaining Limitations

- This task validates workflow closure, permissions, state lifecycle, and evidence preservation; it does not validate real AI semantic quality.
- Production embedding/vector retrieval remains outside this task.
- Complex PDF parsing and parser routing remain governed by prior parser tasks.
- Formula structure recognition, LaTeX, and MathML are not completed here.
- Simple text upload does not prove page/bbox provenance. Page/bbox should be asserted on parser paths that provide those fields.
- `scripts/migrate_db.py --help` safety remains a separate migration CLI hardening task.

## Final State

`TEACHER_REVIEWED_CONCEPT_CARD_E2E_CLOSED`
