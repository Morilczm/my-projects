# Legacy Alignment Retirement Inventory

## Audit Metadata

- Task: `9C.5M`
- Baseline: `4319d35751ba5468961081b17c0d7a49a5997762`
- Branch: `release/pilot-v1-candidate`
- Scope: retirement-boundary audit for `POST /api/alignment/run`
- Current state: `ACTIVE_COMPATIBILITY_SURFACE`
- Audit result: `LEGACY_ALIGNMENT_DEPRECATION_BOUNDARY_ESTABLISHED`

This task does not delete the route, return HTTP 410, change its response or
permissions, modify the worker, or change the formal workflow.

## Component Inventory

| Component | Location | Purpose | Current State |
|---|---|---|---|
| Legacy POST route | `backend/app.py:11048` (`run_alignment`) | Accept synchronous or asynchronous legacy alignment requests | active; can create new work |
| Legacy run detail | `backend/app.py:11234` (`alignment_run_detail`) | Read one legacy `AlignmentRun` | active compatibility read surface |
| Legacy run list | `backend/app.py:11253` (`alignment_runs`) | Read role-filtered legacy run history | active frontend compatibility read surface |
| Admin legacy run list | `backend/routes/admin_alignment_runs.py` | Read recent legacy runs for admins | active read-only admin surface |
| Provider classification | `backend/services/legacy_alignment_provider_classification.py` | Allow bounded local deterministic intent and reject external/live/custom intent | active containment boundary |
| Request/job classification adapters | `backend/app.py:7662`, `backend/app.py:7673` | Convert request or persisted job metadata into the pure classification input | active |
| Legacy provider metadata adapter | `backend/app.py:7691` | Build bounded local metadata after classification | active |
| Legacy alignment execution | `backend/app.py:6942` (`process_alignment_job`) | Execute one persisted legacy `alignment_run` job | active worker dependency |
| Legacy job dispatcher | `backend/app.py:7068` (`run_background_job`) | Dispatch `alignment_run`, ingestion, and evaluation jobs and persist completion/retry/failure | active |
| Legacy job claim | `backend/app.py:7153` (`claim_next_background_job`) | Claim queued/retrying non-formal jobs | active; no legacy stale-running reclaim |
| Local worker loop | `scripts/run_worker.py` | Alternate formal and legacy worker polling | active; still consumes legacy jobs |
| Manual retry/cancel APIs | `backend/app.py` (`retry_background_job`, `cancel_background_job`) | Requeue failed jobs or cancel non-terminal jobs | active; external-disabled retries remain blocked |
| Run model | `backend/app.py:1742` (`AlignmentRun`) | Store legacy run status, provider metadata, counters, and errors | active historical and execution model |
| Job models | `backend/app.py:2856`, `backend/app.py:2900` (`BackgroundJob`, `BackgroundJobEvent`) | Store transport state, attempts, locks, and lifecycle events | shared active infrastructure |
| Legacy card/output models | `TerminologyCard`, legacy `UsageRecord`, `AICallLog`, `SystemLog` in `backend/app.py` | Store legacy outputs, optional usage/call records, and errors | active legacy dependencies |
| Execution helpers | `generate_alignment_result`, `run_alignment_for_chunks`, `create_or_update_card_from_alignment`, `update_alignment_run_stats` in `backend/app.py` | Perform legacy evidence/card/statistics work | active and app-coupled |
| Formal frontend | `frontend/js/formal-workflow.js` | Start/poll/render the formal workflow | migrated; no legacy POST or fallback |
| Legacy history frontend | `frontend/index.html:2314` (`loadAlignmentRuns`) | Load `GET /api/alignment/runs` history | active; not a POST consumer |
| Route/worker compatibility tests | `tests/test_api_contract.py`, `tests/test_permissions.py`, `tests/test_worker.py`, `tests/test_legacy_alignment_run_characterization.py` | Freeze current route, permission, persistence, and worker behavior | active compatibility tests |
| Containment tests | `tests/test_legacy_alignment_external_execution_disabled.py`, `tests/test_legacy_alignment_worker_external_execution_disabled.py` | Prove external intent fails closed without transport or new business writes | active safety tests |
| Formal independence tests | `tests/test_document_alignment_processing_boundary.py`, `tests/test_formal_document_alignment_workflow_boundary.py`, `tests/test_formal_workflow_frontend_cutover_contract.py`, `tests/test_formal_workflow_frontend_e2e_runner.py` | Prove formal processing and UI do not use legacy execution | migrated guard tests |
| Legacy browser runner | `scripts/run_legacy_alignment_browser_e2e.py` | Prove local legacy POST/job completion and external-intent blocking | active compatibility Gate |
| Readiness probe | `scripts/pilot_readiness_check.py` | Check legacy containment, queued-job classification, and formal zero-legacy behavior | active release Gate |
| Formal browser runners | `scripts/run_formal_workflow_frontend_e2e.py`, `scripts/run_formal_workflow_frontend_resume_e2e.py` | Require zero legacy POST requests and no fallback | migrated guard Gate |
| OpenAPI operation | `docs/openapi.yaml:1062` | Advertise the legacy route as deprecated | active but migration text is stale |
| Boundary/ADR documents | `docs/legacy_alignment_run_boundary.md`, `docs/legacy_alignment_consumer_audit.md`, `docs/adr/ADR-legacy-alignment-run-deprecation.md` | Record compatibility, containment, and consumer decisions | active governance records |
| Runtime configuration | `JOB_TYPES`, `JOB_MAX_ATTEMPTS`, `JOB_WORKER_ID` in `backend/app.py` | Keep `alignment_run` dispatch enabled with the shared local retry budget | active; no disable flag or deprecation window |

