# LexiBridge AI Pilot v1.0 Candidate

LexiBridge AI is an AI-powered bilingual course knowledge alignment platform for Sino-foreign cooperative education.

LexiBridge AI 是一个面向中外合作办学课程的 AI 双语课程知识对齐平台。它不是普通 AI 翻译网站，也不是词典或简单 RAG 聊天机器人。当前版本用于课程最终 Demo，核心目标是把英文课程资料、英文课程知识库、中文课程知识库和学生个人资料连接起来，生成有来源证据、置信度和质量控制状态的双语课程术语知识卡片。

## Current Scope

This repository is a Controlled Academic Pilot Release Candidate. It is suitable
for a governed local pilot with the documented conditions; it is not a public,
commercial, or production deployment:

- Backend: Flask + SQLite.
- Frontend: single-page HTML/CSS/JavaScript.
- Auth: local registration, login, bearer token, role checks.
- AI: DeepSeekProvider when configured; local heuristic/mock fallback only for demo.
- Controlled Provider evaluation: an evaluation-only Chinese candidate proposal
  path exists for safe dry-runs and loopback fake-provider E2E. It does not call
  a real Provider by default, does not change the Formal Workflow provider, and
  does not treat Provider output as evidence.
- OCR: local Tesseract when installed and configured; otherwise the system reports OCR unavailable and does not fabricate OCR text. PaddleOCR remains available only when explicitly selected.
- Payment: mock payment for Basic/Pro subscription demos.
- Email: mock verification/reset token in development.
- Retrieval: SQLite keyword/simple similarity, with no vector database in this release.

Not implemented in this Local MVP: real cloud deployment, real SMTP, real payment, real vector database, ByrDocs integration, publisher/library connectors, automatic textbook crawling, and production multi-model routing.

## Configuration

Copy the example file:

```bash
cd LexiBridge-AI
cp .env.example .env
```

Recommended local values:

```env
AUTH_REQUIRED=True
AI_PROVIDER=deepseek
ALLOW_MOCK_AI=True
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY_HERE
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=15
MOCK_EMAIL_ENABLED=True
MOCK_PAYMENT_ENABLED=True
OCR_PROVIDER=none
OCR_LANGS=eng+chi_sim
OCR_MIN_CONFIDENCE=60
OCR_ENABLE_REGION_EXTRACTION=true
PDF_OCR_DPI=300
PDF_IMAGE_MIN_WIDTH=80
PDF_IMAGE_MIN_HEIGHT=40
PDF_MIXED_PAGE_IMAGE_OCR=true
FORMULA_OCR_PROVIDER=none
FORMULA_OCR_MIN_CONFIDENCE=60
FORMULA_DETECTION_MODE=heuristic
MATHPIX_APP_ID=YOUR_MATHPIX_APP_ID_HERE
MATHPIX_APP_KEY=YOUR_MATHPIX_APP_KEY_HERE
LOCAL_LATEX_OCR_COMMAND=
MAX_UPLOAD_SIZE_MB=50
MIN_RETRIEVAL_SCORE=65
RETRIEVAL_VERSION=local_lexical_v1
TERM_EXTRACTION_PROMPT_VERSION=term_extraction_v1
ALIGNMENT_PROMPT_VERSION=alignment_v1
TOKEN_HASH_SECRET=change-this-local-token-hash-secret
```

Use `AI_PROVIDER=none` or remove `DEEPSEEK_API_KEY` to force local demo fallback. Mock/local fallback results are clearly marked and are not auto-approved.

Use `OCR_PROVIDER=auto` to select local Tesseract when its executable and required language data are available. Use `OCR_PROVIDER=none` to verify the unavailable-OCR path. If no OCR engine is installed, image and scanned-PDF uploads return a clear OCR status and do not generate fake OCR terminology cards.

## OCR And Formula OCR

LexiBridge AI separates three parsing layers:

- Native text extraction for digital PDF/DOCX/PPTX/TXT.
- Text OCR for scanned pages, JPG/PNG, and image regions inside mixed PDFs.
- Raster formula region detection, saved as auditable `FormulaBlock` region records.
- Formula OCR/recognition for image-based equations.

Tesseract and PaddleOCR are ordinary text OCR engines. They may read some symbols, but they are not reliable formula OCR engines and do not guarantee LaTeX output. Image-based formulas require a separate Formula OCR provider.

Default local configuration does not fabricate OCR output:

```env
OCR_PROVIDER=none
FORMULA_OCR_PROVIDER=none
```

With this configuration, image uploads or scanned PDF pages that need OCR return
`ocr_unavailable` / `needs_ocr_engine`, and formula-like raster regions are saved
as `FormulaBlock` records with detection provenance and
`FORMULA_RECOGNIZER_UNAVAILABLE`. No fake text or fake LaTeX is generated, and
formula content is not sent to terminology extraction.

To enable Tesseract text OCR, install an operator-reviewed local Tesseract runtime with `eng`, `chi_sim`, and `osd` language data. The server discovers it from `LEXIBRIDGE_TESSERACT_CMD` first, then `PATH`.

Example macOS verification:

```bash
command -v tesseract
tesseract --version
tesseract --list-langs
```

Then set:

```env
OCR_PROVIDER=auto
LEXIBRIDGE_TESSERACT_CMD=
OCR_LANGS=eng+chi_sim
OCR_MIN_CONFIDENCE=60
```

Leave `LEXIBRIDGE_TESSERACT_CMD` unset when `tesseract` is already available
on `PATH`; otherwise set it only in the server process environment, not in Git.

For PaddleOCR, install PaddleOCR in your Python environment and set:

```env
OCR_PROVIDER=paddle
```

For formula OCR, configure one of the optional providers:

```env
FORMULA_OCR_PROVIDER=mathpix
MATHPIX_APP_ID=YOUR_MATHPIX_APP_ID_HERE
MATHPIX_APP_KEY=YOUR_MATHPIX_APP_KEY_HERE
```

or a future local command:

```env
FORMULA_OCR_PROVIDER=local_latex
LOCAL_LATEX_OCR_COMMAND="your-latex-ocr-command"
```

If `FORMULA_OCR_PROVIDER` is not configured, the system still detects likely
raster formula regions and records page, bounding-box, region-hash, detection
method, confidence, surrounding-text refs, and recognizer-unavailable status.
It does not claim to recognize the formula. Ordinary OCR success does not imply
formula OCR success. Handwritten formulas, complex charts, and table-structure
recognition are not promised in this Local MVP.

Never put real API keys in `README.md`, frontend code, `.env.example`, or a release package.

## Controlled Provider Evaluation

Task 10B adds a separate evaluation-only path for future Chinese terminology
candidate proposal testing:

```bash
python scripts/run_controlled_provider_evaluation.py \
  --manifest evaluation/controlled_provider_evaluation/synthetic_manifest.json \
  --json-output /tmp/controlled-provider-evaluation-dry-run.json \
  --dry-run
```

The dry-run validates privacy, provider/model selection, bounded inputs, budget
configuration, strict output contracts, and sanitized artifact writing without
external Provider requests. Live execution requires a later task, an approved
Provider target, a legal credential, safe data, and explicit budget gates.

Provider-generated output is only a proposal for evaluation. It is not document
evidence, not an approved card, and not student-facing learning material.

## Start Locally

Install dependencies:

```bash
bash scripts/bootstrap_runtime.sh
bash scripts/run_python.sh scripts/runtime_environment.py --diagnose
```

The canonical macOS runtime is stored outside the Desktop repository under
`~/Library/Application Support/LexiBridge-AI/runtime` by default. This avoids
making pilot uptime depend on the legacy in-repository `.venv-macos`. Runtime
and test dependencies are exactly pinned in separate lock files. Set
`LEXIBRIDGE_RUNTIME_VENV` to choose another external location.

Initialize or migrate the database:

```bash
bash scripts/run_python.sh scripts/migrate_db.py --apply
```

Start backend:

```bash
bash scripts/run_backend.sh
```

The default `pilot` server mode uses Gunicorn through `backend/wsgi.py` with a
single process and bounded threads suitable for the controlled SQLite pilot.
Flask's development server is available only when explicitly requested with
`LEXIBRIDGE_SERVER_MODE=development`.

Start the local background worker in a second terminal:

```bash
bash scripts/run_worker.sh
```

For a one-shot worker pass during testing:

```bash
bash scripts/run_worker.sh --once
```

The default `standard` loop alternates first opportunity between the formal
document-alignment CAS dispatcher and generic document-ingestion/evaluation
jobs, processing at most one job per iteration. It never consumes legacy
`alignment_run` jobs. Run the compatibility worker separately and explicitly:

```bash
bash scripts/run_worker.sh --mode legacy-alignment
```

`--mode formal` and `--mode generic` are also available for isolated local
operation. `JOB_WORKER_QUEUE_MODE` selects the default mode. This is a
controlled-pilot worker, not a supervised production
daemon. Formal document jobs never enter the legacy dispatcher.

Legacy freeze operations use `LEGACY_ALIGNMENT_RUNTIME_STATE` with
`active`, `freeze`, `draining`, and `disabled` states. Inspect the queue without
writes using `python scripts/legacy_alignment_runtime.py status`. The
safe-failure command is dry-run unless the runtime state, owner fence, stale
cutoff, apply environment gate, and `--apply` all authorize one transaction.
Payload-free observation events are enabled by
`LEGACY_ALIGNMENT_OBSERVATION_ENABLED`; aggregate retained application logs
with `python scripts/legacy_alignment_observation_report.py`. Repository scans
and local E2E do not complete the required target-environment 14-day window.

If port `5000` is occupied:

```bash
BACKEND_PORT=5001 bash scripts/run_backend.sh
```

Then update `frontend/js/config.js`:

```js
window.LEXIBRIDGE_CONFIG = window.LEXIBRIDGE_CONFIG || {
  API_BASE: "http://127.0.0.1:5001"
};
```

Open the frontend file in a browser:

```text
frontend/index.html
```

## Test Accounts

