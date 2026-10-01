# LexiBridge AI Job Queue Design

## Scope

This Local MVP uses a SQLite-backed background job queue for long-running workflows:

- `document_ingestion`: parse uploaded files, run OCR/formula detection when configured, create `DocumentChunk`, `FormulaBlock`, `KnowledgeChunk`, and KB version records.
- `alignment_run`: execute terminology extraction and bilingual evidence alignment for a document or a direct term.
- `evaluation_run`: run the evaluation harness and persist metrics/report output.

The queue is intentionally local and single-worker. It is not a production distributed queue.

## Data Model

### BackgroundJob

`BackgroundJob` stores one unit of asynchronous work:

- `job_type`: `document_ingestion`, `alignment_run`, or `evaluation_run`
- `status`: `queued`, `running`, `completed`, `failed`, `canceled`, `retrying`
- `created_by`, `course_id`, `document_id`, `alignment_run_id`, `evaluation_run_id`
- `scope_type`, `owner_user_id`
- `input_json`, `result_json`
- `progress_current`, `progress_total`, `progress_message`
- `error_code`, `error_message`
- `attempt_count`, `max_attempts`
- timestamps and lock fields: `started_at`, `finished_at`, `canceled_at`, `locked_by`, `locked_at`

### BackgroundJobEvent

`BackgroundJobEvent` stores an append-only event trail:

- `created`
- `claimed`
- `started`
- `progress`
- `completed`
- `failed`
- `retrying`
- `canceled`
- `retry_queued`

Events are used by the API and UI to explain what happened without exposing raw traceback or secrets.

## Default Async Behavior

The following endpoints now default to async behavior:

- `POST /api/documents/upload`
- `POST /api/alignment/run`
- `POST /api/evaluation/run`

Each endpoint creates the domain record first (`Document`, `AlignmentRun`, or `EvaluationRun`), then creates a `BackgroundJob`, and returns the IDs immediately.

For compatibility and tests, append `?sync=true` to keep the older synchronous behavior.

## Worker

Run the default local worker for Formal Workflow plus generic document
ingestion and evaluation jobs:

```bash
python scripts/run_worker.py
```

For a one-shot worker pass:

```bash
python scripts/run_worker.py --once
```

The default worker does not claim `alignment_run`. Compatibility jobs require
an explicitly isolated worker:

```bash
python scripts/run_worker.py --mode legacy-alignment
```

Use `--mode formal` or `--mode generic` to run only that queue family.
`JOB_WORKER_QUEUE_MODE` sets the default mode. Each worker claims eligible
`queued` or `retrying` jobs by priority and ID order, executes the matching
handler, writes progress events, and records the final result.

Legacy retirement operations use `LEGACY_ALIGNMENT_RUNTIME_STATE`:

- `active`: admission and dedicated Legacy claim are available;
- `freeze`: admission and Legacy claim are blocked;
- `draining`: admission stays blocked while the dedicated Legacy worker may
  finish existing queued/retrying jobs;
- `disabled`: admission and Legacy claim are blocked after drain.

Run `python scripts/legacy_alignment_runtime.py status` for a read-only
queued/running/retrying/failed snapshot. Safe failure is a separate fenced,
audited operator action and never retries, migrates, or deletes a job.

## Retry And Cancel

- Unexpected retryable failures move to `retrying` until `attempt_count >= max_attempts`.
- Non-retryable validation/OCR/quota/resource errors move directly to `failed`.
- A queued or running job can be canceled through `POST /api/jobs/<id>/cancel`.
- A failed job can be manually requeued through `POST /api/jobs/<id>/retry`.

Cancellation is cooperative in the Local MVP. If a job is already inside a CPU-bound parser call, the status is recorded as canceled but the parser cannot be interrupted mid-call.

## Permissions

- Student: can view/cancel/retry only jobs they created or jobs where `owner_user_id` is their user ID.
- Teacher: can view/cancel/retry jobs they created or jobs for courses they manage.
- Admin: can view/cancel/retry all jobs.

Personal workspace jobs keep `scope_type=personal` and `owner_user_id` to preserve private KB boundaries.

## API

Job APIs:

- `GET /api/jobs`
- `GET /api/jobs/<job_id>`
- `GET /api/jobs/<job_id>/events`
- `POST /api/jobs/<job_id>/cancel`
- `POST /api/jobs/<job_id>/retry`

All job APIs use the standard response envelope and existing error codes (`AUTH_REQUIRED`, `PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`, `VALIDATION_ERROR`).

## Current Limits

- SQLite polling queue only.
- Single local worker, no distributed locks.
- No Celery/RQ/Redis dependency.
- No hard cancellation of in-progress OCR or PDF parsing.
- Production should replace this with a real queue, durable object storage, and idempotent handler design.
