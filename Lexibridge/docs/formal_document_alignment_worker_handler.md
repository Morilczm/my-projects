# Formal Document Alignment Worker Handler

Status: `FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_ESTABLISHED`

Task: 9C.5D

Baseline: `0ad0636d1c9c833a58418009ad504a676ae22bcb`

Scope: local SQLite pilot worker integration. This is not a production daemon,
PostgreSQL proof, route, query API, frontend workflow, live-provider system, or
exactly-once execution guarantee.

## Boundary

```text
formal dispatcher
-> existing CAS claim/reclaim service
-> FormalJobExecutionLease
-> strict two-field payload validation
-> ProcessDocumentAlignmentWorkflowCommand
-> formal processing orchestrator
-> typed result mapping
-> fenced complete / requeue / fail
```

`backend/services/formal_background_job_dispatch.py` only claims one formal
job and invokes the handler. `document_alignment_worker_handler.py` handles one
already-claimed lease. It does not import Flask, routes, evidence, candidate,
card, provider, verification, or network clients. The explicit production
composition is in `document_alignment_processing_composition.py`.

## Payload And Command

The only accepted payload is:

```json
{
  "workflow_run_uid": "...",
  "workflow_version": "formal-document-alignment-v1"
}
```

Unknown fields, non-object JSON, missing identity, job/run mismatch, and
workflow-version mismatch fail the active BackgroundJob without invoking the
orchestrator. Raw payloads are never copied into the typed result or errors.

The handler builds only `ProcessDocumentAlignmentWorkflowCommand` with run UID,
job UID, worker ID, execution attempt, and a repr-hidden lease token. The token
is absent from the result, audit records, API state, and worker output.

## Result Mapping

| Orchestrator result | Root requirement | BackgroundJob action |
|---|---|---|
| `ready_for_review` | matching terminal root | `complete` |
| `completed_with_warnings` | matching terminal root | `complete` |
| `blocked` | matching terminal root | `complete` |
| `failed` | matching terminal root | `complete` |
| `already_terminal` | matching terminal root | `complete` |
| retryable interruption/persistence error | retry budget remains | `requeue` |
| retryable interruption/persistence error | retry budget exhausted | root failure finalizer, then job `fail` |
| stale attempt/expired lease | none | stop without finalization |
| invalid payload/version/job identity | no mismatched root mutation | job `fail` |

A root failed specifically with
`DOCUMENT_ALIGNMENT_WORKER_RETRY_EXHAUSTED` is recovered as a failed job after a
crash between root finalization and job failure. It is not converted to a
completed job by the generic `already_terminal` rule.

All complete/requeue/fail calls use the original attempt-fenced lease. A CAS
loss returns `ownership_lost` or `persistence_error`; the old attempt does not
retry finalization.

## Attempt Semantics

- `execution_attempt` increments once for every successful claim or stale
  reclaim.
- claim, reclaim, heartbeat, and complete do not increment `attempt_count`.
- successful requeue increments `attempt_count` exactly once.
- permanent fail increments `attempt_count` exactly once.
- a requeue that would exhaust the budget returns `retry_exhausted` without
  mutating the job; the handler first terminalizes the root, then fails the job.
- no retry creates another BackgroundJob.

This separates transport ownership generations from business failure budget.

## Root And Job Consistency

The worker completes a job only after reloading a matching terminal root. A
retry leaves the root queued, validating, or processing. Retry exhaustion
terminalizes the root before failing the job. Invalid payloads may fail a job
without touching a root because no safe root identity is available.

The orchestrator remains the owner of root/item/card/preflight/verification/
usage/audit persistence. The worker owns only BackgroundJob transport state and
the explicit root retry-exhaustion finalizer call. The finalizer recomputes item
counts, preserves completed items, writes one idempotent root failure audit,
and never mutates BackgroundJob.

## Crash Recovery

| Crash point | Recovery |
|---|---|
| after claim, before orchestrator | lease expires; new attempt reclaims and resumes |
| after partial items | persisted checkpoints remain; new attempt skips/reuses completed work |
| after terminal root, before job complete | new attempt gets `already_terminal` and completes job |
| after retry-exhausted root, before job fail | new attempt recognizes root error identity and fails job |
| after requeue | next dispatcher claim advances only `execution_attempt` |
| after terminal job | terminal immutability prevents reclaim |

## Retry Budget

Admission freezes formal V1 jobs with `max_attempts=3`: three counted
processing-failure outcomes and two possible requeues. `execution_attempt`
advances on claim and stale reclaim only. `attempt_count` advances once on a
successful requeue and once on permanent or retry-exhausted failure; claim,
heartbeat, stale reclaim, ownership loss, and completion do not consume it.

A worker crash or ownership loss before a typed processing outcome therefore
does not consume the failure budget. `execution_attempt` can exceed
`max_attempts`, and V1 has no separate persisted cap for repeated stale
reclaims. This contract protects ownership and counts confirmed processing
failures; it does not guarantee a maximum number of process invocations.

Only `retryable_interruption` and `persistence_error` orchestrator outcomes may
enter requeue mapping. The handler does not trust an isolated `retryable=True`
flag. Unknown outcomes are permanent fail-closed results: the handler finalizes
the Root before failing the BackgroundJob. On the third retryable failure it
uses the same Root-first ordering. Existing jobs keep their stored
`max_attempts`; no runtime or schema backfill changes historical behavior.

Provider work remains at-least-once. Only deterministic/mock/fake/replay/local
providers are allowed by the existing item adapter; external/live/custom paths
remain fail-closed. A crash after `provider_started` can replay deterministic
work under the same execution identity. Database uniqueness prevents a second
logical verification, usage row, or audit event, but this is not provider
exactly-once.

## Formal And Legacy Dispatch

The existing generic claim continues to exclude
`formal_document_alignment_workflow_v1`. The formal CAS claim selects only that
type. The local `scripts/run_worker.py` loop alternates which family gets first
chance each iteration and processes at most one job per iteration. Scheduler
preference is in-memory only; no schema was added.

Legacy job execution and retry behavior are unchanged. Formal execution never
uses the legacy alignment handler, urllib transport, AlignmentRun,
TerminologyCard, legacy UsageRecord, or AICallLog.

## Evidence

- handler/result/recovery/security tests use real application models where
  persistence matters;
- the end-to-end worker integration begins with the admission service, claims
  the generated formal job, processes two items, and verifies root/job counts;
- dispatcher concurrency uses file-backed SQLite, two independent
  sessions/connections, real conditional updates and rowcounts, and ten races;
- the established ownership suite adds twenty claim races plus stale-reclaim
  fencing;
- approved-card worker coverage compares every persisted card column and proves
  no preflight, verification, or usage is created;
- worker and orchestrator write-set checks keep legacy writes at zero.

## Limitations

- SQLite only; PostgreSQL claim, isolation, lock, and deadlock behavior are not
  verified.
- `create_all` plus additive upgrade remains the pilot migration mechanism.
- the worker loop is a local development/controlled-pilot process, not a
  supervised production runtime.
- no multi-host scheduler, lease heartbeat thread, metrics, alerting, or stale
  job operations dashboard exists.
- formal query services, HTTP/OpenAPI adapters, and authenticated browser API
  E2E exist, but a formal frontend caller does not.
- live/external providers remain disabled and real credentials are not read.

Next permitted task:

```text
Task 9C.5G v3 verifies the local authenticated HTTP-to-worker-to-polling path.
The next slice is Task 9C.5H: Formal Workflow Frontend Cutover and
Legacy-Independent Teacher Experience.
```