Run `bash scripts/run_python.sh scripts/migrate_db.py --apply` first.

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@lexibridge.local` | `Admin1234` |
| Teacher | `teacher@lexibridge.local` | `Teacher1234` |
| Student | `student@lexibridge.local` | `Student1234` |

All seed users are verified.

## Demo Paths

Teacher course workflow:

1. Login as `teacher@lexibridge.local`.
2. The app opens the Teacher Workspace by default.
3. Open `Courses` and create or select a course.
4. Upload teacher courseware from `Courseware Upload`. Teachers are not expected to manually upload English or Chinese professional knowledge bases.
5. Open `Job Status` to watch the `document_ingestion` job.
6. In the production design, the system should automatically build English/Chinese domain KBs from governed web sources before alignment. In this local build, live internet acquisition connectors are not configured, so missing evidence remains visible in QC.
7. After the job completes, use the document card action to trigger terminology alignment.
8. Open `Alignment Runs` and inspect generated card count, auto-approved count, QC count, missing-evidence count, and failures.
9. Open `Quality Control` to filter by missing evidence, domain mismatch, OCR low confidence, formula evidence missing, weak evidence, or mock/local AI risk.
10. Approve, edit and approve, reject, or mark low-evidence cards as needing more evidence.
11. Open `Student Feedback` to resolve feedback and jump back to card review when needed.

Student course workflow:

1. Login as `student@lexibridge.local`.
2. The app opens the Student Workspace by default.
3. Join or select a course.
4. Search course terminology cards by keyword, course, scope, and status.
5. Open a card and inspect English evidence, Chinese evidence, AI model, risk note, confidence, alignment status, and card status.
6. Favorite, mark mastered, and submit typed feedback.
7. Open `Job Status` to inspect personal upload jobs.

Student personal workspace:

1. Login as a Student.
2. Open `Subscription & Usage`.
3. Use mock payment to activate Basic or Pro if needed.
4. Upload personal documents from `Upload Personal Document`.
5. Confirm the page warning: personal materials are private to the current user and do not enter the course public knowledge base.
6. Track the `document_ingestion` job and generated personal cards from the student workspace.

Admin workflow:

1. Login as `admin@lexibridge.local`.
2. The app opens the Admin Workspace by default.
3. Open user management, course management, knowledge sources, knowledge base versions, subscription plans, usage records, billing records, global jobs, Evaluation Runs, and system logs.
4. Check provider failures, mock email, mock payment, OCR warnings, queue failures, and usage records.

## Frontend Workflow

The current frontend is a single-page HTML/CSS/JavaScript local MVP. It is organized as role workspaces:

- Student Workspace: terminology search, card evidence, favorites, mastered terms, feedback, personal upload, personal jobs, subscription and export.
- Teacher Workspace: course selection, courseware upload, document/job status, Alignment Runs, Quality Control, student feedback, and current-course terminology export.
- Admin Workspace: user/course management, global jobs, Evaluation Runs, logs, usage records, and mock billing.
- Diagnostics: AI/OCR/Formula OCR provider state, job summary, OpenAPI pointer, and Local MVP limitations.

The top status bar displays current user, role, course, AI provider status, OCR provider status, Formula OCR status, job count, and current plan/quota. Mock/local AI results and formula OCR disabled states are shown as risks; they are not visually treated as production live AI. The terminology export button includes the current course when one is selected.

More details are in:

```text
docs/frontend-workflow.md
```

## Mock Email

Public registration creates Student accounts. In development, the backend returns a verification token and writes a mock email log.

Flow:

1. Register.
2. Copy the displayed `verification_token`.
3. Verify the account on the mock verification page.
4. Login with email and password.

Password reset uses the same mock-token pattern.

## Mock Payment And Quota

Seeded plans:

| Plan | Price | Monthly pages | AI/search units | Export |
| --- | ---: | ---: | ---: | --- |
| Free | 0 yuan/month | 5 | 20 | Disabled |
| Basic | 10 yuan/month | 100 | 300 | Enabled |
| Pro | 39 yuan/month | 500 | 2000 | Enabled |

Personal uploads, personal alignment, OCR usage, and export checks are recorded as local `UsageRecord` entries. Mock payment immediately creates an active subscription and a billing record.

## OCR Behavior

Supported upload types: PDF, DOCX, PPTX, TXT/Markdown, JPG/JPEG/PNG.

- Digital PDF pages use native PyMuPDF text extraction.
- Text-poor PDF pages are rendered to images and passed to OCR.
- JPG/JPEG/PNG files are sent directly to OCR.
- OCR chunks keep provider, status, confidence, source location, and failure reason.
- OCR confidence below 60 prevents auto-approval.
- Placeholder strings such as `OCR_REQUIRED` and `OCR_FALLBACK` are blocked from term extraction and card generation.

Tesseract can be installed separately, for example:

```bash
brew install tesseract
```

PaddleOCR is optional and not required for this local demo.

## AI Provider Behavior

PR-12 moves AI calls behind a governed model-service layer. The current code supports:

- `AI_PROVIDER_MODE=none`: no live AI provider configured.
- `AI_PROVIDER_MODE=mock`: deterministic demo/test provider only.
- `AI_PROVIDER_MODE=local_heuristic`: local low-confidence fallback.
- `AI_PROVIDER_MODE=live`: configured live provider such as DeepSeek or OpenAI-compatible API.

All AI tasks should go through `call_ai_task()` so the system records provider, model, prompt version, request/response hashes, token estimates, latency, cost, and error state. Direct provider calls should not be added for alignment, term extraction, feedback classification, or evaluation judging.

When DeepSeek is not configured or fails:

- The backend writes `AICallLog` and `SystemLog` entries.
- Cards show provider/mode/model/prompt metadata and risk notes.
- Cards are routed to `pending_quality_control` or `needs_more_evidence`.
- Mock/local/none results never produce `auto_approved` cards.

Governance commands:

```bash
python scripts/register_default_prompts.py
python scripts/check_ai_config.py --env development
python scripts/run_ai_provider_healthcheck.py
python scripts/export_ai_call_summary.py --format json
```

Important docs:

- `docs/ai-provider-governance.md`
- `docs/prompt-versioning.md`
- `docs/model-registry.md`
- `docs/ai-cost-control.md`
- `docs/ai-failure-and-fallback.md`

Production must set `AI_PROVIDER_MODE=live`, disable mock/local AI, disable full prompt/response logging, and configure real quotas. A model cannot be used for auto-approval unless it is live, enabled, tied to an active prompt, and has a passing recent EvaluationRun.

## Knowledge Base Boundaries

LexiBridge AI separates:

- Global discipline knowledge base.
- Course-specific English and Chinese knowledge bases.
- Student personal knowledge base.

Course uploads require a course context and are visible only through course permissions. Personal uploads are private to the owner and are not shown in teacher QC by default. Retrieval returns empty evidence when the relevance score is below threshold; it does not fall back to unrelated or latest chunks.

## Evidence Retrieval Policy

Current retrieval version: `local_lexical_v1`.

The Local MVP uses SQLite storage plus deterministic local lexical scoring. It does not include a production vector database or reranker. Evidence retrieval now applies metadata hard filters before scoring:

- English evidence: `language in ["en", "bilingual"]` and `knowledge_base_type=en_course_kb`. In the intended production workflow this KB is system-built from governed English web/domain sources.
- Chinese evidence: `language in ["zh", "bilingual"]` and `knowledge_base_type=zh_course_kb`. In the intended production workflow this KB is system-built from governed Chinese web/domain sources.
- Course evidence: exact `course_id` and `visibility=course`.
- Personal evidence: exact `owner_user_id`, `visibility=private`, and `knowledge_base_type=student_personal_kb`.

Scoring returns `evidence_score`, `evidence_strength`, `score_breakdown`, and `risk_flags`. Thresholds:

- `< 0.65`: rejected and not returned.
- `0.65-0.79`: weak evidence, routed to Quality Control.
- `>= 0.80`: strong evidence.

Examples:

## Knowledge Base Versioning

PR-13 adds governed local KB versioning on top of SQLite and the local lexical index:

- `KnowledgeBaseVersion` tracks `draft`, `ready`, `published`, `archived`, `failed`, and rollback states.
- `KnowledgeSource` tracks source lifecycle, license/authorization status, and source quality.
- `KnowledgeChunk` stores `knowledge_base_version_id`, `content_hash`, duplicate status, index status, and active state.
- Retrieval uses the current published KB version when one exists; legacy unversioned chunks remain supported for local compatibility.
- `TerminologyCard` records KB version, retrieval run, index version, and evidence content hashes.

Useful commands:

```bash
python scripts/create_kb_version.py --course-id 1 --scope-type course
python scripts/rebuild_knowledge_index.py --course-id 1 --dry-run
python scripts/check_knowledge_health.py --course-id 1
python scripts/run_retrieval_regression.py --course-id 1
python scripts/export_kb_version_manifest.py --kb-version-id 1 --output docs/generated/kb_manifest_v1.json
```

Design docs:

- `docs/knowledge-versioning-design.md`
- `docs/indexing-and-rebuild-plan.md`
- `docs/retrieval-regression-spec.md`
- `docs/source-governance.md`

- `Fourier Transform` can match `傅里叶变换`.
- `Fourier Transform` must not match `Hash Table`.
- If no Chinese or English evidence passes the threshold, the result is an empty evidence list and the card becomes `needs_more_evidence`.

## Alignment State Machine

Terminology card generation uses `docs/alignment-design.md` as the rule source. The backend separates semantic `alignment_status` from business `TerminologyCard.status`.

Key alignment statuses include `exact_match`, `accepted_translation`, `partial_match`, `no_en_evidence`, `no_zh_evidence`, `domain_mismatch`, `ocr_low_confidence`, `formula_evidence_missing`, `invalid_term_candidate`, and `unverified_translation`.

Business statuses include `needs_more_evidence`, `pending_quality_control`, `conflict_detected`, `auto_approved`, `approved`, `rejected`, and `archived`.

Final confidence is computed from term quality, English evidence score, Chinese evidence score, AI alignment score, course scope, source quality, and direct risk penalties. Missing English or Chinese evidence caps confidence at 45. Mock/local AI adds `mock_or_local_ai` risk and cannot auto-approve.

Auto approval requires confidence `>=85`, English and Chinese evidence scores `>=0.80`, `alignment_status` of `exact_match` or `accepted_translation`, a live AI provider, and no missing evidence, domain mismatch, OCR low confidence, formula evidence missing, invalid term, or multi-translation conflict.

Every alignment run writes `AlignmentRun` statistics, and each `TerminologyCard` stores evidence snapshots plus `score_breakdown_json`, `quality_flags_json`, `retrieval_version`, and `source_alignment_run_id`.

## API Surface

Public:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET/POST /api/auth/verify-email`
- `POST /api/auth/password-reset/request`
- `POST /api/auth/password-reset/confirm`
- `GET /api/subscription/plans`

Authenticated core groups:

- Auth: `/api/auth/me`, `/api/auth/logout`
- Courses: `/api/courses`, `/api/courses/mine`, `/api/courses/<id>/join`
- Documents: `/api/documents/upload`, `/api/documents`, `/api/documents/<id>/chunks`
- Document Parses: `/api/document-parses`, `/api/document-parses/<parse_uid>`, `/api/document-parses/test`
- Knowledge: `/api/knowledge/sources`, `/api/knowledge/versions`, `/api/knowledge/search`
- Concept Cards: `/api/concept-cards`, `/api/concept-cards/<card_uid>`, `/api/concept-cards/<card_uid>/status`
- Audit Records: `/api/audit-records`, `/api/audit-records/<audit_uid>`
- Alignment: `/api/alignment/run`, `/api/alignment/runs/<id>`, `/api/terminology/cards`
- Jobs: `/api/jobs`, `/api/jobs/<id>`, `/api/jobs/<id>/events`, `/api/jobs/<id>/cancel`, `/api/jobs/<id>/retry`
- Export: `/api/terminology/cards/export`
- Quality Control: `/api/quality-control`
- Subscription: `/api/subscription/me`, `/api/subscription/mock-payment`, `/api/usage/me`
- Admin: `/api/admin/users`, `/api/admin/usage`, `/api/admin/billing`, `/api/admin/logs`, `/api/admin/ingestion-jobs`, `/api/admin/alignment-runs`, `/api/admin/model-registry`, `/api/admin/personal-access-audit`
- Evaluation: `/api/evaluation/sets`, `/api/evaluation/items/import`, `/api/evaluation/items`, `/api/evaluation/run`, `/api/evaluation/runs`, `/api/evaluation/runs/<id>`

Legacy `/api/terms/*`, `/api/glossary`, `/api/feedback`, and `/api/knowledge/*` routes are retained for compatibility but now enforce login and role/course permissions.

Concept Alignment Card API examples:

```http
POST /api/concept-cards
```

```json
{
  "english_term": "Fourier Transform",
  "chinese_term": "傅里叶变换",
  "course": "Signal Processing",
  "chapter": "Frequency Analysis",
  "status": "needs_review",
  "confidence_score": 0.82,
  "risk_labels": ["weak_chinese_evidence"],
  "english_evidence": [
    {
      "source": "Lecture notes",
      "page": 12,
      "text": "Fourier Transform converts a time-domain signal into frequency-domain representation.",
      "chunk_id": 101,
      "score": 0.88
    }
  ]
}
```

```http
GET /api/concept-cards?course=Signal%20Processing&status=needs_review&q=Fourier
PATCH /api/concept-cards/<card_uid>
POST /api/concept-cards/<card_uid>/status
```

Supported status values are `draft`, `needs_review`, `approved`, `rejected`, and `deprecated`. `approved` requires English or Chinese evidence. Concept Card and AuditRecord API responses include a `request_id`. Clients may pass `X-Request-ID`; otherwise the backend generates one for that request. These APIs expose the core resource only; live AI alignment generation is not connected in this task.

AuditRecord API examples:

```http
GET /api/audit-records?target_type=concept_alignment_card&target_uid=<card_uid>
GET /api/audit-records?event_type=concept_card_updated&result=success
GET /api/audit-records?request_id=<request_id>
GET /api/audit-records/<audit_uid>
```

Audit records currently cover observable Concept Card behavior events:

- `concept_card_created`
- `concept_card_updated`
- `concept_card_status_changed`
- selected `concept_card_operation_failed` validation failures, including attempts to approve a card without evidence

Audit snapshots store safe structured summaries such as card UID, terms, course/chapter, status, confidence, risk labels, version, reviewer, and timestamps. Evidence and request payloads are summarized/redacted to avoid duplicating large text or secrets. The audit layer records externally observable system behavior and output quality; it does not record or claim access to a model's internal reasoning chain. Future alignment-engine work can extend these records with model name, prompt version, retrieval version, retrieval evidence summaries, raw model output, and structured parser results.

Audit context currently records request ID, actor ID/role/name, event source, optional IP hash, and a truncated user-agent summary. It does not store full request headers, Authorization tokens, cookies, API keys, or raw local secrets.

Document Parse Quality API examples:

```http
GET /api/document-parses?quality_status=native_text_ok&file_type=txt
GET /api/document-parses/<parse_uid>
POST /api/document-parses/test
```

`DocumentParseRecord` stores one document parsing attempt: filename, file type, parser name/version, parse status, quality status, quality flags, page/block counts, extracted text length, OCR availability/requirement, formula/image-only indicators, warnings, and errors. `DocumentParseBlock` stores traceable parsed blocks with page or slide location, block type, text, confidence, parser type, source locator, and quality flags.

