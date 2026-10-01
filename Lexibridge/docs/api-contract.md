# API Contract

LexiBridge AI exposes a Flask JSON API for the Local MVP. The machine-readable contract is:

```text
docs/openapi.yaml
```

The contract uses OpenAPI `3.0.3` and covers the core Auth, Course, Document, Knowledge, Alignment, Background Jobs, Terminology, Quality Control, Pilot Feedback, Iteration Backlog, Pilot Report, Evaluation, and Admin endpoints.

## Response Envelope

Successful JSON responses should follow this shape:

```json
{
  "status": "success",
  "message": "Operation completed.",
  "data": {}
}
```

Some legacy-compatible endpoints still include top-level fields such as `cards`, `users`, or `documents`; new code should also provide `data` where practical.

Error responses use:

```json
{
  "status": "error",
  "error_code": "PERMISSION_DENIED",
  "message": "You do not have permission to access this resource.",
  "details": {}
}
```

Paginated responses use:

```json
{
  "status": "success",
  "data": {
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 0,
      "has_next": false
    }
  }
}
```

## Error Codes

The OpenAPI error enum is intentionally synchronized with `backend/app.py::ERROR_CODES`.

| Error code | HTTP | Meaning |
| --- | ---: | --- |
| `AUTH_REQUIRED` | 401 | Missing or invalid bearer token |
| `TOKEN_EXPIRED` | 401 | Token expired and was revoked |
| `PERMISSION_DENIED` | 403 | Authenticated user lacks role/scope permission |
| `RESOURCE_NOT_FOUND` | 404 | Resource does not exist or cannot be viewed |
| `VALIDATION_ERROR` | 400 | Missing or invalid request data |
| `FILE_TOO_LARGE` | 413 | Upload exceeds `MAX_UPLOAD_SIZE_MB` |
| `UNSUPPORTED_FILE_TYPE` | 415 | Extension or file signature is not allowed |
| `OCR_UNAVAILABLE` | 422 | OCR is required but no usable engine/result exists |
| `FORMULA_OCR_UNAVAILABLE` | 422 | Formula OCR is required but unavailable |
| `PARSING_FAILED` | 422 | Document parser failed without creating valid chunks |
| `QUOTA_EXCEEDED` | 402 | Subscription quota is exhausted |
| `AI_PROVIDER_FAILED` | 502 | Live AI provider failed |
| `PDF_FONT_UNAVAILABLE` | 422 | PDF export cannot render configured fonts |
| `TOO_MANY_REQUESTS` | 429 | Future rate-limit hook |
| `INTERNAL_ERROR` | 500 | Unexpected backend error |

## Core Contract Coverage

`docs/openapi.yaml` covers:

- Auth: register, login, logout, current user, mock email verification, password reset request/confirm.
- Courses: list/create, mine, join.
- Documents: upload, list, chunks.
- Knowledge: evidence search, knowledge sources, knowledge base versions.
- Alignment: run and run history.
- Background Jobs: list, detail, events, cancel, retry.
- Terminology: card list/detail, favorite, mastered, feedback, PDF export.
- Quality Control: queue, approve, reject, edit, needs-more-evidence.
- Subscription: public plans, current subscription/quota, local mock payment.
- Feedback: submit visible-card feedback, list/detail, triage, resolve, reject, convert to EvaluationItem, convert to Backlog.
- Iteration Backlog: list/detail/update status for pilot-derived P0/P1/P2/P3 work items.
- Pilot Report: redacted course/global pilot report markdown for teacher/admin review.
- Evaluation: sets, item import/list, run, run detail.
- Admin: users, role update, usage, billing, logs, ingestion jobs.

## Pilot Feedback Contract

Student feedback never edits a terminology card directly. A student may submit feedback only for a visible `TerminologyCard`.

Core fields:

```text
feedback_type, feedback_source, severity, status, priority,
terminology_card_id, english_term, chinese_term,
reported_issue, expected_result, actual_result, evidence_comment,
classification, root_cause, resolution_action, resolution_note
```

Teacher/admin actions:

- `POST /api/feedback/{feedback_id}/triage`
- `POST /api/feedback/{feedback_id}/resolve`
- `POST /api/feedback/{feedback_id}/reject`
- `POST /api/feedback/{feedback_id}/convert-to-evaluation`
- `POST /api/feedback/{feedback_id}/convert-to-backlog`

High-severity `translation_error` or `evidence_error` feedback can move the linked card back to `pending_quality_control`; it does not make the card `approved`.

## Iteration Backlog And Pilot Report

`POST /api/feedback/{feedback_id}/convert-to-backlog` creates an `IterationBacklogItem` with a rule-based category and P0/P1/P2/P3 priority. Duplicate conversion returns the existing item.