## Consumer Classification

| Consumer | Classification | Evidence | Retirement Treatment |
|---|---|---|---|
| Formal teacher workflow | internal migrated consumer | Formal JS and browser artifacts use only `/api/document-alignment-runs*` | keep zero-legacy Gate |
| Legacy run-history page | internal read consumer | `GET /api/alignment/runs` in `frontend/index.html` | decide separately; POST retirement must not silently remove GET history |
| Legacy worker dispatcher | internal execution consumer | `run_worker.py` calls `run_worker_once`; dispatcher handles `alignment_run` | retain through queue drain |
| Compatibility and containment tests | internal test consumer | route/worker/browser/readiness test inventory | reclassify before 410; do not delete prematurely |
| Demo/export utilities | internal data consumer | `run_demo_flow.py`, `export_sqlite_data.py`, screenshot checklist | retain or migrate independently from the POST |
| OpenAPI and README audience | external-looking documentation surface | Route is documented and discoverable | publish an accurate migration notice before 410 |
| Repository configuration | internal configuration | `alignment_run` remains in `JOB_TYPES`; no route feature flag exists | requires explicit future cutover design |
| Clients outside this repository | unknown external consumer | No client registry, gateway/access log, or route telemetry is available | `UNKNOWN_EXTERNAL_LEGACY_CONSUMER`; investigate and monitor |

No known external executable consumer was found in the repository. That is not
equivalent to proving that external consumers do not exist.

## Job Lifecycle

### Creation

New legacy jobs can still be created. The default asynchronous branch of
`POST /api/alignment/run` creates and commits one queued `AlignmentRun`, one
`BackgroundJob(job_type="alignment_run")`, and a `created` job event.
Synchronous requests do not require a queued job but still execute legacy
alignment and can write legacy run/card/usage data.

### Claim And Execution

`claim_next_background_job()` selects the oldest highest-priority eligible
non-formal job in `queued` or `retrying`, changes it to `running`, increments
`attempt_count`, records its lock owner/time, and commits. Task 9C.5N.1 adds
filtered wrappers: default `run_worker.py` operation excludes legacy jobs,
while `--mode legacy-alignment` consumes only legacy jobs for controlled
compatibility or drain work.

`run_background_job()` dispatches `alignment_run` to
`process_alignment_job()`. Bounded local deterministic work can complete.
Persisted external/live/custom intent is quarantined as failed with
`LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` and cannot be manually retried.

### Retry And Terminal States

Retryable execution failures become `retrying` while `attempt_count` is below
`max_attempts`; the worker can claim them again. Non-retryable or exhausted
failures become `failed`. Users can manually requeue ordinary failed jobs, but
not external-disabled legacy jobs. Completion, failure, cancellation, and
retry all write `BackgroundJobEvent` records.

### Stale And Orphan Boundary

The legacy claim path has no compare-and-swap lease and no stale-running
reclaim. Although legacy jobs store `locked_by`, `locked_at`, heartbeat, and
lease columns shared with formal jobs, the legacy worker does not use the
formal lease service. A worker crash after claim can therefore leave a legacy
job in `running` indefinitely.

Job failure or cancellation does not consistently finalize the linked
`AlignmentRun`. A failed/canceled job can leave a run in `queued` or `running`.
`alignment_run_id` is nullable and is not enforced as a database foreign key,
so missing-run jobs and active runs without jobs must be checked operationally.

## Read-Only Workspace Snapshot

On 2026-07-22, a read-only SQLite query of the discovered repository-local
`backend/lexibridge.db` returned:

| Measure | Count |
|---|---:|
| Legacy `alignment_run` jobs, all statuses | 0 |
| Queued legacy jobs | 0 |
| Running legacy jobs | 0 |
| Retrying legacy jobs | 0 |
| Legacy jobs missing `AlignmentRun` | 0 |
| Active `AlignmentRun` rows missing a legacy job | 0 |
| Legacy `AlignmentRun` rows | 1 completed |

This is point-in-time evidence for one local file only. Runtime
`DATABASE_URL` may select another database, and tests/readiness use temporary
databases. These counts cannot authorize HTTP 410 for another environment.

## Required Answers

1. **Can new legacy jobs still be created?** Yes, through the default async
   legacy POST. Synchronous legacy execution is also still available.
2. **How do existing jobs complete?** The local worker claims queued/retrying
   jobs and dispatches them through `process_alignment_job`; safe local work
   completes, external intent fails closed, and retryable failures may requeue.
3. **Does the worker still consume them?** Only when an operator explicitly
   starts `run_worker.py --mode legacy-alignment`; default and Formal modes do
   not consume them.
4. **What is the deletion risk?** Removing the route alone stops new HTTP
   admission but does not drain queued work. Removing worker/dispatch/models
   can strand queued/retrying/running jobs, break job APIs/history, and leave
   linked legacy runs/cards inconsistent. Running jobs have no automatic stale
   recovery.

## Inventory Conclusion

The formal and legacy execution worlds are independent, but the legacy world
is still live. Retirement requires an external-consumer observation window,
environment-specific queue drain proof, running-job disposition, accurate
migration notice, and compatibility-test conversion before any 410 or code
removal.