Supported `quality_status` values include `native_text_ok`, `partial_text`, `empty_text`, `ocr_required`, `ocr_unavailable`, `ocr_low_confidence`, `formula_detected`, `formula_ocr_required`, `formula_ocr_unavailable`, `unsupported_file_type`, `parse_failed`, and `mixed_quality`. The main status captures the dominant quality state; additional states are stored in `quality_flags`.

The parse quality layer does not fabricate OCR text or formula recognition output. If OCR or formula OCR is required but unavailable, the record is marked with `ocr_required` / `ocr_unavailable` or formula-related flags instead of being treated as normal text. `should_allow_term_extraction` currently allows `native_text_ok` and `partial_text` with non-empty text, and blocks `empty_text`, `ocr_required`, `ocr_unavailable`, `parse_failed`, and `unsupported_file_type`.

Formal upload and ingestion routes now create a `DocumentParseRecord` before knowledge indexing or upload-triggered term extraction. `/api/documents/upload`, `/api/knowledge/upload`, and legacy `/api/upload` return `parse_uid`, `parse_status`, `quality_status`, `quality_flags`, `should_allow_term_extraction`, `ingestion_status`, warnings, and `request_id` where applicable. Blocked documents keep the parse record but do not create active knowledge chunks or term candidates. `partial_text` may continue with risk flags, but it is not treated as an automatically approved result. The current implementation still does not run a live AI alignment engine as part of this parse-quality gate.

Parse quality risk is propagated to downstream knowledge objects. Legacy `Term` and `TerminologyCard` records can store `parse_uid`, `parse_block_uid`, `parse_quality_status`, `parse_quality_flags`, and `input_risk_labels`. `ConceptAlignmentCard` accepts the same parse metadata through the service/API layer and merges mapped risks into `risk_labels`. `partial_text` maps to `input_partial_text`, `mixed_quality` maps to `input_mixed_quality`, low-confidence OCR maps to `ocr_low_confidence`, and unavailable formula recognition maps to `formula_recognition_unavailable`. These risks force draft/needs-review handling and block ordinary create/update/status approval paths. They can only be overridden through the explicit teacher/admin review workflow with an override reason and audit trail. `empty_text`, OCR-unavailable, parse-failed, and unsupported-file inputs remain blocked before term or card creation.

Knowledge Governance API examples:

```http
GET /api/knowledge-sources?course=Data%20Structures&language=en
GET /api/knowledge-sources/<source_uid>
GET /api/knowledge-chunks?source_uid=<source_uid>&quality_status=native_text_ok
GET /api/knowledge-chunks/<chunk_uid>
POST /api/knowledge-sources/from-parse/<parse_uid>
```

`KnowledgeSource` is the governed source record for course materials and references. It keeps a stable `source_uid`, title, course/chapter, language, `source_type`, `source_role`, owner, visibility, trust level, status, parse UID, filename/file type, content hash, license note, version, and parse quality fields. `source_type` describes where the material came from, such as `course_material`, `textbook`, `paper`, `teacher_upload`, `student_upload`, `manual`, or `reference`. `source_role` describes how the source should be used in bilingual alignment, such as `english_course_material`, `chinese_reference_material`, `bilingual_reference`, or `student_private_material`. `trust_level` distinguishes `official_course`, `teacher_verified`, `reference_material`, `student_uploaded`, `unknown`, and `low_quality`. `visibility` is `public`, `course`, `private`, or `admin_only`.

`KnowledgeChunk` is the governed, traceable text block used by later retrieval and concept alignment work. It keeps `chunk_uid`, `source_uid`, parse/block UID, course/chapter/language, chunk index, text, normalized text, source locator, page/slide, block type, content hash, parse quality status/flags, trust level, governance status, and `embedding_status`. `KnowledgeVersion` records source-level lifecycle changes such as `created`, `updated`, `reingested`, `deprecated`, or `restored`. `KnowledgePermission` stores the minimal source permission tuple: principal type/id and read/write/admin access.

Formal knowledge ingestion now goes through `services/knowledge_ingestion.py`, which calls the Knowledge Governance service to create or associate `KnowledgeSource` and `KnowledgeChunk` records. The sync `/api/documents/upload` path, background `process_document_ingestion_job`, `/api/knowledge/upload`, and legacy `/api/upload` all preserve `source_uid`, `chunk_uid`, `parse_uid`, `parse_block_uid`, course, chapter, language, source type/role, trust level, quality status, and quality flags. Upload responses include `source_uid`, `chunk_count`, and sample `chunk_uids` while keeping legacy response fields. The legacy `KnowledgeDocument`, `DocumentChunk`, `CoursewareUpload`, and `Term` records remain compatible; new legacy term candidates also store `source_uid` and `chunk_uid` when available.

The unified ingestion gate allows `native_text_ok` to create active governed chunks and allows `partial_text` only as needs-review / low-quality governed chunks. `empty_text`, `ocr_required`, `ocr_unavailable`, `parse_failed`, and `unsupported_file_type` are blocked before active `KnowledgeChunk` creation. Successful governed ingestion records summary audit events such as `knowledge_source_created`, `knowledge_chunks_created`, and `knowledge_ingestion_completed`; blocked ingestion records `knowledge_ingestion_blocked`. These audit records store metadata summaries, not full chunk text or secrets.

`POST /api/knowledge-sources/from-parse/<parse_uid>` can build a governed source and chunks from existing `DocumentParseRecord` / `DocumentParseBlock` rows. It preserves `parse_uid`, `parse_block_uid`, source locator, quality status, and quality flags. Blocked parse states such as `empty_text`, `ocr_unavailable`, `parse_failed`, and `unsupported_file_type` do not create active `KnowledgeChunk` rows. `partial_text` creates needs-review chunks with quality risk flags. The current governance layer does not generate embeddings, does not create a vector database, does not run reranking, and does not call a real LLM alignment engine. Future evidence retrieval and Concept Card alignment should prefer governed `KnowledgeChunk` records over anonymous raw text.

Evidence Retrieval API example:

```http
POST /api/evidence/search
Content-Type: application/json

{
  "query": "Fourier transform",
  "course": "Signals and Systems",
  "chapter": "Frequency Domain",
  "language": "en",
  "limit": 5
}
```

The evidence retrieval foundation in `services/evidence_retrieval.py` searches governed `KnowledgeChunk` records with lexical keyword/phrase scoring only. It does not generate embeddings, use a vector database, call a reranker, or call a real LLM. Returned candidates include `source_uid`, `chunk_uid`, course/chapter/language, source type/role, trust level, quality status/flags, source locator, page/slide, a bounded snippet, matched terms, risk labels, and a `score`. This score is a retrieval score for ranking candidates; it is not a model confidence score and must not be treated as Concept Card confidence.

Default evidence filters exclude blocked/deprecated chunks and sources, parse-failed/OCR-unavailable/unsupported/empty-text quality states, and `low_quality` trust levels. `needs_review`, `partial_text`, and mixed/low-confidence quality inputs require explicit `include_needs_review=true`; low-quality sources require `include_low_quality=true`. The API records summary `AuditRecord` events (`evidence_retrieval_completed` / `evidence_retrieval_failed`) with query, filters, result count, top chunk/source UIDs, request ID, and latency. It does not store full chunk text, Authorization/Cookie headers, model output, or internal model reasoning.

Bilingual Evidence Workflow API example:

```http
POST /api/evidence/bilingual
Content-Type: application/json

{
  "english_term": "Fourier transform",
  "chinese_term": "傅里叶变换",
  "course": "Signals and Systems",
  "chapter": "Frequency Domain",
  "limit": 5
}
```

`services/bilingual_evidence_workflow.py` organizes two governed lexical retrieval passes: English evidence from English course/reference material and Chinese evidence from Chinese reference/course material. It returns `english_evidence_candidates`, `chinese_evidence_candidates`, risk labels, and a `draft_payload` shaped for later `ConceptAlignmentCard` creation. This workflow does not translate missing terms, does not perform final bilingual alignment, does not call a real LLM, and does not create an approved card.

The draft payload defaults to `draft` / `needs_review`; missing English or Chinese evidence forces review. It sets `confidence_score`, `model_name`, and `prompt_version` to null and leaves `alignment_reason` empty so the system does not fabricate model confidence or alignment reasoning. `retrieval_version` is set to `lexical-v1`. `bilingual_alignment_not_verified` is always present until a later alignment engine or teacher quality-control workflow explicitly verifies the card. Other risk labels include `no_english_evidence`, `no_chinese_evidence`, `missing_chinese_term`, `low_english_evidence_score`, `low_chinese_evidence_score`, `cross_language_evidence_missing`, `course_mismatch`, `chapter_mismatch`, `evidence_from_needs_review_source`, `evidence_from_partial_text`, and `evidence_from_low_trust_source`.

The bilingual API records summary `AuditRecord` events (`bilingual_evidence_retrieval_completed`, `bilingual_evidence_retrieval_failed`, and `concept_card_draft_payload_created`) with term/course/chapter inputs, result counts, top chunk UIDs, risk labels, request ID, and latency. It does not store full chunk text, Authorization/Cookie headers, model output, confidence, or internal model reasoning.

Chinese term candidate generation:

```http
POST /api/terms/chinese-candidates
Content-Type: application/json

{
  "english_term": "Fourier transform",
  "course": "Signals and Systems",
  "chapter": "Frequency Domain",
  "limit": 10
}
```

`services/chinese_term_candidates.py` generates candidate Chinese terms only from existing evidence-constrained sources: approved / teacher-verified `ConceptAlignmentCard` rows, legacy `Term` / `TerminologyCard` rows, and governed bilingual `KnowledgeChunk` patterns such as `中文术语（English term）` or `English term（中文术语）`. It does not call an LLM, does not call a translation API, and does not invent a Chinese term when no source contains one. `candidate_score` is a local ranking score, not alignment confidence.

Candidates include source identifiers (`source_uid`, `chunk_uid`, `card_uid`, `term_id`), source locator, bounded evidence snippet, trust/quality metadata, match pattern, score breakdown, and risk labels. Default filters exclude `low_quality`, blocked/deprecated, `parse_failed`, `ocr_unavailable`, `unsupported_file_type`, and empty-text sources. Risk labels include `candidate_not_alignment_verified`, `legacy_unverified_source`, `bilingual_pattern_extracted`, `candidate_from_partial_text`, `candidate_from_needs_review_source`, `candidate_from_low_trust_source`, `course_mismatch`, `chapter_mismatch`, `ambiguous_chinese_candidates`, `weak_candidate_score`, and `no_chinese_candidate_found`. The candidate API records summary audit events (`chinese_term_candidates_generated`, `chinese_term_candidates_not_found`, and `chinese_term_candidate_generation_failed`) without storing full chunk text or sensitive headers.

When `POST /api/evidence/bilingual` receives `auto_generate_chinese_candidates=true` and `chinese_term` is empty, it calls the candidate service, selects the highest-scoring candidate by default, retrieves Chinese evidence for that candidate, and returns both `chinese_term_candidates` and `selected_chinese_candidate`. The result keeps `candidate_not_alignment_verified`; it still does not perform final concept alignment, fabricate confidence, or approve a card.

Concept Card draft creation from evidence:

```http
POST /api/concept-cards/draft-from-evidence
Content-Type: application/json

{
  "english_term": "Fourier transform",
  "chinese_term": "傅里叶变换",
  "course": "Signals and Systems",
  "chapter": "Frequency Domain",
  "limit": 5,
  "auto_generate_chinese_candidates": false,
  "create": true
}
```

`/api/concept-cards/draft-from-evidence` runs the bilingual evidence workflow and either returns a safe draft payload (`create=false`) or saves it as a `ConceptAlignmentCard` draft (`create=true`, the default). Created cards are `needs_review` and never `approved`. The endpoint does not perform final concept alignment, does not call a real LLM, does not fabricate `confidence_score`, and does not generate a model-style `alignment_reason`. `confidence_score`, `model_name`, and `prompt_version` remain null/empty, while `retrieval_version` records the lexical evidence workflow version.

If `chinese_term` is omitted, callers may pass `auto_generate_chinese_candidates=true`. The endpoint then uses the evidence-constrained candidate service and stores the selected candidate summary in the draft payload / Chinese evidence payload. The saved card remains `needs_review`, preserves `candidate_not_alignment_verified`, and cannot be auto-approved.

To avoid duplicate drafts, the endpoint reuses an existing `draft` / `needs_review` card when `english_term + chinese_term + course + chapter + retrieval_version` already match. In that case the response returns `created=false` and `reused=true`. `force_create=true` can create another draft, but the card still cannot be approved automatically. Audit events include `concept_card_draft_payload_created`, `concept_card_draft_created`, `concept_card_draft_reused`, and `concept_card_draft_creation_failed`, with metadata summaries only.