`GET /api/pilot/report` returns Markdown and is redacted by design: it uses anonymized student identifiers and aggregated counts, not full student email addresses, tokens, API keys, or personal document content.

The PR-7 frontend contract test also verifies that the paths called by `frontend/index.html` are present in `docs/openapi.yaml`.

## File Upload Contract

`POST /api/documents/upload` is documented as `multipart/form-data`. It accepts only:

```text
pdf, docx, pptx, txt, md, png, jpg, jpeg
```

The API rejects executable/script/macro/archive-like extensions, rejects extension/signature mismatches, randomizes saved filenames, and does not create terminology cards when parsing fails.

By default, upload is asynchronous and returns `document_id` plus `job_id`. Use `?sync=true` only for local compatibility tests.

PR-11 routes new document uploads through `StorageService`. `Document` responses may include:

```text
storage_object_id
storage_backend
storage_key
original_filename
content_type
size_bytes
sha256
```

The API must not expose a server absolute path. Legacy `saved_filename` remains for local compatibility and migration only.

## Background Job Contract

The long-running endpoints return queued job IDs by default:

- `POST /api/documents/upload`
- `POST /api/alignment/run`
- `POST /api/evaluation/run`

Job status APIs:

- `GET /api/jobs`
- `GET /api/jobs/<id>`
- `GET /api/jobs/<id>/events`
- `POST /api/jobs/<id>/cancel`
- `POST /api/jobs/<id>/retry`

Statuses are:

```text
queued, running, completed, failed, canceled, retrying
```

Students can only see their own jobs. Teachers can see their own jobs and jobs attached to courses they manage. Admins can see all jobs.

## AI Governance Contract

PR-12 adds admin-only AI governance APIs:

- `GET /api/admin/ai/providers`
- `GET /api/admin/ai/models`
- `GET /api/admin/ai/prompts`
- `POST /api/admin/ai/prompts`
- `GET /api/admin/ai/calls`
- `GET /api/admin/ai/usage`
- `GET /api/admin/ai/health`
- `POST /api/admin/ai/healthcheck`

These endpoints expose provider mode, model metadata, active prompt versions, redacted call logs, usage estimates, and health status. They never return API keys. `AICallLog` stores request/response hashes and redacted previews rather than full prompts or full model responses in normal configuration.

AI errors use the standard JSON envelope. Additional error codes:

```text
AI_PROVIDER_NOT_CONFIGURED
AI_INVALID_RESPONSE
```

Mock and local heuristic providers are explicitly marked by `provider_mode` and cannot produce `auto_approved` terminology cards.

## Knowledge Base Versioning Contract

PR-13 adds governed KB lifecycle APIs:

- `GET /api/knowledge/versions`
- `POST /api/knowledge/versions`
- `GET /api/knowledge/versions/{version_id}`
- `POST /api/knowledge/versions/{version_id}/publish`
- `POST /api/knowledge/versions/{version_id}/rollback`
- `POST /api/knowledge/versions/{version_id}/rebuild`
- `GET /api/knowledge/versions/{version_id}/manifest`
- `GET /api/knowledge/health`
- `POST /api/knowledge/retrieval-regression`

Course KB publish, rebuild, and rollback are teacher/admin scoped. Student personal versions remain owner-scoped. Default retrieval uses the published KB version when present; legacy unversioned chunks remain readable for Local MVP compatibility.

## RAG Retrieval Enhancement Contract

PR-14 extends `GET /api/knowledge/search` with:

```text
retrieval_backend=lexical|vector|hybrid|hybrid_rerank
kb_version_id=<id>
include_score_breakdown=true|false
include_debug=true|false
```

Students cannot request `include_debug=true`. Every backend must preserve language, course, scope, owner, KB type, KB version, source status, authorization, duplicate, and active-index hard filters.

Admin/teacher retrieval diagnostics:

- `POST /api/admin/retrieval/vector-index/build`
- `POST /api/admin/retrieval/experiments/run`
- `GET /api/admin/retrieval/experiments`
- `GET /api/admin/retrieval/experiments/{id}`
- `GET /api/admin/retrieval/health`

Teachers are limited to their own courses. Admins can run all diagnostics. API responses never expose embedding API keys or server-local index internals beyond controlled health metadata.

## Download Contract

`GET /api/terminology/cards/export` returns `application/pdf` on success. Error responses remain JSON and use the standard error envelope.

## Contract Tests

Run:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_api_contract.py
backend/.venv-macos/bin/python -m pytest tests/test_frontend_contract.py
```

The test parses `docs/openapi.yaml`, verifies core paths and methods, checks upload/export schemas, and ensures the documented error codes match `backend/app.py`.

`tests/test_frontend_contract.py` additionally extracts the inline JavaScript, runs `node --check`, checks role navigation boundaries, checks user-facing error-code mappings, and verifies frontend API paths are documented.
