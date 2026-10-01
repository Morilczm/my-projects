# Legacy Alignment Runtime Inventory

## Audit Metadata

- Task: `9C.5N`
- Baseline: `d4ec0790c53f05f5f3d598908ac4da60f5c2ea80`
- Runtime-isolation amendment: Task `9C.5N.1`, baseline
  `e58982d216d9d2977abc5c91f35a2b1c7429ade8`
- Freeze-preparation amendment: Task `9C.5N.2`, baseline
  `9762b03197b0a919b72fd6ced913982d0da4a794`
- Branch: `release/pilot-v1-candidate`
- Runtime target: legacy `POST /api/alignment/run`
- Current state: `ACTIVE_COMPATIBILITY_SURFACE`
- Formal Workflow dependency: none

This inventory records the current runtime behavior. It does not disable the
route, change worker behavior, alter the response contract, or authorize HTTP
410.

## Runtime Topology

```text
POST /api/alignment/run
  |-- default async
  |     |-- AlignmentRun(status=queued)
  |     `-- BackgroundJob(job_type=alignment_run, status=queued)
  |            `-- legacy worker -> process_alignment_job()
  |                    `-- local deterministic cards and run updates
  `-- ?sync=true
        `-- direct legacy execution -> AlignmentRun + legacy cards

POST /api/documents/upload?sync=true
  `-- run_alignment_for_chunks() -> AlignmentRun + legacy cards

scripts/run_worker.py --mode standard
  |-- formal_document_alignment_workflow_v1
  `-- document_ingestion + evaluation_run

scripts/run_worker.py --mode legacy-alignment
  `-- alignment_run only
```

The default production frontend upload does not request `sync=true`, and the
formal teacher alignment module does not call the legacy POST. The supported
formal flow uses `POST /api/document-alignment-runs` and its run/items GET
operations.

## Execution Components

| Component | Location | Responsibility | Runtime State |
|---|---|---|---|
| Legacy admission | `backend/app.py:11048` (`run_alignment`) | Authenticate, authorize, classify provider intent, then execute synchronously or create queued work | active |
| Legacy run model | `backend/app.py:1742` (`AlignmentRun`) | Store legacy execution state and counters | active |
| Shared job model | `backend/app.py:2856` (`BackgroundJob`) | Store queued work, attempts, lock metadata, and formal lease columns | active |
| Job creation helper | `backend/app.py:6381` (`create_background_job`) | Create a queued job and `created` event | active internal helper |
| Legacy execution | `backend/app.py:6942` (`process_alignment_job`) | Execute a persisted local deterministic alignment job | active |
| Generic dispatcher | `backend/app.py:7068` (`run_background_job`) | Dispatch non-formal jobs and persist completed/retrying/failed state | active |
| Generic claim | `backend/app.py` (`claim_next_background_job`) | Select and claim queued/retrying non-formal jobs, with optional validated job-type filtering | active; non-CAS |
| Generic wrapper | `backend/app.py` (`claim_next_generic_background_job`) | Claim only document ingestion and evaluation jobs | active isolated family |
| Legacy wrapper | `backend/app.py` (`claim_next_legacy_alignment_job`) | Claim only `alignment_run` | active isolated family |
| Worker loop | `scripts/run_worker.py` | Dispatch `standard`, `formal`, `generic`, or explicit `legacy-alignment` modes | active; default excludes legacy |
| Cancel API | `backend/app.py:14990` | Mark a non-terminal job canceled | active shared API |
| Retry API | `backend/app.py:15012` | Requeue a failed job except quarantined external legacy work | active shared API |
| Legacy history reads | `backend/app.py:11234`, `backend/app.py:11253`, `backend/routes/admin_alignment_runs.py` | Preserve run detail/list/admin history | active read surfaces |

## Creation Entry Matrix

| Entry | Location | Can create new job | Current purpose | Classification | Action |
|---|---|---:|---|---|---|
| Legacy POST, default async | `backend/app.py` | yes when admission is enabled: creates one queued `alignment_run` job and one queued run | compatibility execution | required compatibility | keep during observation; disable reversibly before drain |
| Legacy POST, sync direct term | `backend/app.py:11175` branch | no job; creates a running/completed run and card writes | synchronous compatibility | required compatibility | keep during observation; include in POST traffic count |
| Legacy POST, sync document | `backend/app.py:11137` branch | no job; helper creates a run and cards | synchronous compatibility | required compatibility | keep during observation; include in POST traffic count |
| Sync document upload | `backend/app.py:10156`, call at `backend/app.py:10542` | no alignment job; helper creates a run and cards | legacy synchronous upload compatibility | unknown | investigate callers before any creation block |
| Document-type legacy worker execution | `backend/app.py` `process_alignment_job` | reuses the job-linked run while processing existing work | queued compatibility execution | required compatibility until drain | allow only in Active/Draining |
| Direct helper call | `backend/app.py:9571` (`run_alignment_for_chunks`) | no job; creates a run only in Active, or reuses a caller-supplied linked run during drain | shared legacy execution helper | required compatibility | do not expose as a new service; retire with callers |
| Demo flow | `scripts/run_demo_flow.py:188` and `:217` | creates terminal run and terminal job records | local demo material | test-only | remove or replace only after demo/read-history decision |
| Readiness containment probe | `scripts/pilot_readiness_check.py:615` and `:631` | creates and immediately processes an isolated test job | release safety proof | test-only | retain until 410 test conversion |
| Direct test setup | legacy worker, route, card, and admin tests | can create isolated records/jobs | characterization and safety coverage | test-only | reclassify at deprecation execution |
| Admin UI/API action | repository scan | no dedicated creation action found | none | obsolete | no action |
| External callers | outside repository | potentially yes through legacy POST | unknown | unknown | observe and identify owners |

`LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=false` now participates in one
creation boundary covering the Legacy POST, sync upload, direct helper, and
legacy job factory. The runtime state separately controls whether the dedicated
worker may drain existing work. This does not resolve queued/running work in
target environments or unknown external callers.

```text
LEGACY_ALIGNMENT_CREATION_FREEZE_BOUNDARY_COMPLETE
```

## Job State Transitions

| Source State | Trigger | Destination | Notes |
|---|---|---|---|
| none | default async POST | queued | creates `AlignmentRun`, `BackgroundJob`, and `created` event |
| queued/retrying | generic claim | running | increments `attempt_count`, writes `locked_by` and `locked_at` |
| running | successful dispatcher execution | completed | stores result and completed event |
| running | retryable failure below budget | retrying | immediately eligible for another generic claim |
| running | non-retryable or exhausted failure | failed | stores safe error and failed event |
| failed | manual retry API | queued | clears error/result terminal fields but does not reset attempt count |
| queued/running/retrying | cancel API | canceled | updates job only; linked `AlignmentRun` is not finalized |

`JOB_MAX_ATTEMPTS` defaults to 3. There is no persisted retry delay or
backoff. The generic claim can select a retrying job again on the next poll.

## AlignmentRun State Behavior

- Async admission creates the linked run as `queued`.
- Local execution changes the linked run to `running` and then `completed`.
- External intent is rejected before the run is changed to `running`, so a
  failed external job can leave its linked run `queued`.
- Exceptions after execution starts can leave the linked run `running` while
  the job becomes `retrying` or `failed`.
- Generic cancellation changes only the job and can leave the run queued or
  running.
- Document-type worker execution passes its linked `AlignmentRun` to
  `run_alignment_for_chunks()`. Drain execution no longer creates a second run,
  so queue/run counts have one stable identity for new drain operations.
- `BackgroundJob.alignment_run_id` is nullable and is not a database foreign
  key, so the database does not enforce job/run lifecycle integrity.

## Worker Lifecycle Risk Audit

| Question | Evidence-Based Answer |
|---|---|
| Is owner recorded after claim? | Yes. `locked_by` and `locked_at` are written and committed. |
| Is there a legacy heartbeat? | No. Shared `heartbeat_at` exists, but the legacy path never updates it. |
| Is there stale reclaim? | No. Legacy claim only selects queued/retrying jobs and never evaluates `lease_expires_at` or lock age. |
| Is there ownership fencing? | No. `execution_attempt` and `lease_token` are not assigned by legacy claim, and writes/terminal commits have no owner CAS check. |
| How is a running job recovered? | There is no automatic safe recovery path. The fenced operator tool may fail a stale job and linked run after the former owner is confirmed stopped; it never replays the job. |
| Is there orphan cleanup? | No automated job/run reconciliation or cleanup was found. |
| Is there a manual recovery procedure? | No approved procedure or operator script exists. Generic cancel can mark the job canceled but does not repair the linked run; retry accepts only failed jobs. |

Two generic workers can also select the same candidate before either commit;
the claim is not a compare-and-swap update. A concurrent cancel is not fenced
from an already running worker's later writes. These are containment risks,
not changes introduced by this audit.

```text
LEGACY_RUNNING_JOB_RECOVERY_GAP
```

## Retry, Cancel, And Terminal Behavior

- `JobExecutionError.retryable=true` and unexpected exceptions enter
  `retrying` while `attempt_count < max_attempts`; otherwise they fail.
- External/live/custom legacy intent fails non-retryably with
  `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED`.
- Manual retry is restricted to `failed` jobs. It is blocked for the external
  execution error but otherwise does not reset `attempt_count`.
- Cancel accepts queued, running, or retrying jobs and rejects completed,
  failed, or already canceled jobs.
- Job terminal states are completed, failed, and canceled. AlignmentRun
  terminal consistency is not guaranteed on failure or cancellation.

## Containment Conclusion

Formal execution is independent and remains the only production frontend
alignment path. Default worker operation no longer claims legacy jobs, and a
dedicated legacy mode is available for controlled drain. Legacy creation is
nevertheless still available through more than one compatibility path, and
the explicit legacy worker still lacks strong ownership. Runtime retirement
therefore requires observed zero callers, environment-authoritative queue
drain, rehearsed running-job disposition, shutdown evidence, and rollback
ownership.

```text
LEGACY_ALIGNMENT_RUNTIME_ISOLATED
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