Teacher/admin Concept Card review workflow:

```http
GET /api/concept-cards/review-queue
GET /api/concept-cards/<card_uid>/reviews
POST /api/concept-cards/<card_uid>/review
POST /api/concept-cards/<card_uid>/assign-reviewer
```

`services/concept_card_review.py` records human quality-control decisions in `ConceptCardReviewRecord`; optional assignment metadata is stored in `ConceptCardReviewAssignment`. Review actions include `approve`, `reject`, `request_revision`, `mark_needs_more_evidence`, `mark_candidate_incorrect`, `mark_translation_ambiguous`, `reopen`, `deprecate`, and reviewer assignment. Only teacher/admin API users can perform review actions. Students and unauthenticated users cannot approve or reject cards.

The review states reuse the existing Concept Card status values: `draft`, `needs_review`, `approved`, `rejected`, and `deprecated`. Drafts and needs-review cards appear in the default review queue; deprecated cards are hidden unless explicitly requested. Only the review API is intended to approve a card. Provider verification, draft-from-evidence, mock/fake/replay providers, and ordinary evidence retrieval cannot approve a card and cannot write `ConceptAlignmentCard.confidence_score`.

Approval requires a non-empty English term, Chinese term, course, at least one evidence side, a teacher/admin reviewer, and a reason or comment. Blocking risk labels such as `no_english_evidence`, `no_chinese_evidence`, `missing_chinese_term`, `bilingual_alignment_not_verified`, `candidate_not_alignment_verified`, `input_partial_text`, `input_mixed_quality`, `ocr_low_confidence`, `formula_recognition_unavailable`, `parse_failed`, `evidence_from_low_trust_source`, `course_mismatch`, and `chapter_mismatch` stop approval by default. A teacher/admin may set `allow_risk_override=true`, but must provide `override_reason`; the override is stored in the review record and an audit event. Approval does not delete risk labels and does not fabricate confidence.

Course-level review governance is handled by `services/course_review_policy.py`. `CourseReviewPermission` records who can review, approve, override risk, or assign reviewers for a specific course/chapter. Admin users keep a backend-wide governance path, but teacher/reviewer/assistant users must have an active course permission before they can see review-queue items for that course or perform review actions. Students cannot approve.

`CourseReviewPolicy` stores per-course approval rules: required evidence side (`english_only`, `chinese_only`, `both`, or `either`), minimum evidence count, blocking risks, override-allowed risks, override-forbidden risks, whether teacher override is allowed, whether admin is required for override, and whether two-step review is required. The default policy is conservative: human review required, both evidence sides required, at least two evidence items required, teacher override disabled, admin required for override, unverified alignment/partial-text/missing-evidence approvals blocked, and auto-approval unavailable.

Course review governance APIs:

```http
GET /api/review-policies
GET /api/review-policies/<policy_uid>
POST /api/review-policies
GET /api/review-permissions
POST /api/review-permissions
POST /api/review-permissions/<permission_uid>/revoke
```

Policy and permission writes are admin-only. Review actions now evaluate both the 7A quality gates and the course policy/permission gate. If `override_forbidden_risk_labels` contains a risk, override cannot approve it. If `require_admin_for_override=true`, teacher override is blocked even with `allow_risk_override=true`. If `require_two_step_review=true`, a teacher approve records `ready_for_admin_review` but keeps the card in `needs_review`; an admin second approval is required for `approved`. This task adds only backend governance and APIs, not a teacher UI.

Review audit events include `concept_card_review_record_created`, `concept_card_approved`, `concept_card_rejected`, `concept_card_revision_requested`, `concept_card_more_evidence_requested`, `concept_card_reopened`, `concept_card_deprecated`, `concept_card_risk_override_used`, and `concept_card_reviewer_assigned`. Audit records store card UID, action, previous/new status, reviewer role, reason code, resolved/remaining risk labels, override usage, and request ID. They do not store sensitive headers, API keys, or full evidence text.

Course-governance audit events include `course_review_policy_created`, `course_review_policy_updated`, `course_review_permission_granted`, `course_review_permission_revoked`, `concept_card_review_blocked_by_course_policy`, `concept_card_review_blocked_by_permission`, and `concept_card_risk_override_blocked_by_policy`. These records contain only summary fields such as course, policy UID, permission UID, reviewer role, action, blocked reason, risk labels, and request ID.

Teacher Concept Card review UI:

The Teacher/Admin navigation includes `Concept Card Review` / `概念卡审核`. It loads `GET /api/concept-cards/review-queue` and supports status, course, chapter, risk label, and text search filters. The list shows English term, Chinese term, course, chapter, status, risk labels, evidence counts, assignment summary, and verification summary when available. Teachers only see cards allowed by backend course permissions; students cannot access the review UI APIs.

Selecting a card opens a detail panel with basic Concept Card metadata, English evidence, Chinese evidence, risk labels, retrieval version, optional alignment verification summary, and `GET /api/concept-cards/<card_uid>/reviews` review history. The verification panel explicitly labels `alignment_confidence` as verification output, not final approval confidence. Provider verification is not displayed as an auto-approval basis.

The UI supports `approve`, `reject`, `request_revision`, `mark_needs_more_evidence`, optional `reopen`, optional admin `deprecate`, and optional reviewer assignment. Every action is submitted to `POST /api/concept-cards/<card_uid>/review` or `POST /api/concept-cards/<card_uid>/assign-reviewer`; the frontend never writes card state directly. Approve requires reason/comment, can include resolved risk labels, and only shows `override_reason` when risk override is requested. The backend CourseReviewPolicy / CourseReviewPermission gate remains the final authority and can reject a UI request with a stable JSON error and request ID.

This UI does not include CourseReviewPolicy management. Policies and permissions remain backend/API-managed in this task; a future admin policy-management UI can be added separately.

Teacher review demo seed:

```bash
python scripts/seed_review_demo.py --reset-demo
```

The seed is idempotent and creates only clearly marked demo records for `DEMO Signals and Systems`: demo teacher/admin/student accounts, a conservative `CourseReviewPolicy`, teacher/admin `CourseReviewPermission` rows, governed `KnowledgeSource` / `KnowledgeChunk` evidence, three needs-review Concept Cards, one rejected card with review history, at least three approved student-facing Concept Cards, active student course memberships, a `CourseStudentVisibilityPolicy`, a mock-only alignment verification summary, multiple mastered/favorited student learning states, submitted feedback items, and one resolved feedback item. It also creates one approved card in `DEMO Hidden Course` that the demo student cannot see because they are not enrolled there. It does not read API keys, does not call external services, and does not write generated databases into version control.

Demo accounts:

- Teacher: `review.teacher@lexibridge.local` / `Teacher1234`
- Admin: `review.admin@lexibridge.local` / `Admin1234`
- Student: `review.student@lexibridge.local` / `Student1234`
- Student 2: `review.student2@lexibridge.local` / `Student2234`

Manual review demo:

1. Initialize/migrate the database, then run `python scripts/seed_review_demo.py --reset-demo`.
2. Start the backend and open `frontend/index.html`.
3. Log in as the demo teacher and open `Concept Card Review`.
4. Filter course `DEMO Signals and Systems` and inspect `Fourier transform`, `Transfer function`, and `Convergence`.
5. Open a card detail panel to review English evidence, Chinese evidence, risk labels, verification summary, and Review History.
6. Submit `Request Revision` and confirm the history refreshes.
7. Try approving `Transfer function`; the backend policy should block missing Chinese evidence and the UI displays the returned `request_id`.
8. Log in as the demo admin to test risk override paths, or reject/reopen a card to verify history updates.
9. Log in as the demo student, open `Concept Cards`, and verify `Impulse response` is visible while `DEMO Hidden Course` cards are not listed.
10. Inspect the student Learning Progress panel; the demo students have mastered/favorited cards and submitted feedback items.
11. Return to the demo teacher, open `Concept Card Review`, and use the `Student Feedback` queue to acknowledge, resolve, request revision, reopen, or reject the demo feedback.
12. Open the `Course Learning Analytics` section in `Concept Card Review` to inspect approved card counts, mastery rate, low-mastery cards, feedback hotspots, and CSV export.

The frontend review UI includes stable `data-testid` markers for the queue, filters, card detail, evidence lists, review history, action forms, submit buttons, and request-id error/success display. The regression suite keeps DOM contract and Flask API workflow tests, and Task 9B.1 adds an independent Python Playwright/Chromium browser E2E gate for the student and teacher pilot flows.

Student Concept Card learning view:

The student navigation now includes `Concept Cards` / `课程概念卡`. This view is separate from the legacy glossary and reads only from teacher-approved `ConceptAlignmentCard` records that the current user is allowed to see for the card's course. The student APIs are approved-only and course-visible by design:

```http
GET /api/student/courses
GET /api/student/course-memberships
GET /api/student/progress
GET /api/student/concept-cards
GET /api/student/concept-cards/<card_uid>
POST /api/student/concept-cards/<card_uid>/state
POST /api/student/concept-cards/<card_uid>/feedback
GET /api/student/concept-cards/export
```

`GET /api/student/concept-cards` supports course, chapter, keyword, favorite, mastered, feedback, and pagination filters. It returns list summaries only: English term, Chinese term, course, chapter, short explanations, evidence count, source summary, favorite/mastered state, feedback state, and update time. It never returns `draft`, `needs_review`, `rejected`, or `deprecated` cards. It also filters approved cards through `StudentCourseMembership` and `CourseStudentVisibilityPolicy`; filtering by a course the student cannot access returns an empty list rather than revealing card contents.

`GET /api/student/concept-cards/<card_uid>` returns bounded student-safe detail for an approved card in an accessible course: bilingual explanations, structured English/Chinese evidence summaries, source title/role/trust/quality/locator, retrieval version, teacher-reviewed badges, and the caller's learning state. Non-approved cards and cards from unauthorized courses return a stable 404/403-style JSON response with `request_id`; access denial is audited with `student_concept_card_access_denied`. The detail API does not expose provider raw output, full audit records, review override reasons, or internal risk labels as raw engineering tags. `alignment_confidence` must not be displayed as final correctness; the UI labels teacher review as the trusted state.

Course-level student visibility:

- `StudentCourseMembership` records `user_id`, course, role in course, active/inactive/revoked status, enrollment and revoke metadata. Only active memberships grant access for `enrolled_only` courses.
- `CourseStudentVisibilityPolicy` controls course visibility with `public`, `enrolled_only`, `private`, or `disabled`. The conservative default is `enrolled_only`, no auditor view, teacher preview enabled, and cross-course search disabled.
- `GET /api/student/courses` returns the courses visible to the current user. The student UI uses this list for course context and shows `No accessible course concept cards.` when nothing is visible.
- Minimal backend APIs exist for admin-managed membership and visibility policy rows: `POST /api/student/course-memberships`, `POST /api/student/course-memberships/<membership_uid>/revoke`, `GET/POST /api/course-student-visibility-policies`. This task does not include a full course-membership admin UI.

`StudentConceptCardState` stores per-user learning state for approved cards: `card_uid`, `user_id`, course, favorite, mastered, mastered time, last viewed time, view count, and an optional personal note. The unique key is `user_id + card_uid`, so students can independently favorite or master the same card without modifying `ConceptAlignmentCard`.

Student actions:

- Favorite and mastered toggles call `POST /api/student/concept-cards/<card_uid>/state`.
- Feedback calls `POST /api/student/concept-cards/<card_uid>/feedback` and creates a `Feedback` row linked to the Concept Card UID. Feedback does not change card status.
- Export supports `scope=all|favorited|mastered|unmastered` and `format=json|csv`. Exports include only approved cards visible under the current user's course membership/policy, plus learning content and source summaries. They do not include internal audit/provider data.

Students cannot call the teacher review APIs to approve, reject, request revision, or change card status. Teachers and admins may open the student learning view, but it still uses approved-only behavior and respects `allow_teacher_preview` for course visibility. This task does not add admin review-policy UI, real LLM calls, embeddings, vector retrieval, or external network access.

Student learning progress:

`GET /api/student/progress` summarizes only the current student's visible approved Concept Cards. The denominator excludes hidden courses and all non-approved statuses. The main counters are `visible_card_count`, `mastered_count`, `unmastered_count`, `favorited_count`, `viewed_count`, `feedback_count`, and `mastery_rate`, where `mastery_rate = mastered_count / visible_card_count` and is `0` when there are no visible cards. Course and chapter summaries use the same approved-only and course-visibility filters. Recent activity is derived from `StudentConceptCardState.last_viewed_at`, `view_count`, and update timestamps.

