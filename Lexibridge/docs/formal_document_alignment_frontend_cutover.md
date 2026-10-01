# Formal Document Alignment Frontend Cutover

Status: `FORMAL_WORKFLOW_FRONTEND_CUTOVER_ESTABLISHED`

Scope: Task 9C.5H replaces the teacher document-alignment start path with the
formal workflow API. It is a minimal functional cutover in the existing
single-page HTML/JavaScript frontend. It does not provide a historical run
center, a complete review workbench, a visual redesign, PostgreSQL proof, or a
production worker runtime.

## Teacher Entry And Source Identity

The teacher continues to upload course material through the existing governed
document-ingestion path. The initial upload response identifies the document;
after ingestion, `GET /api/knowledge/sources` provides the server-issued
`source_uid` and its `document_id`. The frontend refreshes that collection and
maps the selected visible document to its governed source.

The frontend never derives a source UID from a filename, parse UID, DOM text,
timestamp, or random browser value. If no governed source is available, start
fails locally and no formal or legacy alignment request is sent.

## Formal API Client

`frontend/js/formal-workflow.js` owns the route-neutral client and controller:

```text
POST /api/document-alignment-runs
GET  /api/document-alignment-runs/{run_uid}
GET  /api/document-alignment-runs/{run_uid}/items?page=N&page_size=20
```

The start request sends only `source_uid` and a cryptographically generated
`Idempotency-Key`. It accepts the formal `202`, `Location`, `Retry-After`, and
safe JSON envelope. There is no fallback to `POST /api/alignment/run`.

## Idempotency And Active State

A new explicit start intent gets a key in the form
`ui-formal-alignment-v1-<uuid>`. The controller uses `crypto.randomUUID()` or
`crypto.getRandomValues()`; it does not use `Math.random()`, a filename,
request ID, or source UID as the key.

The pending state is persisted before POST. An ambiguous network failure keeps
the same key, and manual resubmission reuses it. Concurrent clicks share one
in-flight start promise. Starting another source cancels prior polling before a
new active state is installed.

The versioned session key is:

```text
lexibridge.formalAlignment.activeRun.v1
```

Only these fields survive schema validation:

- `source_uid`
- `idempotency_key`
- `run_uid`
- `location`
- `items_url`
- `started_at`
- `last_status`
- `poll_interval_seconds`
- `page`
- `page_size`

Tokens, cookies, evidence, provider data, prompts, job ownership, raw errors,
and complete responses are not persisted. Logout and formal `401`, `403`, or
`404` responses clear active state.

## Polling And Reload Recovery

Polling uses the server `Location`, with `Retry-After` clamped to 1 through 10
seconds and a default of 2 seconds. One GET may be active at a time. New work,
page unload, terminal status, authorization loss, and explicit cancellation
abort the controller. A bounded total timeout and a three-network-error limit
prevent infinite polling.

Terminal statuses are `ready_for_review`, `completed_with_warnings`, `blocked`,
and `failed`. Fast completion before the first GET is valid. Network failure is
rendered as a connection interruption and does not overwrite the last business
status with `failed`.

On authenticated page initialization, a stored Run is queried before polling
resumes. A stored pending key without a Run is never automatically submitted;
the teacher must choose the resume action, which reuses the original key.
Reload recovery therefore cannot create a second Run by itself.

## Minimal View

The existing teacher course-upload workspace now includes a small unframed
formal status area. It renders business status, stage, API progress, item
counts, warnings, safe errors, and the paginated item summaries approved by the
formal query DTO. It distinguishes processing, ready for review, completed
with warnings, business blocked, business failed, and connection interrupted.

Items are fetched one API page at a time with `page_size=20`. Previous and next
controls are disabled at their boundaries, failed page requests retain the
current page, and session state remembers the current page. API strings are
escaped before insertion; no formal API value is assigned directly to
`innerHTML`.

The backend remains the permission boundary. The start control is exposed only
through the existing teacher/admin workspace context, and the formal API still
rejects students and unauthorized actors.

## Legacy Independence

The teacher start, polling, item loading, and reload-recovery paths contain no
request to `POST /api/alignment/run` and do not fall back to it after errors.
The backend legacy endpoint and legacy run-list compatibility UI remain in the
repository for the next consumer audit; they are not deleted or changed to
`410` in this task.

## Browser Evidence

The required browser gates are:

- `scripts/run_formal_workflow_frontend_e2e.py`
- `scripts/run_formal_workflow_frontend_resume_e2e.py`

The first uses real controls to start successful, partial-warning, and
all-blocked workflows, runs the formal worker, observes UI polling and API
pagination, and checks duplicate-click protection. The second starts through
the UI, reloads before worker execution, confirms no second POST and the same
Run UID, then observes terminal state and items after the formal worker runs.

Expected artifacts:

- `/private/tmp/lexibridge-9c5h-formal-ui-e2e.json`
- `/private/tmp/lexibridge-9c5h-resume-e2e.json`
- `/private/tmp/lexibridge-9c5h-readiness.json`

An implementation is not considered verified merely because the scripts
exist. Both UI artifacts must report PASS with zero console errors, page
errors, external dependency requests, legacy alignment requests, duplicate
formal POSTs, and timeouts.

## Remaining Limits

- The legacy endpoint remains registered pending consumer audit and retirement.
- The old run-list compatibility view remains; no formal historical list API exists.
- Item summaries are not a complete review workbench or card-detail experience.
- The UI is a minimal cutover, not a visual redesign.
- SQLite, local Flask, and local worker evidence do not establish PostgreSQL,
  distributed worker, supervised deployment, or live-provider behavior.
