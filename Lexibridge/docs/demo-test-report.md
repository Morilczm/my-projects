# LexiBridge AI Local MVP v0.8 Demo Test Report

## Test Objective

Verify that the local course-demo release behaves as an AI bilingual course knowledge alignment platform rather than a simple translation page. The test focuses on document ingestion, OCR status handling, term extraction quality, evidence retrieval boundaries, quality control routing, role permissions, personal workspace privacy, mock payment, and honest AI fallback behavior.

## Environment

- Backend: Flask + SQLite.
- Frontend: single-page HTML/CSS/JavaScript.
- OCR: local Tesseract/PaddleOCR when available; otherwise `needs_ocr_engine`.
- AI: DeepSeekProvider when configured; local heuristic/mock fallback for demo.
- Payment/email: mock local flow.

## Seed Accounts

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@lexibridge.local` | `Admin1234` |
| Teacher | `teacher@lexibridge.local` | `Teacher1234` |
| Student | `student@lexibridge.local` | `Student1234` |

## Tested File Types

| Type | Expected Result |
| --- | --- |
| TXT / Markdown | Native text extraction, chunking, term extraction. |
| DOCX | Paragraph/table extraction, chunking. |
| PPTX | Slide text/table extraction, slide number retained. |
| Digital PDF | PyMuPDF page text extraction, page number retained. |
| Scanned PDF | Text-poor pages rendered to images and sent to OCR. |
| JPG / PNG | Direct OCR. If OCR unavailable, no fake text is generated. |
| Mixed PDF | Digital text is extracted and image regions on the same page are also processed. |
| Formula image | Formula-like regions create `FormulaBlock`; LaTeX requires a Formula OCR provider. |

## OCR Acceptance Notes

- The system blocks `[OCR_REQUIRED]`, `[OCR_FALLBACK]`, `OCR_REQUIRED`, and `OCR_FALLBACK` from term extraction.
- If OCR is unavailable, image/scanned uploads return an OCR error state and do not create terminology cards from placeholder text.
- If OCR confidence is below 60, generated cards cannot be auto-approved.
- Tesseract/PaddleOCR are text OCR engines, not guaranteed formula OCR engines.
- If `FORMULA_OCR_PROVIDER=none`, formula regions return `needs_formula_ocr_engine` and no LaTeX is fabricated.
- `FormulaBlock` records are not sent into terminology extraction.

## Formula OCR Acceptance Notes

Expected local MVP behavior:

- `FORMULA_OCR_PROVIDER=none`: formula image creates a FormulaBlock with `needs_formula_ocr_engine`.
- `FORMULA_OCR_PROVIDER=mock`: no fake LaTeX is generated.
- Formula placeholders such as `[FormulaBlock #12]` are skipped by term extraction.
- LaTeX-like fragments such as `sqrt`, `frac`, `int`, `x^2`, and `e^{-x^2}` do not become `english_term`.
- Mixed PDF pages with selectable text still process image/formula regions.

## Signal Processing Manual Test

Teacher upload text:

```text
Convolution combines two signals to produce a third signal.
Fourier Transform converts a time-domain signal into a frequency-domain representation.
Angular frequency is measured in radians per second.
Wavelength is the spatial period of a wave.
```

Expected extraction:

- `Convolution`
- `Fourier Transform`
- `time-domain signal`
- `frequency-domain representation`
- `Angular frequency`
- `Wavelength`

Blocked examples:

- `Convolution combines two signals`
- `Hash Table uses`
- `OCR REQUIRED`
- `OCR FALLBACK`
- full sentence fragments

If no matching Chinese evidence exists in the selected course/global Chinese KB, generated cards must be `needs_more_evidence` or `pending_quality_control`, not `auto_approved`.

## Permission Tests

Expected results:

- No token calling `/api/terms/pending`: `401`.
- Student calling `/api/terms/clear-pending`: `403`.
- Teacher calling admin-only user APIs: `403`.
- Admin calling admin APIs: allowed.
- Student A personal document chunks are not visible to Student B.
- Teacher does not see student personal uploads in course KB or default QC.

## Retrieval Regression Results

Executed with `backend/.venv-macos/bin/python -m pytest tests/test_retrieval.py tests/test_evidence_scoring.py`.

Result:

```text
8 passed
```

Verified cases:

- `Fourier Transform` returns Fourier English evidence.
- `Fourier Transform` returns `傅里叶变换` Chinese evidence.
- `Hash Table` returns hash table English evidence.
- `Hash Table` returns `哈希表` Chinese evidence.
- `Convolution` returns `卷积` Chinese evidence.
- `Angular frequency` returns `角频率` Chinese evidence.
- `Fourier Transform` does not return `Hash Table` evidence.
- `Hash Table` does not return `傅里叶变换` evidence.
- `Collision Resolution` does not return `卷积` evidence.
- no matching Chinese/English evidence returns an empty list.
- stopword-only query does not create strong evidence.
- personal chunks are filtered by owner.
- mock/local AI cannot auto approve even with strong evidence.

## Alignment State Machine Regression Results

Executed with:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_alignment_status.py tests/test_card_generation.py tests/test_confidence_scoring.py
```

Result:

```text
13 passed
```

Verified cases:

- missing English evidence becomes `no_en_evidence + needs_more_evidence`.
- missing Chinese evidence becomes `no_zh_evidence + needs_more_evidence`.
- weak evidence becomes `pending_quality_control`.
- domain mismatch becomes `domain_mismatch + pending_quality_control`.
- OCR low confidence becomes `ocr_low_confidence + pending_quality_control`.
- formula OCR failure or missing Formula OCR becomes `formula_evidence_missing + pending_quality_control`.
- mock/local AI cannot create `auto_approved` cards.
- strong bilingual evidence plus live AI and `exact_match` can create `auto_approved`.
- rejected cards cannot be system-promoted back to `auto_approved`.
- `TerminologyCard` saves evidence snapshots, score breakdown, quality flags, retrieval version, and source alignment run.
- `AlignmentRun` records run-level statistics and is available through `/api/alignment/runs/<id>`.

Full regression was run with:

```bash
backend/.venv-macos/bin/python -m pytest
```

Result:

```text
28 passed, 5 warnings
```

## Evaluation Harness Regression Results

Executed with:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_evaluation.py tests/test_evaluation_metrics.py
```

Result:

```text
4 passed
```

Verified cases:

- Teacher/Admin can create an `EvaluationSet`.
- JSONL evaluation items can be imported.
- Invalid JSONL lines are skipped and reported.
- Split filtering works for `test`.
- `EvaluationRun` is written to the database.
- `EvaluationRun` stores metrics, `report_json`, and `report_markdown`.
- `no_evidence_forced_alignment_rate`, `auto_approval_error_rate`, `false_positive_rate`, extraction precision, and extraction recall are computed by service functions.
- Student cannot run evaluation.
- Teacher cannot run an evaluation set owned by another admin unless course permissions allow it.

Sample set:

- `docs/evaluation_sample.jsonl`
- 60 smoke items.
- 20 signal processing items.
- 20 data structure items.
- 20 mathematics / communication basics items.
- Includes negative evidence examples and formula-related items.

Local CLI sample run:

```bash
AI_PROVIDER=none DEEPSEEK_API_KEY= ALLOW_MOCK_AI=True \
backend/.venv-macos/bin/python scripts/run_evaluation.py \
  --set docs/evaluation_sample.jsonl \
  --split test \
  --name lexibridge_smoke_local_v1
```

Observed output:

```text
Imported: 60 skipped: 0
EvaluationRun ID: 4
extraction_precision: 0.2844
extraction_recall: 0.5167
evidence_accuracy: 0
alignment_accuracy: 0.0
false_positive_rate: 0.0
auto_approval_error_rate: 0
no_evidence_forced_alignment_rate: 0.0
release_gate: FAIL
```

Interpretation:

- The harness runs end to end and exposes weak local KB coverage.
- `no_evidence_forced_alignment_rate` stayed `0.0`, so the system did not force positive alignment without bilingual evidence.
- The gate failure is expected for the current 60-item smoke set because the local demo knowledge base is not a full gold evidence corpus.

## AI Provider Notes

DeepSeekProvider is the only live provider implemented. If DeepSeek is missing or fails, the backend logs the issue and cards show local heuristic/mock risk notes. Mock/local fallback cards are routed to QC and do not auto-approve.

## Current Limitations

- SQLite retrieval is local demo retrieval, not production semantic search.
- No real payment or SMTP integration.
- No real vector database.
- No ByrDocs, publisher, school library, or automatic textbook crawler is implemented.
- Tesseract/PaddleOCR must be installed separately for real image OCR.
- No real Formula OCR is active unless Mathpix or a local LaTeX OCR command is configured.
- Handwritten formulas, complex tables, and chart structure recognition are not promised.

## PR-5 Engineering Closure Results

Test time:

```text
2026-06-22 17:34:46 CST
```

Environment:

```text
Python 3.9.6
macOS 26.5.1
```

Commands executed:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python -m pytest tests/test_api_contract.py tests/test_auth.py tests/test_permissions.py tests/test_upload_security.py tests/test_personal_privacy.py tests/test_migrations.py
backend/.venv-macos/bin/python -m pytest
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260622.zip
```

Results:

```text
py_compile: passed
migrate_db.py: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
PR-5 regression subset: 25 passed
Full pytest suite: 57 passed, 5 warnings
Frontend JS syntax check: passed
Release package tests: 25 passed
Release package check: passed
```

OpenAPI contract:

- `docs/openapi.yaml` exists and parses as OpenAPI `3.0.3`.
- Core Auth, Course, Document, Knowledge, Alignment, Terminology, Quality Control, Evaluation, and Admin routes are represented.
- Error code enum matches `backend/app.py::ERROR_CODES`.
- Upload is declared as `multipart/form-data`.
- PDF export is declared as `application/pdf`.

Security and permission regression:

- Missing token returns `AUTH_REQUIRED`.
- Expired token returns `TOKEN_EXPIRED`.
- Student and Teacher cannot access `/api/admin/users`.
- Student cannot access `/api/quality-control`.
- Student cannot run evaluation.
- Teacher cannot run an unowned/unbound admin evaluation set.
- Student cannot trigger course-scope alignment.
- Teacher cannot search another teacher's course knowledge base.

Upload security regression:

- Allowed text upload succeeds with randomized safe filename.
- Dangerous extensions are rejected with `UNSUPPORTED_FILE_TYPE`.
- Oversized file returns `FILE_TOO_LARGE`.
- Extension spoofing is rejected.
- Rejected uploads do not create terminology cards.
- OCR unavailable and Formula OCR unavailable paths return structured errors, not 500.

Personal privacy regression:

- Student A can search Student A personal chunks.
- Student B cannot search Student A personal chunks.
- Teacher cannot override `owner_user_id` to search student personal chunks.
- Admin personal search writes `PersonalAccessAudit`.
- Personal cards do not enter course public terminology lists.

Migration regression:

- Empty database migration succeeds.
- Old partial schema migration succeeds.
- Repeated migration is idempotent.
- Required PR-1 to PR-5 tables and fields are present.
- Existing users/courses are preserved.

Release package:

```text
dist/LexiBridge-AI-Local-MVP-v0.8-20260622.zip
```

The package checker confirmed the zip does not include `.env`, database files, uploads, virtual environments, cache directories, Mac metadata, personal paths, or obvious API-key patterns.

## PR-5 Continued API Envelope Hardening

Additional work:

- Added API-level JSON handlers for `/api/*` 404 and 500 errors.
- Standardized more core Auth, Course, Document, Knowledge Search, Alignment, Terminology Export, Terminology Feedback, and Evaluation error branches through `api_error(...)`.
- Added API envelope regression coverage for register validation, missing knowledge query, course-scope alignment denial, missing alignment run, missing evaluation run target, and unknown `/api/*` path.

Latest commands:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_api_contract.py tests/test_auth.py tests/test_permissions.py tests/test_upload_security.py tests/test_personal_privacy.py tests/test_migrations.py
backend/.venv-macos/bin/python -m pytest
bash scripts/package_release.sh
```

Latest results:

```text
PR-5 regression subset: 26 passed
Full pytest suite: 58 passed, 5 warnings
Release package tests: 26 passed
Release package check: passed
```

## PR-6 Async Job Queue Regression

Test date: 2026-06-22

Commands run:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_jobs.py tests/test_job_api.py tests/test_worker.py tests/test_api_contract.py
backend/.venv-macos/bin/python -m pytest tests/test_upload_security.py tests/test_ocr_text_image.py tests/test_formula_ocr.py tests/test_personal_privacy.py tests/test_evaluation.py tests/test_permissions.py
```

Results:

```text
PR-6 queue + OpenAPI subset: 10 passed
Async compatibility regression subset: 25 passed
PR-6 job/worker/migration subset: 10 passed
Full pytest suite after PR-6: 65 passed, 5 warnings
Release package PR-5+PR-6 subset: 33 passed
Release package check: passed
```

Verified behavior:

- Default document upload returns `document_id`, `job_id`, and `job_status=queued`.
- `document_ingestion` worker execution parses text documents, creates chunks, indexes knowledge chunks, records events, and completes the job.
- Default `/api/alignment/run` creates `AlignmentRun` plus `alignment_run` job; worker execution completes the run and creates a terminology card.
- Default `/api/evaluation/run` creates `EvaluationRun` plus `evaluation_run` job; worker execution completes metrics and report markdown.
- `GET /api/jobs`, `GET /api/jobs/<id>`, and `GET /api/jobs/<id>/events` are role-scoped.
- Student cannot view a teacher course job.
- Queued jobs can be canceled; failed jobs can be retried.
- Legacy synchronous upload/OCR/evaluation tests use `?sync=true` and still pass.

Known PR-6 limits:

- The queue is SQLite-backed and single-worker only.
- Cancellation is cooperative and cannot interrupt a parser call already running inside Python/C extensions.
- Production should replace this with a durable queue such as Celery/RQ/Arq plus Redis/PostgreSQL advisory locks or cloud task infrastructure.

## PR-7 Frontend Information Architecture Regression

Test date: 2026-06-22

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python -m pytest tests/test_frontend_contract.py tests/test_api_contract.py tests/test_permissions.py tests/test_personal_privacy.py tests/test_jobs.py -q
backend/.venv-macos/bin/python -m pytest -q
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260622.zip
```

Results:

```text
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
PR-7 frontend/API/permission/privacy/job subset: 20 passed
Full pytest suite after PR-7: 70 passed, 5 warnings
Frontend JS syntax check: passed
Release package tests: 38 passed
Release package check: passed
```

Verified PR-7 behavior:

- Login now routes users to role-oriented workspaces: Student Workspace, Teacher Workspace, or Admin Workspace.
- Top status bar shows user, role, current course, AI provider status, OCR status, Formula OCR status, job count, and subscription quota.
- Student pages focus on terminology search, evidence-rich card details, favorites, mastered terms, feedback, personal upload, jobs, and subscription/export.
- Teacher pages focus on course selection, course upload, document/job status, AlignmentRun records, QC filtering, evidence snapshots, risk flags, and student feedback.
- Admin pages expose user/course management, global jobs, EvaluationRun metrics, system logs, usage records, and mock billing.
- QC can filter missing English evidence, missing Chinese evidence, domain mismatch, OCR low confidence, formula evidence missing, weak evidence, mock/local AI, conflicts, rejected, and auto-approved.
- Frontend error mapping includes core API error codes and renders user-facing messages instead of relying on console output.
- Frontend API paths used by `frontend/index.html` are documented in `docs/openapi.yaml`.

Known PR-7 limits:

- Frontend remains a vanilla single-page HTML/CSS/JS app.
- No WebSocket/SSE live task updates; users refresh job lists.
- Some teacher QC edit/reject actions use browser `prompt()` for course-demo simplicity.
- The UI is still a Local MVP, not a production design-system implementation.

## PR-7 Continued Frontend Workflow Closure

Test date: 2026-06-23

Additional frontend work:

- Added a logged-in Diagnostics page showing AI Provider, OCR Provider, Formula OCR Provider, background job summary, OpenAPI location, and Local MVP limitations.
- Added current-course terminology export from the Teacher Workspace.
- Updated terminology export to include the selected `course_id` and optional `scope_type`.
- Updated frontend workflow documentation and README to describe Diagnostics and current-course export.

Commands run:

```bash
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
backend/.venv-macos/bin/python -m pytest tests/test_frontend_contract.py -q
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python -m pytest tests/test_frontend_contract.py tests/test_api_contract.py tests/test_permissions.py tests/test_personal_privacy.py tests/test_jobs.py -q
backend/.venv-macos/bin/python -m pytest -q
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
```

Results:

```text
Frontend JS syntax check: passed
Frontend contract tests: 5 passed
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
PR-7 regression subset: 20 passed
Full pytest suite: 70 passed, 5 warnings
Release package tests: 38 passed
Release package check: passed
```

Release package:

```text
dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
```

## PR-16 Final Delivery Validation

Test time: 2026-06-23, Asia/Shanghai.

Environment:

```text
Python: 3.9.6
OS: macOS-26.5.1-arm64-arm-64bit
Database: SQLite local MVP database
Retrieval backend: lexical default with vector/hybrid-ready interfaces
AI provider: local configuration; production readiness still NOT READY
```

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python -m py_compile scripts/check_final_delivery.py scripts/generate_final_release_manifest.py scripts/build_final_release.py scripts/generate_final_demo_report.py scripts/collect_final_screenshots_checklist.py
backend/.venv-macos/bin/python scripts/check_pilot_package.py
backend/.venv-macos/bin/python scripts/check_final_delivery.py
backend/.venv-macos/bin/python scripts/generate_final_release_manifest.py --output final_delivery/final_release_manifest.json
backend/.venv-macos/bin/python scripts/generate_final_demo_report.py --output final_delivery/final_test_report.md
backend/.venv-macos/bin/python scripts/collect_final_screenshots_checklist.py --output final_delivery/final_screenshot_checklist.md
backend/.venv-macos/bin/python -m pytest tests/test_final_delivery.py tests/test_final_release_package.py tests/test_final_materials.py -q
backend/.venv-macos/bin/python -m pytest -q
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
backend/.venv-macos/bin/python scripts/build_final_release.py
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
backend/.venv-macos/bin/python scripts/check_production_readiness.py
```

Results:

```text
Pilot Package Check: PASS; files checked: 22; warnings: 0
Final Delivery Check: PASS; files checked: 24; warnings: 0
Generated final_delivery/final_release_manifest.json
Generated final_delivery/final_test_report.md
Generated final_delivery/final_screenshot_checklist.md
PR-16 focused tests: 13 passed in 0.83s
Full pytest suite: 173 passed, 6 warnings in 37.05s
Frontend JS syntax check: passed
build_final_release.py: PASS_WITH_WARNINGS
package_release.sh tests: 129 passed, 1 warning
Release package check: passed
Release zip: dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
Production readiness: NOT READY
```

Final release manifest summary:

```text
project_name: LexiBridge AI
version: local-pilot-ready-final
sensitive_file_check.passed: true
production_readiness.status: NOT_READY
production_readiness.blocker_count: 29
```

Production readiness blockers include SQLite, local storage, non-live AI provider mode, production secret/CORS configuration, missing production AI cost limits, and missing production healthcheck configuration.

PR-16 limitations:

- Final delivery is suitable for course submission, local demo, and small pilot preparation.
- It is not a production deployment package.
- Demo data does not represent real-course full accuracy.
- Terminology cards still require evidence, risk notes, and teacher review context.

## PR-15 Pilot Package Validation

Test time: 2026-06-23, Asia/Shanghai.

Environment:

```text
Python: 3.9.6
OS: macOS-26.5.1-arm64-arm-64bit
Database: SQLite local MVP database
AI provider: local configuration; production readiness still NOT READY
```

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python -m py_compile scripts/check_pilot_package.py scripts/generate_pilot_package_summary.py scripts/export_final_project_snapshot.py
backend/.venv-macos/bin/python scripts/check_pilot_package.py
backend/.venv-macos/bin/python scripts/generate_pilot_package_summary.py --output docs/generated/pilot_package_summary.md
backend/.venv-macos/bin/python scripts/export_final_project_snapshot.py --output docs/generated/final_project_snapshot.json
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python -m pytest tests/test_pilot_package.py tests/test_project_materials.py tests/test_final_snapshot.py -q
backend/.venv-macos/bin/python -m pytest -q
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
backend/.venv-macos/bin/python scripts/check_production_readiness.py
```

Results:

```text
Pilot Package Check: PASS
Files checked: 22
Warnings: 0

Generated docs/generated/pilot_package_summary.md
Generated docs/generated/final_project_snapshot.json

Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
PR-15 focused tests: 12 passed in 0.08s
Full pytest suite: 160 passed, 6 warnings in 36.17s
Frontend JS syntax check: passed
Release package tests: 116 passed, 1 warning in 27.43s
Release package check: passed
Release zip: dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
Production readiness: NOT READY
```

Production readiness blockers reported by `scripts/check_production_readiness.py`:

- `APP_ENV` is not production.
- `SECRET_KEY` is not a strong production secret.
- `AI_PROVIDER_MODE` is not live.
- SQLite is still configured.
- CORS production allowlist is unsafe for production.
- Local storage is still the only storage backend.
- AI daily/monthly/cost limits and production healthcheck are not production configured.

PR-15 known limitations:

- The pilot package is a local pilot and presentation material set, not a production operations manual.
- Real course trials still require teacher confirmation of material authorization.
- Demo success does not imply full real-course accuracy.
- Terminology cards must be interpreted with evidence, risk notes, and teacher review status.

## PR-13 Knowledge Base Versioning Validation

Validation time: 2026-06-23

Environment:

- Python: 3.9.6
- OS: macOS / Darwin
- Database: SQLite local database
- Retrieval index: `local_lexical_v1`
- Vector DB: not configured

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python -m py_compile scripts/create_kb_version.py scripts/rebuild_knowledge_index.py scripts/run_retrieval_regression.py scripts/check_knowledge_health.py scripts/export_kb_version_manifest.py scripts/export_sqlite_data.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python -m pytest tests/test_knowledge_versioning.py tests/test_knowledge_indexing.py tests/test_chunk_dedup.py tests/test_retrieval_regression.py tests/test_knowledge_health.py tests/test_source_governance.py -q
backend/.venv-macos/bin/python -m pytest tests/test_api_contract.py tests/test_frontend_contract.py -q
backend/.venv-macos/bin/python -m pytest -q
backend/.venv-macos/bin/python scripts/rebuild_knowledge_index.py --course-id 1 --apply
backend/.venv-macos/bin/python scripts/check_knowledge_health.py --course-id 1
backend/.venv-macos/bin/python scripts/run_retrieval_regression.py --course-id 1
backend/.venv-macos/bin/python scripts/export_kb_version_manifest.py --kb-version-id 18 --output docs/generated/kb_manifest_v18.json
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
backend/.venv-macos/bin/python scripts/check_production_readiness.py
```

Results:

```text
Python compile checks: passed
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
PR-13 pytest subset: 10 passed
API/frontend contract subset: 8 passed
Full pytest suite: 137 passed, 6 warnings
Frontend JS syntax check: passed with bundled Codex Node runtime
Release package tests: 93 passed, 1 warning
Release package check: passed
Production readiness: NOT READY
```

Knowledge index rebuild result:

```json
{
  "version_id": 18,
  "version_name": "course-1-kb-v2",
  "status": "ready",
  "source_count": 4,
  "chunk_count": 38,
  "formula_block_count": 1,
  "deduped_chunk_count": 0,
  "health_status": "PASS"
}
```

Knowledge health result after publishing version 18:

```json
{
  "status": "PASS",
  "issues": [],
  "warnings": [],
  "metrics": {
    "active_chunk_count": 38,
    "chunk_count": 38,
    "duplicate_count": 0,
    "duplicate_ratio": 0.0,
    "source_count": 2,
    "unknown_authorization_count": 0
  }
}
```

Retrieval regression result:

```json
{
  "status": "completed",
  "case_count": 21,
  "passed": 2,
  "failed": 19,
  "negative_match_errors": 0,
  "no_evidence_forced_match": 0
}
```

Regression interpretation:

- Safety-critical checks passed: no negative evidence match and no no-evidence forced match.
- Positive recall is low because the published course-1 KB version contains only the current local demo subset, while the course evaluation items cover a broader data-structures smoke set.
- The regression result is intentionally reported as a quality gap; it should block automatic KB publication in a stricter staging gate until the KB is expanded or the evaluation split is scoped to the published course materials.

Schema and database readiness:

```text
Schema audit: WARN; tables checked=40; issues=13
Database readiness: WARN; duplicate_cards=3; orphan_records=0; missing_personal_owner_records=0
```

Generated artifacts:

```text
docs/generated/kb_manifest_v18.json
dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
```

Production readiness blockers remain expected for Local MVP:

- Environment is not configured as production.
- SQLite is still used locally.
- Local storage is still used.
- Live AI provider and production AI quota settings are not configured.
- CORS and production secret values are not production-ready.

## PR-14 RAG Retrieval Enhancement Validation

Validation time: 2026-06-23

Environment:

- Python: 3.9.6
- Database: SQLite local database
- Default retrieval backend: `lexical`
- Optional vector index tested with: `local_json`
- Optional embedding provider tested with: `local_hash_embedding`
- Optional reranker tested with: `local_heuristic`

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python -m py_compile scripts/build_vector_index.py scripts/rebuild_vector_index.py scripts/run_retrieval_experiment.py scripts/check_vector_index_health.py scripts/export_retrieval_experiment_report.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python -m pytest tests/test_retrieval_backend_abstraction.py tests/test_embedding_provider.py tests/test_vector_index.py tests/test_hybrid_retrieval.py tests/test_reranker.py tests/test_retrieval_experiments.py tests/test_retrieval_permissions_with_vector.py tests/test_retrieval_score_fusion.py -q
backend/.venv-macos/bin/python -m pytest -q
backend/.venv-macos/bin/python scripts/build_vector_index.py --kb-version-id 1 --dry-run || true
backend/.venv-macos/bin/python scripts/build_vector_index.py --kb-version-id 18 --apply --embedding-provider local_hash_embedding --vector-index-backend local_json
backend/.venv-macos/bin/python scripts/check_vector_index_health.py --kb-version-id 18 --vector-index-backend local_json
EMBEDDING_PROVIDER=local_hash_embedding VECTOR_INDEX_BACKEND=local_json ENABLE_RERANKER=true RERANKER_PROVIDER=local_heuristic backend/.venv-macos/bin/python scripts/run_retrieval_experiment.py --course-id 1 --kb-version-id 18
backend/.venv-macos/bin/python scripts/export_retrieval_experiment_report.py --experiment-id 3 --output docs/generated/retrieval_experiment_3.md
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
```

Results:

```text
Python compile checks: passed
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
PR-14 pytest subset: 11 passed
Full pytest suite: 148 passed, 6 warnings
Frontend JS syntax check: passed
```

Vector index build result for KB version 18:

```json
{
  "status": "ready",
  "kb_version_id": 18,
  "chunks_scanned": 38,
  "chunks_embedded": 38,
  "skipped": 0,
  "failed": 0,
  "backend": "local_json",
  "embedding_provider": "local_hash_embedding",
  "embedding_dimension": 256
}
```

Vector index health:

```json
{
  "status": "ok",
  "backend": "local_json",
  "kb_version_id": 18,
  "vector_count": 38,
  "dimensions": [256],
  "index_dir": "data/vector_indexes"
}
```

Retrieval experiment summary:

```json
{
  "status": "completed",
  "experiment_id": 3,
  "recommendation": "Keep lexical. No tested backend improved top1 accuracy.",
  "lexical": {
    "top1_accuracy": 0.0,
    "top5_accuracy": 0.0,
    "negative_match_error_rate": 0.0,
    "no_evidence_forced_match_rate": 0.0,
    "personal_leakage_count": 0,
    "restricted_source_violation_count": 0
  },
  "vector": {
    "top1_accuracy": 0.0,
    "top5_accuracy": 0.0,
    "negative_match_error_rate": 0.0,
    "no_evidence_forced_match_rate": 0.0,
    "personal_leakage_count": 0,
    "restricted_source_violation_count": 0
  },
  "hybrid": {
    "top1_accuracy": 0.0,
    "top5_accuracy": 0.0,
    "negative_match_error_rate": 0.0,
    "no_evidence_forced_match_rate": 0.0,
    "personal_leakage_count": 0,
    "restricted_source_violation_count": 0
  },
  "hybrid_rerank": {
    "top1_accuracy": 0.0,
    "top5_accuracy": 0.0,
    "negative_match_error_rate": 0.0,
    "no_evidence_forced_match_rate": 0.0,
    "personal_leakage_count": 0,
    "restricted_source_violation_count": 0
  }
}
```

Interpretation:

- PR-14 successfully adds retriever abstraction, local vector index, hybrid fusion, reranker boundary, and retrieval experiments.
- Safety-critical metrics remained clean: no negative match, no no-evidence forced match, no personal leakage, no restricted source violation.
- Local hash vectors did not improve accuracy on the current local course/evaluation subset; the system correctly recommends keeping lexical retrieval.
- `local_hash_embedding` and `local_json` are demo/test backends, not production semantic retrieval.

Generated artifact:

```text
docs/generated/retrieval_experiment_3.md
```

## PR-12 AI Provider Governance Validation

Validation time: 2026-06-23

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py scripts/check_ai_config.py scripts/run_ai_provider_healthcheck.py scripts/export_ai_call_summary.py scripts/register_default_prompts.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python scripts/register_default_prompts.py
backend/.venv-macos/bin/python scripts/check_ai_config.py --env development
backend/.venv-macos/bin/python scripts/run_ai_provider_healthcheck.py
backend/.venv-macos/bin/python -m pytest tests/test_ai_provider_registry.py tests/test_prompt_registry.py tests/test_ai_call_logging.py tests/test_ai_provider_health.py tests/test_ai_cost_control.py tests/test_ai_alignment_integration.py -q
backend/.venv-macos/bin/python -m pytest tests/test_api_contract.py tests/test_frontend_contract.py -q
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
backend/.venv-macos/bin/python -m pytest -q
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
backend/.venv-macos/bin/python scripts/check_production_readiness.py
```

Results:

```text
Python compile checks: passed
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
Default prompts: created=0; updated=0; total=3
AI config check (development): PASS
AI healthcheck: deepseek (live) unknown; config complete; live probe skipped
PR-12 AI tests: 16 passed, 1 warning
OpenAPI/frontend contract tests: 8 passed
Frontend JS syntax check: passed
Full pytest suite: 127 passed, 6 warnings
Package release tests: 83 passed, 1 warning
Release package check: passed
Production readiness: NOT READY
```

AI governance notes:

- `AICallLog` stores hashes, status, token estimates, latency, cost, and redacted previews.
- Mock/local/none providers are explicitly blocked from auto-approved terminology cards.
- Live provider output still cannot bypass evidence gates, model evaluation eligibility, or card-generation risk checks.
- No real API key was used or committed during this validation.
- Production readiness remains NOT READY because the local environment still uses development settings, SQLite, local storage, and no configured live AI provider quotas.

## PR-11 Database And Object Storage Migration Readiness Results

Test time: 2026-06-23

Scope:

- SQLite remains supported for local pilot use.
- PostgreSQL and object storage paths are prepared through configuration, export/import dry-run scripts, schema audit, StorageService, and storage integrity checks.
- This does not claim production database or production object storage is already connected.

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py scripts/export_sqlite_data.py scripts/import_postgres_data.py scripts/migrate_local_files_to_storage.py scripts/check_storage_config.py scripts/check_database_readiness.py scripts/storage_integrity_check.py scripts/schema_audit.py scripts/check_production_readiness.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python scripts/schema_audit.py
backend/.venv-macos/bin/python scripts/check_database_readiness.py
backend/.venv-macos/bin/python scripts/check_storage_config.py --env development --file .env.example
backend/.venv-macos/bin/python scripts/check_storage_config.py --env production --file .env.production.example
backend/.venv-macos/bin/python scripts/migrate_local_files_to_storage.py --dry-run
backend/.venv-macos/bin/python scripts/storage_integrity_check.py
backend/.venv-macos/bin/python scripts/export_sqlite_data.py --db backend/lexibridge.db --output /tmp/lexibridge_sqlite_export_pr11 --exclude-personal
backend/.venv-macos/bin/python scripts/import_postgres_data.py --input /tmp/lexibridge_sqlite_export_pr11 --database-url postgresql://user:password@host:5432/lexibridge
backend/.venv-macos/bin/python -m pytest
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
backend/.venv-macos/bin/python scripts/check_production_readiness.py
```

Observed results:

```text
Python compile checks: passed
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
Schema audit: WARN; tables checked=35; issues=13
Database readiness: WARN; connectable=true; duplicate_cards=3; orphan records=0; missing_personal_owner_records=0
Development storage config: PASS
Production storage template config: FAIL as expected because S3 placeholders are not configured
Local files -> storage dry-run: documents dry_run=15, missing=11; formula_blocks missing=4
Storage integrity: PASS; storage objects checked=0; missing=0; hash_mismatch=0
SQLite export: passed; personal-scope documents/cards excluded with --exclude-personal
PostgreSQL import: dry-run passed; --apply remains intentionally gated
PR-11 focused pytest subset: 18 passed
Full pytest suite: 111 passed, 5 warnings
Frontend JS syntax check: passed
Release package tests: 67 passed
Release package check: passed
Production readiness: NOT READY
```

Production readiness blockers observed:

```text
- APP_ENV must be production.
- SECRET_KEY must be a strong non-placeholder value of at least 32 characters.
- DATABASE_URL must not use SQLite in production.
- CORS allowlist must not contain * in production.
- Local storage is not acceptable as the only production storage backend.
```

Release package:

```text
dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
```

PR-11 limitations:

- PostgreSQL is not connected in this local pilot environment; `import_postgres_data.py` supports dry-run and keeps destructive import behind `--apply`.
- S3-compatible object storage is a prepared interface and configuration boundary; no real bucket or secret is included.
- Existing legacy `file_path` records are preserved for compatibility; new uploads now write storage metadata through `StorageService`.
- Production remains blocked until PostgreSQL, object storage, production secrets, CORS allowlist, backup rehearsal, and deployment hardening are completed.

## PR-10 Pilot Feedback Loop Validation

Test time:

```text
2026-06-23 Asia/Shanghai
```

Scope validated:

- Student can submit visible-card pilot feedback.
- Student cannot submit feedback for invisible course cards.
- High-severity translation/evidence feedback moves the linked card back to `pending_quality_control`.
- Critical feedback writes a `SystemLog` entry.
- Teacher can triage, resolve, reject, convert to EvaluationItem, and convert to Backlog.
- Backlog priority mapping covers P0/P1/P2/P3.
- Pilot Report generation is redacted and does not include full student email, token, API key, or personal document text.
- Feedback summary export omits student email and personal document content.

Commands run:

```bash
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py scripts/generate_pilot_report.py scripts/export_feedback_summary.py
backend/.venv-macos/bin/python -m pytest tests/test_pilot_feedback.py tests/test_feedback_workflow.py tests/test_iteration_backlog.py tests/test_pilot_report.py
backend/.venv-macos/bin/python -m pytest tests/test_api_contract.py tests/test_frontend_contract.py tests/test_permissions.py
backend/.venv-macos/bin/python -m pytest
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
backend/.venv-macos/bin/python scripts/check_production_readiness.py
```

Observed results:

```text
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
PR-10 focused tests: 12 passed
API/frontend/permission regression tests: 15 passed
Full pytest suite: 98 passed, 5 warnings
Frontend JS syntax check: passed
Package release test subset: 54 passed
Release package check: passed
Production readiness: NOT READY
Production readiness blockers: local environment is not production, SECRET_KEY is not production-strong, DATABASE_URL uses SQLite, and CORS is not a production allowlist.
```

Additional PR-10 hardening after review:

```text
OpenAPI contract tests now include /api/feedback/*, /api/backlog/*, and /api/pilot/report.
Migration tests now verify Feedback pilot fields and iteration_backlog_item schema.
Focused PR-10 + contract + migration tests: 18 passed
Full pytest suite after hardening: 98 passed, 5 warnings
Frontend JS syntax check after hardening: passed
```

Known PR-10 limitations:

- Feedback classification is rule-based, not NLP-based.
- Pilot report is a local pilot summary, not production analytics.
- Real pilot validity still depends on teacher/student review and additional course data.

## PR-9 Deployment Readiness Results

Test time: 2026-06-23 09:10 Asia/Shanghai.

Scope:

- Environment configuration checks.
- Logging redaction helpers.
- Health report.
- Local backup and restore.
- Cost-control helpers.
- Production readiness report.
- Release package validation.

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python -m py_compile scripts/check_env.py scripts/backup_local_data.py scripts/restore_local_data.py scripts/collect_health_report.py scripts/check_production_readiness.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python scripts/check_env.py --env development --file .env.development.example
backend/.venv-macos/bin/python scripts/check_env.py --env production --file .env.production.example
backend/.venv-macos/bin/python scripts/collect_health_report.py
backend/.venv-macos/bin/python scripts/backup_local_data.py --output backups/lexibridge_pr9_backup_test.zip --database backend/lexibridge.db --uploads backend/uploads
backend/.venv-macos/bin/python scripts/restore_local_data.py --backup backups/lexibridge_pr9_backup_test.zip --target /tmp/lexibridge-pr9-restore
backend/.venv-macos/bin/python -m pytest tests/test_env_config.py tests/test_logging_safety.py tests/test_backup_restore.py tests/test_cost_control.py tests/test_production_readiness.py -q
backend/.venv-macos/bin/python -m pytest -q
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
backend/.venv-macos/bin/python scripts/check_production_readiness.py --env-file .env.production.example --skip-tests
```

Results:

```text
Python compile checks: passed
Migration: passed
Development env check: PASS, with weak-secret warning as expected
Production env template check: FAIL as expected
PR-9 pytest subset: 12 passed
Full pytest suite: 86 passed, 5 warnings
Frontend JS syntax check: passed
Release package tests: 54 passed
Release package check: passed
Production readiness: NOT READY
```

Health report excerpt:

```json
{
  "status": "ok",
  "database": {
    "type": "sqlite",
    "size_mb": 0.8203
  },
  "jobs": {
    "queued": 0,
    "running": 0,
    "failed": 0,
    "completed": 6
  },
  "quality": {
    "auto_approved": 0,
    "pending_quality_control": 28,
    "needs_more_evidence": 48
  },
  "evaluation": {
    "latest_run_id": 5,
    "alignment_accuracy": 0.0328,
    "no_evidence_forced_alignment_rate": 0.0
  }
}
```

Backup/restore:

```text
Backup created: backups/lexibridge_pr9_backup_test.zip
included_env: false
upload_file_count: 23
restore target: /tmp/lexibridge-pr9-restore
restore result: passed
```

Production readiness blockers from `.env.production.example`:

```text
Production readiness: NOT READY
- Production environment validation failed.
- UPLOAD_DIR/UPLOAD_FOLDER is not writable: /var/lib/lexibridge/uploads
- SECRET_KEY must be a strong non-placeholder value of at least 32 characters.
- DEEPSEEK_API_KEY must be configured with a non-placeholder value for production DeepSeek.
```

This `NOT READY` result is correct for the current Local MVP. The project now has deployment-readiness checks, but it has not been deployed and should not be presented as production-ready.

## PR-8 Demo Dataset And Pilot Flow Results

Test time: 2026-06-23 08:50 Asia/Shanghai.

Environment:

- Python: backend virtual environment at `backend/.venv-macos/bin/python`.
- Database: local SQLite.
- AI provider: forced to `AI_PROVIDER=none` inside `scripts/run_demo_flow.py` for deterministic local demo execution.
- OCR provider: `none` unless the developer configures a local OCR engine.
- Formula OCR provider: `none`; formula regions are marked rather than converted to LaTeX.

Demo data created:

- `DS101 - Data Structures and Algorithms`
- `SP101 - Signal Processing Basics`
- `MATH101 - Engineering Mathematics`
- 61 gold evaluation items.
- 95 demo document chunks.
- 95 demo knowledge chunks.
- 4 formula blocks marked as needing formula OCR.

Seed command:

```bash
backend/.venv-macos/bin/python scripts/seed_demo_data.py --summary-json
```

Observed seed output:

```text
Demo Seed Result:
- Created users: 0 (updated 4)
- Created courses: 0 (updated 3)
- Created documents: 0 (updated 11)
- Created document chunks: 95
- Created knowledge chunks: 95
- Created formula blocks: 4
- Created evaluation items: 61
- Evaluation set id: 5
```

Demo flow command:

```bash
backend/.venv-macos/bin/python scripts/run_demo_flow.py --summary-json
```

Observed demo flow output:

```text
Demo Flow Result:
- document ingestion: PASS
- alignment run: PASS
- cards generated: 10
- QC cards: 10
- auto approved cards: 0
- student search: PASS
- student feedback: PASS
- admin jobs: PASS
- evaluation run: PASS
- no evidence forced alignment rate: 0.0
```

EvaluationRun metrics from the demo flow:

```json
{
  "input_count": 61,
  "skipped_count": 0,
  "extraction_precision": 0.2205,
  "extraction_recall": 0.7049,
  "english_evidence_accuracy": 1.0,
  "chinese_evidence_accuracy": 0.75,
  "evidence_accuracy": 0.0984,
  "alignment_accuracy": 0.0328,
  "false_positive_rate": 0.0,
  "auto_approval_error_rate": 0,
  "no_evidence_forced_alignment_rate": 0.0,
  "ocr_noise_term_rate": null
}
```

Release-gate note:

- The demo flow passed the safety-critical gate `no_evidence_forced_alignment_rate = 0`.
- The local smoke metrics do not yet meet the desired production-style quality thresholds for extraction precision, evidence accuracy, or alignment accuracy.
- This is expected for the current Local MVP with local lexical retrieval and no live AI provider. These gaps are intentionally reported rather than hidden.

PR-8 demo limitations:

- Demo materials are self-authored examples, not real licensed course textbooks.
- Without a real Formula OCR provider, formula samples are saved as FormulaBlock status `needs_formula_ocr_engine`.
- Without a live AI provider, demo cards remain in QC or evidence-needed states and are not auto-approved.

## PR-8 Validation Commands

Commands run:

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py scripts/run_worker.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
backend/.venv-macos/bin/python -m py_compile scripts/seed_demo_data.py scripts/run_demo_flow.py
backend/.venv-macos/bin/python scripts/migrate_db.py
backend/.venv-macos/bin/python scripts/seed_demo_data.py
backend/.venv-macos/bin/python -m pytest tests/test_demo_seed.py -q
backend/.venv-macos/bin/python -m pytest tests/test_demo_flow.py -q
backend/.venv-macos/bin/python -m pytest tests/test_demo_evaluation.py -q
backend/.venv-macos/bin/python -m pytest -q
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check /tmp/lexibridge-frontend.js
bash scripts/package_release.sh
backend/.venv-macos/bin/python scripts/check_release_package.py dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
```

Results:

```text
Python compile checks: passed
Migration: database migrated; seed_users_created=0; seed_courses_created=0; seed_plans_created=0; demo_kb_created=0
Demo seed command: passed
tests/test_demo_seed.py: 2 passed
tests/test_demo_flow.py: 1 passed
tests/test_demo_evaluation.py: 1 passed
Full pytest suite: 74 passed, 5 warnings
Frontend JS syntax check: passed
Release package tests: 42 passed
Release package check: passed
```

Release package:

```text
dist/LexiBridge-AI-Local-MVP-v0.8-20260623.zip
```