The student frontend shows these counters in the Concept Cards page and provides a shortcut to continue unmastered cards. The progress panel never reveals cards from hidden courses and does not include draft, needs-review, rejected, or deprecated cards.

Student feedback return loop:

Student Concept Card feedback is stored in the existing `Feedback` table with `feedback_source=student_concept_card`, a stable `feedback_uid`, `card_uid`, course/chapter, message, suggested term, status, handler fields, and optional linked review metadata. New feedback starts as `submitted`; it does not modify `ConceptAlignmentCard.status`.

Teacher/admin feedback APIs:

```http
GET /api/concept-cards/student-feedback-queue
GET /api/concept-cards/<card_uid>/student-feedback
POST /api/concept-cards/student-feedback/<feedback_uid>/triage
```

Teachers only see feedback for courses where they have review permission; admins can inspect all feedback. Triage actions include `acknowledge`, `mark_resolved`, `mark_duplicate`, `reject_feedback`, `request_card_revision`, `reopen_card_for_review`, `link_to_existing_review`, and `add_teacher_note`. `request_card_revision` and `reopen_card_for_review` reuse the Concept Card review workflow, so CourseReviewPolicy and CourseReviewPermission remain the final authority. Student feedback never automatically reopens or changes a card.

Feedback triage records are stored in `ConceptCardFeedbackTriageRecord`, and AuditRecord events include `student_learning_progress_viewed`, `concept_card_feedback_queue_viewed`, `concept_card_feedback_triaged`, `concept_card_feedback_resolved`, `concept_card_feedback_linked_to_review`, and `concept_card_reopened_from_student_feedback`. Audit summaries store IDs, course, action, previous/new status, and request ID; they do not store sensitive headers, API keys, full evidence, or provider raw output.

Teacher learning analytics:

Teacher/admin analytics APIs provide aggregate course and card-level reports over approved Concept Cards:

```http
GET /api/teacher/learning-analytics
GET /api/teacher/learning-analytics/cards
GET /api/teacher/learning-analytics/export
```

The statistics include only `status=approved` `ConceptAlignmentCard` records in courses the caller is allowed to review. Draft, needs-review, rejected, and deprecated cards are excluded. Ordinary teachers are limited by `CourseReviewPermission`; admins can query broader data, but every analytics view/export is audited. Student-invisible courses are not mixed into ordinary teacher analytics.

Course-level metrics include approved card count, enrolled student count, viewed card count, mastered/unmastered counts, favorited count, feedback count, unresolved/resolved feedback, mastery rate, feedback rate, and average view count per card. Chapter-level metrics use the same approved-only and permission-filtered scope. Card-level metrics include mastered/favorited/viewed counts, feedback and unresolved feedback counts, latest feedback type/status, risk labels, review timestamp, and `priority_hint`.

`priority_hint` is a deterministic rules hint, not an AI judgment. Current values include `high_feedback_low_mastery`, `many_unresolved_feedback`, `missing_learning_activity`, `frequently_favorited_unmastered`, `needs_teacher_attention`, and `stable`.

Analytics responses and exports are aggregate-only. They do not include student personal identifiers, AuditRecord payloads, provider raw output, review override reasons, Authorization/Cookie headers, API keys, or full evidence text. Reports do not automatically reopen cards or create revision tasks; teachers must still use the existing feedback triage or Concept Card review workflow for `request_card_revision` and `reopen_card_for_review`.

The teacher frontend shows these analytics in the `Concept Card Review` workspace as `Course Learning Analytics`, with course/chapter filters, summary counters, chapter table, low-mastery list, feedback hotspots, and CSV export. The demo seed includes multiple approved cards, two demo students, multiple learning states, submitted feedback, and resolved feedback so this panel is non-empty after seeding.

Alignment Verification provider API:

```http
POST /api/alignment/verify
Content-Type: application/json

{
  "card_uid": "CONCEPT_CARD_UID",
  "provider": "fake-llm-v1",
  "fake_response_type": "valid",
  "attach_to_card": true
}
```

`services/alignment_verification.py` defines the alignment verification input/output schema and persists `AlignmentVerificationRun` rows. `services/alignment_providers.py` exposes four guarded providers:

- `mock-rule-v1`: deterministic rule-based mock provider used to verify structure, API flow, persistence, and audit records.
- `fake-llm-v1`: fake LLM-style provider used to test prompt construction, JSON output parsing, failure handling, and safety gates. It returns local fixture strings and never calls a real model.
- `deepseek-alignment-v1-disabled`: disabled external LLM adapter. It is registered so the API and audit path can handle a real-provider name, but external calls are blocked by default and return `provider_disabled`.
- `external-llm-replay-v1`: replay adapter that returns local fixture output through the same prompt/parser path. It never calls a real model and returns `provider_response_status=replayed`.

No provider calls DeepSeek, OpenAI, Claude, a translation API, embeddings, a vector database, a reranker, or any external network service in the current baseline. No real API key is read or required by tests. Task 9C.5L confirms that the production teacher workflow no longer calls legacy `POST /api/alignment/run`; the route remains an active compatibility surface because compatibility tests/safety probes and unknown external consumers still require a deprecation decision. Task 9C.5N.1 isolates queued legacy work behind the explicit `legacy-alignment` worker mode; the default worker does not consume it. Task 9C.5N.2 unifies route, synchronous upload, internal helper, and job-factory creation admission, adds Active/Freeze/Draining/Disabled states, read-only queue inspection, fenced safe failure, and an isolated shutdown rehearsal. Admission remains enabled by default in the release candidate. External/live provider intent remains blocked at route, worker, retry, queued-job, and direct-helper boundaries with `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED`.

External provider configuration lives in `services/llm_provider_config.py`. External LLM access is disabled unless a future task explicitly enables it through configuration. API keys may only be referenced by environment variable name, such as `DEEPSEEK_API_KEY`; key values are not stored in code, README, fixtures, `AlignmentVerificationRun`, or `AuditRecord`. `sanitize_provider_config()` removes `api_key` values and strips sensitive URL userinfo/query data. Timeout, retry, max prompt length, max output length, and rough cost-estimate gates are normalized before a provider can run.

Transport behavior lives in `services/llm_transport.py`:

- `DisabledLLMTransport`: returns `provider_disabled`.
- `FakeLLMTransport`: returns local fake JSON fixture strings.
- `ReplayLLMTransport`: returns local replay fixture strings.
- `HTTPTransport`: placeholder only; it returns a controlled disabled error in this task and is not used by tests.

The verification input contains `english_term`, `chinese_term`, course/chapter, bounded English/Chinese evidence summaries, optional candidate info, retrieval version, risk labels, parse quality risks, and source trust summary. Sensitive keys such as API keys, Authorization, Cookie, token, secret, and password are removed from prompt input, and evidence snippets are bounded.

Prompt and parser versions are explicit. `alignment_prompting.py` currently provides `alignment-v1`, which instructs a future provider to output JSON only, use only supplied evidence, return `insufficient_evidence` when evidence is missing, distinguish retrieval/candidate/alignment scores, and never auto-approve. `alignment_output_parser.py` currently provides `alignment-parser-v1` and `alignment-output-v1`, validating this JSON schema:

```json
{
  "alignment_decision": "aligned | likely_aligned | uncertain | not_aligned | insufficient_evidence",
  "alignment_confidence": 0.0,
  "recommendation": "needs_review | reject | insufficient_evidence | candidate_ambiguous | ready_for_human_review",
  "risk_labels": [],
  "evidence_assessment": {
    "english_evidence_supported": true,
    "chinese_evidence_supported": true,
    "cross_language_support": "strong | moderate | weak | missing",
    "evidence_limitations": []
  },
  "term_assessment": {
    "english_term_ok": true,
    "chinese_term_ok": true,
    "candidate_ambiguity": "none | low | medium | high",
    "notes": ""
  },
  "course_context_assessment": {
    "course_match": true,
    "chapter_match": true,
    "notes": ""
  },
  "explanation": "",
  "limitations": []
}
```

`fake-llm-v1` supports `fake_response_type=valid`, `non_json`, `missing_fields`, `confidence_out_of_range`, `insufficient_evidence`, and `ambiguous_candidate`. Non-JSON, missing fields, illegal enum values, non-list `risk_labels`, and out-of-range `alignment_confidence` produce a persisted failed `AlignmentVerificationRun` with parser error metadata. Provider output fields such as `auto_approve` are ignored.

`external-llm-replay-v1` supports `replay_response_type=valid`, `non_json`, `missing_fields`, `confidence_out_of_range`, `insufficient_evidence`, `ambiguous_candidate`, and `output_too_long`. It reuses `alignment-v1`, `alignment-parser-v1`, and `alignment-output-v1`. Replay results are not production results and cannot auto-approve.

Stable provider guardrail error codes include `provider_disabled`, `provider_not_configured`, `missing_api_key`, `provider_timeout`, `provider_rate_limited`, `provider_bad_response`, `provider_non_json_output`, `provider_schema_invalid`, `provider_confidence_out_of_range`, `provider_network_error`, `provider_cost_limit_exceeded`, and `provider_output_too_long`. These errors persist as failed `AlignmentVerificationRun` rows and are summarized in `AuditRecord`.

Provider governance lives in `services/provider_governance.py` and uses two tables:

- `AlignmentProviderPolicy`: records whether a provider is enabled, replay-only, allowed to call external services, allowed to attach results to cards, allowed to return production results, allowed to auto-approve, required to route through human review, scoped to courses/roles, and bounded by daily/monthly call and estimated-cost limits.
- `AlignmentProviderUsageRecord`: records provider usage summaries such as provider name/type, run UID, card UID, course/chapter, request ID, estimated tokens/cost, response status, and error code.

Policy defaults are conservative: `enabled=false`, `replay_only=true`, `allow_external_calls=false`, `allow_attach_to_card=false`, `allow_production_result=false`, `allow_auto_approve=false`, and `require_human_review=true`. `mock-rule-v1` and `fake-llm-v1` keep built-in local-test policies so existing local schema and parser tests can run. `external-llm-replay-v1` requires an explicit policy before `/api/alignment/verify` can use it. `deepseek-alignment-v1-disabled` remains blocked unless a future task adds a separate explicit real-provider enablement mode.

Provider governance APIs:

```http
GET /api/alignment/providers
GET /api/alignment/providers/<provider_name>/policy
POST /api/alignment/providers/<provider_name>/policy
GET /api/alignment/providers/<provider_name>/usage
POST /api/alignment/providers/<provider_name>/preflight
GET /api/alignment/providers/<provider_name>/preflight
GET /api/alignment/providers/preflight/<preflight_uid>
```

`POST /api/alignment/providers/<provider_name>/policy` is admin-only. It can enable replay-only test policies and set course scope, role scope, call limits, cost limits, prompt/output length limits, timeout, retry count, and attach permission. It still forces `allow_auto_approve=false` and `require_human_review=true`.

`/api/alignment/verify` now evaluates provider governance before running a provider. Missing/disabled policy, disallowed course, blocked course, usage limit, cost limit, disallowed external call, replay-only violation, or disallowed attach produce stable JSON and a failed `AlignmentVerificationRun` or policy-block audit. Additional governance error codes include `provider_policy_missing`, `provider_disabled_by_policy`, `provider_external_calls_not_allowed`, `provider_replay_only`, `course_not_allowed`, `course_blocked`, `provider_usage_limit_exceeded`, `provider_daily_cost_limit_exceeded`, `provider_monthly_cost_limit_exceeded`, `provider_human_review_required`, `provider_auto_approve_forbidden`, `provider_policy_invalid`, and `provider_attach_not_allowed`.

Provider preflight is a read-only readiness check for future real-provider enablement. `POST /api/alignment/providers/<provider_name>/preflight` creates an `AlignmentProviderPreflightRun` report with provider config status, policy readiness, course scope, call and cost limits, prompt/output length guards, human-review gates, API-key environment variable presence, and replay dry-run status. `api_key_present` is only a boolean; key values are never returned, stored, logged, or audited. Preflight does not modify provider policy, does not enable external calls, does not call the real network, does not approve cards, and does not write `ConceptAlignmentCard.confidence_score`. Even if `overall_ready=true`, `/api/alignment/verify` still must pass the governance gate for every request.

Preflight audit events are `provider_preflight_requested`, `provider_preflight_completed`, and `provider_preflight_failed`. They store only summaries such as provider name, course, readiness status, blocking reasons, warnings, and request ID. Replay dry-run uses local replay fixtures and only verifies that prompt construction, parser, failure handling, and audit paths are wired; it is not evidence that a real DeepSeek/OpenAI/Claude provider is enabled or reliable.

The verification output includes `alignment_decision`, `alignment_confidence`, `recommendation`, `risk_labels`, evidence/term/course assessments, explanation, limitations, `is_production_result`, and `can_auto_approve`. For `mock-rule-v1`, `is_production_result=false`, `can_auto_approve=false`, and `verification_status=mock_only`. For `fake-llm-v1` and replay providers, `is_production_result=false`, `can_auto_approve=false`, and successful fixture runs stay `needs_review`. Mock, fake, replay, or future external `alignment_confidence` is stored only on `AlignmentVerificationRun`; it is not written to `ConceptAlignmentCard.confidence_score`.

The three scores are intentionally separate:

- `retrieval_score`: ranks evidence candidates returned from governed `KnowledgeChunk` retrieval.
- `candidate_score`: ranks Chinese term candidates extracted from existing cards, legacy terms, or bilingual chunks.
- `alignment_confidence`: belongs to alignment verification output. In this task it is mock-only and not production-trustworthy.

`attach_to_card=true` is also controlled by provider policy. If `allow_attach_to_card=false`, verification can still create a run, but the card is not modified. If attach is allowed, it only merges verification risk labels and moves a draft card to `needs_review`. It never changes a card to `approved`, never writes `confidence_score`, never removes evidence, and does not overwrite human review. Audit events include `alignment_verification_requested`, `alignment_verification_completed`, `alignment_verification_failed`, `alignment_verification_blocked_by_policy`, `alignment_verification_attached_to_card`, `provider_policy_created`, `provider_policy_updated`, and `provider_usage_recorded`; they store summaries only, not full prompts, raw outputs, evidence text, sensitive headers, model output, or internal reasoning. Future real providers must reuse the same schema, parser, AuditRecord trace, evidence/risk handling, and human quality-control gates; high provider confidence alone must still not auto-approve a card.

`docs/openapi.yaml` is the local API contract for this MVP. It documents the stable core endpoints and the explicit error codes used for auth, permissions, quota, OCR, parsing, AI provider failures, file upload safety, PDF font availability, and background job status.

Long-running endpoints default to asynchronous execution:

- `POST /api/documents/upload` returns `document_id`, `job_id`, `parse_uid`, and parse quality fields before asynchronous ingestion proceeds.
- `POST /api/alignment/run` returns `alignment_run_id` and `job_id`.
- `POST /api/evaluation/run` returns `evaluation_run_id` and `job_id`.

Use `?sync=true` only for local tests or compatibility scripts that need immediate execution.

Contract checks:

```bash
bash scripts/run_python.sh -m pytest tests/test_api_contract.py
```

The standard JSON error envelope is:

```json
{
  "status": "error",
  "error_code": "PERMISSION_DENIED",
  "message": "You do not have permission to access this resource.",
  "details": {}
}
```

The standard success envelope is:

```json
{
  "status": "success",
  "message": "Operation completed.",
  "data": {}
}
```

`docs/evaluation_sample.jsonl` provides a 60-item smoke evaluation set covering signal processing, data structures, and mathematics / communication basics.

## Evaluation Harness

The Local MVP includes a repeatable evaluation harness. It is not a production benchmark, but it makes failures visible and prevents silent regressions in term extraction, evidence retrieval, alignment status, and auto-approval safety.

CLI flow:

```bash
python scripts/run_evaluation.py --set docs/evaluation_sample.jsonl --split test
```

API flow:

1. Login as Teacher or Admin.
2. Create a set:

```http
POST /api/evaluation/sets
```

```json
{
  "name": "lexibridge_smoke_v1",
  "discipline": "mixed",
  "description": "60-item Local MVP smoke evaluation."
}
```

3. Import JSONL:

```http
POST /api/evaluation/items/import
```

```json
{
  "evaluation_set_id": 1,
  "file_path": "docs/evaluation_sample.jsonl"
}
```

4. Run:

```http
POST /api/evaluation/run
```

```json
{
  "evaluation_set_id": 1,
  "split": "test",
  "model_version": "local-or-deepseek",
  "prompt_version": "alignment_v1",
  "retrieval_version": "local_lexical_v1"
}
```

5. Inspect:

```http
GET /api/evaluation/runs/<id>
```

Main metrics:

- `extraction_precision`: correct professional terms divided by extracted candidates.
- `extraction_recall`: expected gold terms found by extraction.
- `english_evidence_accuracy`: returned English evidence correctness.
- `chinese_evidence_accuracy`: returned Chinese evidence correctness.
- `evidence_accuracy`: both-side evidence correctness.
- `alignment_accuracy`: actual `alignment_status` equals gold status.
- `false_positive_rate`: positive alignment when gold status is not positive.
- `auto_approval_error_rate`: wrong `auto_approved` rate.
- `no_evidence_forced_alignment_rate`: missing evidence but system still claims positive alignment.
- `ocr_noise_term_rate`: OCR noise among OCR-origin term candidates.

`no_evidence_forced_alignment_rate` must remain `0`. If it rises above `0`, the platform is again forcing concept alignment without enough bilingual evidence.

Smoke release gate:

- `extraction_precision >= 0.75`
- `extraction_recall >= 0.60`
- `evidence_accuracy >= 0.70`
- `alignment_accuracy >= 0.70`
- `false_positive_rate <= 0.10`
- `auto_approval_error_rate <= 0.05`
- `no_evidence_forced_alignment_rate == 0`

The smoke set has only 60 items. It is useful for local regression, not a production accuracy claim. A real gold set should grow beyond 300 reviewed items across courses and document types.

## Demo Quick Start

PR-8 adds a deterministic demo package for course reports, classroom demos, and small pilot trials. Demo data is self-authored and does not include copyrighted textbook excerpts.

Seed and run the demo:

```bash
bash scripts/run_python.sh scripts/migrate_db.py --apply
bash scripts/run_python.sh scripts/seed_demo_data.py
bash scripts/run_backend.sh
bash scripts/run_worker.sh
bash scripts/run_python.sh scripts/run_demo_flow.py
```

If port `5000` is occupied:

```bash
BACKEND_PORT=5001 bash scripts/run_backend.sh
```

The demo seed creates:

- `DS101 - Data Structures and Algorithms`
- `SP101 - Signal Processing Basics`
- `MATH101 - Engineering Mathematics`
- 61 gold evaluation items across the three courses
- self-authored English course notes, Chinese reference notes, OCR/image samples, and formula samples
- demo users:
  - `admin@lexibridge.local / Admin1234`
  - `teacher@lexibridge.local / Teacher1234`
  - `student@lexibridge.local / Student1234`
  - `student2@lexibridge.local / Student2234`

Teacher demo path:

1. Log in as `teacher@lexibridge.local`.
2. Open `Teacher Workspace`.
3. Select `SP101`.
4. Inspect course documents and jobs.
5. Inspect an `AlignmentRun`.
6. Open Quality Control and review cards such as `Fourier Transform`.

Student demo path:

1. Log in as `student@lexibridge.local`.
2. Open `Student Workspace`.
3. Select `SP101`.
4. Search `Fourier Transform`.
5. View evidence, risk notes, provider status, and formula evidence status.
6. Favorite, mark mastered, and submit feedback.

Admin demo path:

1. Log in as `admin@lexibridge.local`.
2. Open `Admin Workspace`.
3. Inspect users, courses, global jobs, EvaluationRuns, logs, usage, and mock billing.

Run the automated demo flow:

```bash
python scripts/run_demo_flow.py --summary-json
```

Expected local-provider behavior:

- document ingestion: `PASS`
- alignment run: `PASS`
- student search and feedback: `PASS`
- evaluation run: `PASS`
- `auto_approved_cards=0` when `AI_PROVIDER=none/local/mock`
- `no_evidence_forced_alignment_rate=0`

Detailed demo scripts:

- `docs/demo-script-teacher.md`
- `docs/demo-script-student.md`
- `docs/demo-script-admin.md`
- `docs/pilot-feedback-template.md`
- `pilot_feedback/student_feedback_form.md`
- `pilot_feedback/teacher_feedback_form.md`
- `pilot_feedback/feedback_summary_template.md`

## Pilot Package

PR-15 adds a course pilot package for teachers, students, administrators, and pilot coordinators. It is designed for small real-course trials and final project presentation material. It does not claim production readiness.

Start with:

- `pilot_package/README.md`: pilot package index and role-based reading path.
- `pilot_package/pilot_runbook.md`: end-to-end pilot process from preparation to retrospective.
- `pilot_package/teacher_manual.md`: teacher workflow for course setup, uploads, jobs, AlignmentRun, QC, feedback, export, KB versions, and EvaluationRun.
- `pilot_package/student_manual.md`: student workflow for course selection, terminology search, evidence review, favorite/mastered marks, feedback, personal uploads, and review export.
- `pilot_package/admin_manual.md`: admin workflow for users, jobs, EvaluationRun, AI governance, KnowledgeBaseVersion, retrieval diagnostics, pilot reports, backup, health, and readiness checks.
- `pilot_package/data_authorization_guide.md`: source type, license type, authorization status, and restricted-source rules.
- `pilot_package/privacy_and_risk_notice.md`: privacy scope, AI/OCR risks, non-production boundary, and teacher-review disclaimer.
- `pilot_package/pilot_metrics.md`: usage, quality, teacher-side, and student-side pilot metrics.
- `pilot_package/post_pilot_report_template.md`: final pilot report structure.
- `pilot_package/demo_vs_real_pilot.md`: why demo success does not prove real-course success.
- `pilot_package/final_presentation_materials_index.md`: material index for course report, poster, and presentation.

Course report and final presentation materials:

- `docs/final-project-summary.md`
- `docs/course-report-materials.md`
- `docs/poster-content-outline.md`
- `docs/presentation-script-outline.md`

Validate and summarize the package:

```bash
python scripts/check_pilot_package.py
python scripts/generate_pilot_package_summary.py --output docs/generated/pilot_package_summary.md
python scripts/export_final_project_snapshot.py --output docs/generated/final_project_snapshot.json
```

The final snapshot is a safe JSON summary for reports and presentations. It lists core capabilities, demo courses, evaluation metric names, KB/versioning support, retrieval backend status, AI governance status, known limitations, and pilot package files. It does not include API keys, tokens, local secrets, or personal document content.

## Final Delivery

PR-16 adds the final course handoff package in `final_delivery/`. Use it when preparing the final code submission, course report, presentation, poster, and demo checklist.

Key files:

- `final_delivery/README.md`: final delivery index.
- `final_delivery/final_delivery_checklist.md`: final code, feature, documentation, and safety checklist.
- `final_delivery/final_acceptance_report.md`: acceptance report across teacher/student/admin workflows, OCR, retrieval, alignment, evaluation, jobs, security, demo, and pilot package.
- `final_delivery/final_test_report.md`: final test report generated from project validation records.
- `final_delivery/final_demo_script.md`: final teacher, student, admin, and course-learning demo script.
- `final_delivery/final_screenshot_checklist.md`: screenshots to collect for PPT, poster, and report.
- `final_delivery/final_course_report_materials.md`: course report material with computational thinking and design thinking.
- `final_delivery/final_presentation_outline.md`: 10-slide presentation outline.
- `final_delivery/final_poster_copy.md`: poster text copy.
- `final_delivery/final_release_manifest.json`: generated release manifest.

Run final checks:

```bash
python scripts/check_final_delivery.py
python scripts/generate_final_release_manifest.py --output final_delivery/final_release_manifest.json
python scripts/build_final_release.py
```

`build_final_release.py` runs material checks, regenerates the manifest, builds the release zip, runs sensitive-file checks, and records production-readiness blockers. A `NOT READY` production-readiness result is expected at this stage because the target is local pilot-ready / course demonstration-ready, not production deployment.

## v1 Core Engine Additions

The current codebase now records the key objects described in `LexiBridge_AI_v1.0_Core_Engine_最终版实现文档.docx`:

- `ConceptAlignmentCard`: core bilingual concept-alignment data model with stable `card_uid`, course/chapter scope, bilingual terms and explanations, evidence JSON/text fields, confidence score, risk labels, review status, source references, model/prompt/retrieval metadata, version number, and timestamps. This data model does not claim that the AI alignment engine is complete.
- `AuditRecord`: system-level observable audit record for Concept Card creation, update, status change, and selected validation failures. It stores safe before/after snapshots, input/output summaries, changed fields, actor metadata, result/error details, and reserved model/prompt/retrieval metadata fields for future alignment-engine work. It does not record a model's internal reasoning chain.
- `DocumentParseRecord` and `DocumentParseBlock`: document parsing quality records and traceable parsed blocks. They distinguish native text success, partial text, empty text, OCR required/unavailable, unsupported file types, parse failures, and formula/image quality warnings before downstream knowledge ingestion or term extraction.
- `KnowledgeSource`, `KnowledgeChunk`, `KnowledgeVersion`, and `KnowledgePermission`: governed knowledge assets with stable source/chunk UIDs, course/chapter scope, language, source type/role, visibility, trust level, parse quality status/flags, source-level version records, and minimal read/write/admin permission tuples. They do not create embeddings or vector indexes in this task.
- `AlignmentRun`: every document or direct-term alignment records provider, model, prompt version, retrieval version, extracted term count, card count, auto-approved count, QC count, needs-evidence count, conflict count, failed count, status metrics, and failure message.
- `BackgroundJob` and `BackgroundJobEvent`: long document ingestion, alignment, and evaluation workflows now run through a local SQLite-backed queue with progress, retry, cancel, and event history.
- `TerminologyCard`: stores normalized English/Chinese terms, evidence snapshots, English/Chinese evidence scores, alignment status, score breakdown, quality flags, AI provider/model, prompt version, retrieval version, source alignment run, approval/rejection metadata, and risk notes.
- `ModelPromptRegistry`: tracks enabled provider/model/prompt/retrieval combinations and last evaluation run.
- `EvaluationSet`, `EvaluationItem`, `EvaluationRun`: provide local smoke evaluation for extraction precision/recall, evidence accuracy, alignment accuracy, false positive rate, auto-approval error rate, OCR noise, and no-evidence forced alignment.
- `PersonalAccessAudit`: records admin access to another user's private personal knowledge base or document chunks.

Auto approval remains strict: a card needs confidence `>=85`, strong English evidence, strong Chinese evidence, no quality flags, and a live provider. Local heuristic/mock output, missing evidence, low OCR confidence, domain mismatch, or ambiguous/conflicting candidates are routed to QC or `needs_more_evidence`.

Run the existing migration command to create or update local tables, including `concept_alignment_card` and `audit_record`:

```bash
bash scripts/run_python.sh scripts/migrate_db.py --apply
```

Legacy `Term` and `TerminologyCard` tables are retained. Future migration work can map old term rows into `ConceptAlignmentCard` records without deleting legacy data.

## Validation Commands

Before committing, run the local pre-release gate from the repository root:

```bash
bash scripts/run_python.sh scripts/dev_check.py
```

The same command works from macOS, Linux, and Windows PowerShell when the project virtual environment is active. It runs the release safety scan, the full pytest suite, database initialization against a temporary SQLite file, and a backend import/API smoke check. It does not require a real `.env` or live API keys, and it writes runtime files to a temporary directory instead of the project root.

```bash
PYTHONPYCACHEPREFIX=/tmp/lexibridge-pycache python -m py_compile backend/app.py scripts/migrate_db.py backend/services/ai_providers.py backend/services/ocr.py
bash -n scripts/run_backend.sh
bash scripts/run_python.sh scripts/migrate_db.py --apply
```

PR-5 security and migration regression tests:

```bash
bash scripts/run_python.sh -m pytest tests/test_api_contract.py
bash scripts/run_python.sh -m pytest tests/test_auth.py tests/test_permissions.py
bash scripts/run_python.sh -m pytest tests/test_upload_security.py
bash scripts/run_python.sh -m pytest tests/test_personal_privacy.py
bash scripts/run_python.sh -m pytest tests/test_migrations.py
```

PR-6 background job regression tests:

```bash
bash scripts/run_python.sh -m pytest tests/test_jobs.py tests/test_job_api.py tests/test_worker.py
```

PR-8 demo regression tests:

```bash
bash scripts/run_python.sh -m pytest tests/test_demo_seed.py
bash scripts/run_python.sh -m pytest tests/test_demo_flow.py
bash scripts/run_python.sh -m pytest tests/test_demo_evaluation.py
```

Full test suite:

```bash
bash scripts/run_python.sh -m pytest
```

Frontend inline JavaScript syntax:

```bash
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
node --check /tmp/lexibridge-frontend.js
```

## Package A Clean Release

```bash
bash scripts/package_release.sh
```

The script runs Python compile checks, PR-5 package tests, creates a dated release zip such as `dist/LexiBridge-AI-Local-MVP-v0.8-20260622.zip`, and runs:

```bash
python scripts/check_release_package.py dist/<release>.zip
```

Run the broader release safety check before handoff:

```bash
python scripts/check_release_safety.py
python scripts/check_release_safety.py dist/<release-dir-or-zip>
```

The release checker rejects `.git`, `.env`, database files, uploads, derived images, virtual environments, cache directories, Mac metadata, nested archives, personal local paths, logs, temporary files, and obvious API-key patterns. The default repository scan checks files that are tracked or eligible to be added; ignored local files such as `.env` stay local and are not deleted.

## Deployment Readiness

LexiBridge AI is currently the LexiBridge AI Pilot v1.0 Candidate, classified as
a Controlled Academic Pilot Release. It is not production-ready.

Environment templates:

- `.env.example`: safe common template.
- `.env.development.example`: local demo/development settings.
- `.env.production.example`: conservative production placeholder template.

Create a local development env:

```bash
cp .env.development.example .env
python scripts/check_env.py --env development --file .env
```

Check a production candidate env:

```bash
python scripts/check_env.py --env production --file .env.production
```

The production check fails for unsafe settings such as `DEBUG=true`, weak `SECRET_KEY`, SQLite, wildcard CORS, mock AI/payment/email, disabled log redaction, or placeholder API keys.

Run the local worker:

```bash
bash scripts/run_worker.sh
```

Collect a health report:

```bash
bash scripts/run_python.sh scripts/collect_health_report.py
```

The report includes users, courses, documents, knowledge chunks, terminology cards, queued/running/failed jobs, OCR/provider failure counts, latest EvaluationRun metrics, upload size, derived upload size, and database size.

Back up local data:

```bash
python scripts/backup_local_data.py --output backups/lexibridge_backup_$(date +%Y%m%d_%H%M%S).zip
```

Restore local data into a separate target:

```bash
python scripts/restore_local_data.py --backup backups/example.zip --target ./restore_test
```

`.env` is not included in backups by default. Use `--include-env` only when you understand the secret-leak risk.

Cost-control helpers are in:

```text
backend/services/cost_control.py
```

Tracked usage events include document parsing, OCR pages, formula OCR calls, AI term extraction, AI alignment, knowledge search, evaluation items, and PDF export. Exceeded quotas should return `QUOTA_EXCEEDED`.

Production readiness report:

```bash
python scripts/check_production_readiness.py
```

For the current Local MVP, `NOT READY` is expected. Required before production:

- PostgreSQL or managed production database.
- Durable object storage.
- HTTPS and strict CORS allowlist.
- Real SMTP or disabled email flow.
- Real payment or disabled billing UI.
- Production queue such as Celery/RQ/Redis.
- Monitoring and alerting.
- Backup and restore drill.
- Privacy policy and data retention policy.
- Teacher/professional reviewed gold set.

## Database And Object Storage Migration Readiness

PR-11 prepares the data layer for a future PostgreSQL + object storage deployment while keeping SQLite and local uploads working for development.

Environment settings:

```env
DATABASE_ENGINE=sqlite
DATABASE_URL=sqlite:///lexibridge.db
STORAGE_BACKEND=local
LOCAL_STORAGE_ROOT=backend/uploads
```

Production template uses:

```env
DATABASE_ENGINE=postgresql
DATABASE_URL=postgresql://user:password@host:5432/lexibridge
STORAGE_BACKEND=s3
```

Run schema audit:

```bash
python scripts/schema_audit.py
```

Run database readiness check:

```bash
python scripts/check_database_readiness.py
```

Export SQLite to JSONL:

```bash
python scripts/export_sqlite_data.py --db backend/lexibridge.db --output exports/sqlite_export_YYYYMMDD
```

Dry-run PostgreSQL import:

```bash
python scripts/import_postgres_data.py --input exports/sqlite_export_YYYYMMDD --database-url postgresql://user:password@host:5432/lexibridge
```

Check storage config:

```bash
python scripts/check_storage_config.py --env development --file .env.example
```

Migrate legacy local files into StorageService-managed keys:

```bash
python scripts/migrate_local_files_to_storage.py --dry-run
python scripts/migrate_local_files_to_storage.py --apply
```

Check storage integrity:

```bash
python scripts/storage_integrity_check.py
```

Related docs:

- `docs/database-migration-plan.md`
- `docs/object-storage-design.md`
- `docs/storage-migration-plan.md`
- `docs/schema-audit-report.md`
- `docs/production-data-readiness.md`

Deployment docs:

- `docs/deployment-readiness.md`
- `docs/environment-config.md`
- `docs/logging-and-monitoring.md`
- `docs/backup-and-recovery.md`
- `docs/cost-control.md`
- `docs/production-risk-boundary.md`
- `docs/production-readiness-checklist.md`

Additional docs:

- `docs/api-contract.md`
- `docs/security-and-privacy-design.md`
- `docs/migration-and-testing-strategy.md`
- `docs/release-checklist.md`

## Pilot Readiness 9A

Task 9A adds a system-level pilot readiness audit instead of new product features. The check verifies core end-to-end flows, permission boundaries, database fresh/upgrade paths, OpenAPI route parity, data integrity, request IDs, release safety, and the no-real-network provider boundary.

Run the full pilot readiness check:

```bash
bash scripts/run_python.sh scripts/pilot_readiness_check.py
```

For a faster local loop that skips the full pytest pass but still runs targeted pilot gates:

```bash
bash scripts/run_python.sh scripts/pilot_readiness_check.py --skip-full-tests
```

The readiness check uses a temporary SQLite database and temporary uploads directory. It removes real LLM API key environment variables from its subprocess environment, keeps external providers disabled, verifies legacy healthcheck live-probe blocking, verifies legacy alignment route/worker external-execution blocking, scans for runnable legacy external alignment jobs, and does not call DeepSeek, OpenAI, Claude, translation APIs, embeddings, vector databases, or rerankers.

Pilot readiness documents:

- `docs/architecture_map.md`: current implemented data objects, services, flows, states, and permission boundaries.
- `docs/technical_debt_register.md`: technical debt with severity, impact, recommended action, and pilot-blocking status.
- `docs/pilot_readiness_report.md`: latest pilot readiness report generated from actual checks.
- `docs/pilot_runbook.md`: local/small-pilot runbook, backup/restore notes, demo route, provider boundary, and troubleshooting.

Current deployment boundary:

- Flask development server is not production deployment.
- SQLite is acceptable for local demo and controlled small-course pilot only.
- Demo accounts are local-only and must not be used in production.
- External LLM providers remain disabled by default.
- Mock/fake/replay alignment providers are workflow and parser checks, not production semantic verification.

## Backend Route Structure

Most Flask routes still live in `backend/app.py` while the project is being split in narrow, contract-tested slices. Task 9C.1 extracts only the teacher learning analytics endpoints into `backend/routes/teacher_learning_analytics.py`. Task 9C.2 extracts only the student Concept Card learning endpoints into `backend/routes/student_concept_cards.py`. Task 9C.3A extracts only the teacher Concept Card review queue/history/action/assignment endpoints into `backend/routes/concept_card_review.py`. Task 9C.3B extracts only the teacher-facing student feedback queue/card-feedback/triage endpoints into `backend/routes/concept_card_feedback.py`; student feedback submission remains part of the student Concept Card route module. Task 9C.4A extracts only read-only provider governance/preflight GET endpoints into `backend/routes/provider_governance.py`. Task 9C.4B extracts only provider policy mutation into `backend/routes/provider_policy.py`. Task 9C.4C extracts only provider preflight execution into `backend/routes/provider_preflight.py`. Task 9C.4D.1 moves `/api/alignment/verify` execution orchestration into `backend/services/alignment_verification_execution.py`, and Task 9C.4E extracts the remaining thin HTTP adapter into `backend/routes/alignment_verification.py`. Task 9C.4G extracts only the legacy admin alignment run listing into `backend/routes/admin_alignment_runs.py`. Task 9C.4I extracts only the legacy provider admin observability GET endpoints into `backend/routes/legacy_provider_admin_observability.py`. Task 9C.4J does not extract a route; it moves legacy provider registry seed and flush behavior into `backend/services/legacy_provider_registry_seed.py` while callers keep existing commit/rollback ownership. Task 9C.4K extracts only the seed-backed legacy provider admin configuration GET endpoints into `backend/routes/legacy_provider_admin_configuration.py`; prompt mutation and healthcheck remain separate tasks. Task 9C.4L.1 disables the legacy healthcheck live-probe transport path; `live_probe=true` now returns a safe disabled result instead of calling provider transport. Task 9C.4M moves legacy healthcheck local readiness calculation into `backend/services/legacy_provider_local_readiness.py`. Task 9C.4N extracts the thin legacy healthcheck POST adapter into `backend/routes/legacy_provider_admin_healthcheck.py`; the route module still owns seed, health-field writes, commit, and the legacy response envelope, while live transport remains disabled. Task 9C.4O characterizes `POST /api/admin/ai/prompts`; Task 9C.4P accepts the small-pilot `LEGACY_PROMPT_MUTABLE_REVISION_V1` policy; Task 9C.4Q implements that policy in `backend/services/legacy_provider_prompt_mutation.py`, so prompt mutation now owns seed, mutable key/version upsert, one commit, and explicit rollback in an application service; Task 9C.4R moves the thin POST adapter into `backend/routes/legacy_provider_admin_configuration.py` while preserving the shared `admin_ai_prompts` endpoint. Task 9C.4S characterizes legacy `POST /api/alignment/run` and concludes `DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`; Task 9C.4T accepts `LEGACY_ALIGNMENT_RUN_DEPRECATION_V1`, classifying that route as temporary frontend compatibility only; Task 9C.4U blocks legacy alignment external/live execution without moving the route. Task 9C.4V defines the formal document alignment workflow contract, Task 9C.4W adds `DocumentAlignmentWorkflowRun` and `DocumentAlignmentWorkflowItem`, Task 9C.4X adds admission/start, Tasks 9C.5A-9C.5C establish bootstrap, per-item recovery, and processing, Task 9C.5D adds local formal worker dispatch and BackgroundJob result mapping, and Task 9C.5E adds permission-safe read-only run/item query services with SQL pagination. Routes, OpenAPI, frontend cutover, disabled response, and final legacy removal remain future slices. These modules register with `app.add_url_rule` to preserve URL, method, endpoint name, response, audit, permission, visibility, review-policy, feedback-triage, provider-governance, provider-policy, provider-preflight, alignment-verification, legacy-observability, legacy-configuration, legacy-healthcheck, prompt-mutation compatibility, and export behavior.

Task 9C.2.1 adds `backend/routes/shared.py` with `RouteCoreDependencies`, a small immutable bundle for common route infrastructure such as request IDs, actor/auth context, response helpers, audit service, current-time helper, and the database handle. Domain services, domain models, course visibility, and review permissions remain explicit dependencies in each route module. This is staged route extraction, not a full app factory, Blueprint migration, or dependency injection container.

Task 9C.5F supersedes the earlier route-status sentence above: the formal
document-alignment API now has `app.add_url_rule` adapters for asynchronous
start, run status, and paginated items plus a parsed OpenAPI contract. The
routes remain thin and hide BackgroundJob ownership. Task 9C.5F.1 adds a
server-owned deterministic provider selection (`mock-rule-v1`,
`mock-rule-v1:v1`, `alignment-v1`), freezes it at Admission, removes silent
item-preparation fallback, and aligns policy, preflight, and attach. Task
9C.5F.2 freezes three counted processing-failure outcomes at Admission, permits
two attempt-fenced requeues, and keeps historical job budgets unchanged. Task
9C.5G v3 verifies authenticated HTTP admission, formal worker execution,
polling, pagination, source-scoped concurrent replay, business partial failure,
recovery, and same-origin browser API access on local SQLite. Task 9C.5H adds
the minimal teacher frontend cutover: server-issued governed source identity,
crypto-backed Idempotency-Key handling, formal POST/run polling, API-paginated
items, duplicate-start prevention, and sessionStorage reload recovery. The
legacy route remains registered after Task 9C.5L identifies its remaining
compatibility boundary. Legacy deprecation/410, a historical formal run center, a full review workbench,
PostgreSQL, a supervised worker, and live-provider operation remain future
work.

Task 9C.3C establishes the first cumulative route-refactor Git checkpoint. Because earlier route extraction work was verified before it was committed, this checkpoint is intentionally honest: it does not fabricate historical task-by-task commits. It records the current route extraction state in `docs/route_extraction_checkpoint.md` and must be verified from a clean worktree before any provider governance route extraction begins.

Repository hygiene rules for future checkpoints:

- Do not store release copies, backup packages, browser artifacts, SQLite databases, uploads, or virtual environments inside the repository.
- Keep historical archives outside Git. The incomplete historical `lexibridge AI/` archive is preserved under the user's Documents archive directory and is not a build, test, or runtime dependency.
- Use precise path staging, not `git add .`, when large untracked sets exist.
- Before declaring a checkpoint reproducible, verify it from a fresh `git worktree` with full pytest, release safety, dev check, browser E2E, and pilot readiness.

Clean worktree verification pattern:

```bash
git worktree add /private/tmp/lexibridge-checkpoint-verify HEAD
cd /private/tmp/lexibridge-checkpoint-verify

bash scripts/run_python.sh -m pytest -q
bash scripts/run_python.sh scripts/check_release_safety.py
bash scripts/run_python.sh scripts/dev_check.py
bash scripts/run_python.sh scripts/run_browser_e2e.py \
  --json-output /private/tmp/checkpoint-full-e2e.json
bash scripts/run_python.sh scripts/pilot_readiness_check.py \
  --json-output /private/tmp/checkpoint-readiness.json
```

## Pilot Hardening 9B / 9B.1

Task 9B keeps the product surface unchanged and hardens the pilot startup checks. Task 9B.1 installs and gates real Chromium browser E2E for the student and teacher pilot flows:

- `scripts/pilot_readiness_check.py` now reports one of `READY`, `READY_WITH_CONDITIONS`, or `NOT_READY`.
- The current expected verdict for local demo / small-course pilot is `READY_WITH_CONDITIONS`.
- `scripts/pilot_backup.py` creates a SQLite + uploads backup with `backup_manifest.json` and SHA-256 hashes.
- `scripts/verify_pilot_backup.py` verifies manifest, hashes, SQLite integrity, core tables, and secret-like content.
- `scripts/pilot_restore.py` restores verified backups to explicit targets and refuses overwrite unless `--force` is supplied.
- `scripts/run_browser_e2e.py` runs student and teacher browser E2E flows in real Chromium with localhost-only network routing.
- `requirements-e2e.txt` records browser test dependencies separately from production/runtime dependencies.

Run readiness with a machine-readable result:

```bash
bash scripts/run_python.sh scripts/pilot_readiness_check.py \
  --profile small-pilot \
  --json-output /private/tmp/lexibridge-pilot-result.json
```

Create, verify, and restore a pilot backup:

```bash
bash scripts/run_python.sh scripts/pilot_backup.py \
  --database /absolute/path/to/lexibridge.db \
  --uploads /absolute/path/to/uploads \
  --output /private/tmp/lexibridge-pilot-backup

bash scripts/run_python.sh scripts/verify_pilot_backup.py \
  --backup /private/tmp/lexibridge-pilot-backup

bash scripts/run_python.sh scripts/pilot_restore.py \
  --backup /private/tmp/lexibridge-pilot-backup \
  --database-target /private/tmp/lexibridge-restored.db \
  --uploads-target /private/tmp/lexibridge-restored-uploads
```

Run browser E2E:

```bash
bash scripts/bootstrap_e2e.sh
bash scripts/run_python.sh scripts/run_browser_e2e.py \
  --json-output /private/tmp/lexibridge-browser-e2e.json
```

If Playwright or Chromium is not installed, browser E2E returns `E2E_ENVIRONMENT_UNAVAILABLE` instead of pretending to pass. In that case readiness remains `READY_WITH_CONDITIONS` with `browser_e2e_not_executed`. If browser E2E runs and fails, readiness is `NOT_READY`.

Current local browser gate baseline:

- Playwright `1.60.0`;
- Chromium `148.0.7778.96`;
- student and teacher flows pass twice with real DOM actions;
- console errors/page errors are empty;
- page-owned external dependency requests are empty;
- student and teacher export downloads are verified non-empty.

## Pilot Feedback Loop

PR-10 adds a local pilot feedback loop for student/teacher trials:

```text
student feedback
-> teacher triage
-> terminology card QC
-> convert important issues to EvaluationItem
-> convert product/data issues to IterationBacklogItem
-> run evaluation
-> generate pilot report
```

Student flow:

1. Log in as a student and open a visible terminology card.
2. Click feedback and choose `translation_error`, `evidence_error`, `concept_explanation_error`, `ocr_error`, `formula_ocr_error`, `ui_confusion`, or `other`.
3. Add severity and expected result. Feedback does not directly change an approved card.

Teacher flow:

1. Open Feedback Review.
2. Filter by status/type/severity.
3. Triage feedback to `triaged` or `in_review`.
4. Resolve with a required `resolution_note`, reject, convert to EvaluationItem, or convert to Backlog.
5. High-severity evidence/translation feedback can move the linked card back to `pending_quality_control`.

Admin flow:

1. Review all feedback and generated backlog items.
2. Generate a redacted pilot report.
3. Export a feedback summary without student email or personal document text.

Generate a pilot report:

```bash
python scripts/generate_pilot_report.py --course-id 1 --output docs/generated/pilot_report_course_1.md
```

Export feedback summary:

```bash
python scripts/export_feedback_summary.py --course-id 1 --output feedback_summary.csv
```

Pilot workflow docs:

- `docs/pilot-feedback-design.md`
- `docs/pilot-runbook.md`
- `docs/pilot-report-template.md`
- `docs/iteration-backlog-template.md`

## Known Limitations

- SQLite keyword/simple-similarity retrieval is suitable for local course demo only.
- PR-14 adds a pluggable retrieval layer: `lexical`, optional `vector`, `hybrid`, and `hybrid_rerank`.
- Local vector search uses `local_hash_embedding` and `local_json` only for demos/tests; it is not production semantic retrieval.
- Run a retrieval experiment before considering any non-lexical backend:

```bash
python scripts/build_vector_index.py --kb-version-id 18 --apply --embedding-provider local_hash_embedding --vector-index-backend local_json
python scripts/check_vector_index_health.py --kb-version-id 18 --vector-index-backend local_json
EMBEDDING_PROVIDER=local_hash_embedding VECTOR_INDEX_BACKEND=local_json ENABLE_RERANKER=true RERANKER_PROVIDER=local_heuristic \
  python scripts/run_retrieval_experiment.py --course-id 1 --kb-version-id 18
```

- OCR requires a local engine; no OCR text is fabricated when engines are unavailable.
- Mock/local AI fallback is for workflow demonstration only.
- Legacy `/api/alignment/run` remains an active compatibility surface after Task 9C.5L's consumer audit. No production frontend POST consumer remains, but compatibility tests, readiness probes, OpenAPI contract, unresolved target-environment state, and unknown external clients prevent removal or HTTP 410 in this candidate. Task 9C.5H removes it from the teacher document-alignment start, polling, item-loading, and reload-recovery paths; Task 9C.5N.1 isolates its worker; Task 9C.5N.2 makes all repository production creation paths freeze-controlled and rehearses isolated drain/shutdown. The release defaults remain Active, and external/live execution remains blocked.
- Task 9C.4V defines `FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`; Task 9C.4W adds its root/item models, Task 9C.4X adds admission/start, Task 9C.4Y characterizes processing, and Task 9C.4Z establishes local-pilot formal BackgroundJob CAS/lease ownership. Task 9C.5A adds governed chunk-scoped item bootstrap, Task 9C.5B adds lease-fenced per-item verification recovery, and Task 9C.5C adds sequential document processing and root finalization. Task 9C.5D adds strict formal payload handling, CAS-only dispatch, result-to-job mapping, retry-exhaustion root finalization, stale recovery, and the original local formal/non-formal queue rotation; Task 9C.5N.1 later isolates `alignment_run` behind an explicit worker mode. Task 9C.5E adds permission-safe read-only run/item queries. Task 9C.5F establishes authenticated formal start/run/items HTTP routes and OpenAPI. Task 9C.5F.1 freezes a server-owned local provider/model/prompt identity at Admission. Task 9C.5F.2 freezes new formal jobs at three counted processing-failure outcomes, allows two attempt-fenced requeues, and verifies HTTP Admission-to-recovery without changing historical jobs. Task 9C.5G v3 verifies real authenticated HTTP start, formal worker processing, polling, pagination, source-scoped concurrent replay, partial/all-blocked business outcomes, retry/crash/terminal recovery, and same-origin browser API access. Task 9C.5H connects the existing teacher page to that formal API with duplicate-start prevention and refresh recovery. Pre-outcome crash/reclaim generations are uncounted and have no separate V1 cap. Historical formal runs, a complete review workbench, supervised runtime, PostgreSQL proof, distributed-worker behavior, and real-provider operation remain absent. `PILOT_CREATE_ALL_ONLY`, provider at-least-once, external/live provider disablement, and production operations remain explicit conditions.
- No real payment, SMTP, cloud storage, vector database, ByrDocs connector, publisher connector, or crawler is included.
- Production deployment would require fixed `FRONTEND_ORIGIN`, HTTPS, real secret management, audited RBAC, background workers, durable storage, and PostgreSQL/vector retrieval.
