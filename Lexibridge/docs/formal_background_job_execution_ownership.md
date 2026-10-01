# Formal BackgroundJob Execution Ownership

Status: `FORMAL_BACKGROUND_JOB_EXECUTION_OWNERSHIP_ESTABLISHED_FOR_LOCAL_PILOT`

Task: 9C.4Z

Baseline: `7eb8c1440ca192383ff817c4d3c55c7240ebd173`

Primary conclusion: `FORMAL_BACKGROUND_JOB_EXECUTION_OWNERSHIP_ESTABLISHED_FOR_LOCAL_PILOT`

The formal queue contract is:

```text
AT_LEAST_ONCE_TRANSPORT
+
ATTEMPT_FENCED_OWNERSHIP
```

It is not an exactly-once execution guarantee. It does not register the formal
worker handler, process document-alignment items, prevent every duplicate
external side effect, or validate PostgreSQL behavior.

## Scope

`backend/services/formal_background_job_execution.py` owns short transactions
for formal job claim/reclaim, heartbeat, completion, permanent failure, and
retry requeue. It accepts only
`formal_document_alignment_workflow_v1`. The legacy generic worker explicitly
excludes that job type and direct legacy dispatch leaves a formal job unchanged.

The service never reads workflow content, credentials, provider configuration,
evidence, prompts, cards, verification runs, Flask request state, or frontend
state. `BackgroundJob` remains transport state; `DocumentAlignmentWorkflowRun`
and `DocumentAlignmentWorkflowItem` remain business state.

## BackgroundJob Schema

Existing fields retained:

| Meaning | Field |
|---|---|
| database identity | `id` |
| type and transport state | `job_type`, `status` |
| ordering | `priority`, `id` |
| retry budget | `attempt_count`, `max_attempts` |
| worker owner | `locked_by` |
| claim time | `locked_at` |
| safe failure | `error_code`, `error_message` |
| lifecycle | `started_at`, `finished_at`, `updated_at` |

Additive fields:

| Meaning | Field |
|---|---|
| stable transport UID | `job_uid` |
| ownership generation | `execution_attempt` |
| opaque owner capability | `lease_token` |
| latest renewal | `heartbeat_at` |
| ownership deadline | `lease_expires_at` |

`job_uid` is generated for new ORM rows. A pre-upgrade formal row with no UID
receives one in the successful claim CAS. Existing legacy rows may safely keep
`NULL` UIDs until touched by a future dedicated migration; they are not claimed
by the formal service.

Indexes:

- unique `ix_background_job_job_uid`;
- `ix_background_job_formal_claim` on job type, status, priority, and ID;
- `ix_background_job_formal_stale_lease` on job type, status, and expiry.

The upgrade is additive SQLite DDL only. `PILOT_CREATE_ALL_ONLY` and
`FORMAL_MIGRATION_REQUIRED_BEFORE_PRODUCTION` remain in force.

## DTOs

`FormalJobExecutionLease` is frozen and carries only `job_uid`, `job_type`,
`worker_id`, `execution_attempt`, the opaque `lease_token`, claim/heartbeat/
expiry times, and status.

`ClaimFormalJobResult` returns `claimed`, `no_job_available`, `claim_conflict`,
or `persistence_error`.

`FormalJobLeaseOperationResult` returns `accepted`, `lease_not_owned`,
`lease_expired`, `stale_attempt`, `terminal_immutable`, `invalid_state`, or
`persistence_error`. Results contain no ORM object, integer database ID, raw
payload, raw exception, traceback, HTTP status, or secret.

## Lease And Clock Policy

```text
FORMAL_JOB_DEFAULT_LEASE_SECONDS = 30
```

The current legacy worker polls every two seconds. A 30-second lease gives a
single-node local worker multiple heartbeat opportunities without making crash
recovery unbounded. A lease is expired when:

```text
lease_expires_at <= now
```

All service time comes from an injected UTC clock; tests use no sleep.

Current clock policy:

- `SINGLE_NODE_CLOCK_TRUSTED_FOR_PILOT`;
- `DATABASE_TIME_REQUIRED_FOR_DISTRIBUTED_PRODUCTION`;
- `POSTGRESQL_LEASE_SEMANTICS_NOT_VERIFIED`.

## Atomic Claim CAS

Candidate discovery may read a bounded, stable list ordered by priority and ID.
Ownership is obtained only by a SQL `UPDATE` whose `rowcount == 1`.

Queued/retrying claim conditions include:

```text
job id matches
job_type == formal_document_alignment_workflow_v1
status == selected queued/retrying state
execution_attempt == observed attempt
lease_token is empty
```

Stale-running reclaim additionally compares the observed attempt and token and
requires `lease_expires_at <= now`. A successful claim or reclaim:

- increments `execution_attempt` exactly once;
- does not increment `attempt_count`;
- creates a new unpredictable lease token;
- replaces worker ownership;
- updates claim, heartbeat, and expiry times;
- commits once.

A zero rowcount never grants ownership. The transaction is rolled back and the
caller receives a conflict/no-job result. Candidate scanning is capped at 20.

## Heartbeat And Active Guard

Heartbeat is a fenced conditional update over all of:

```text
job_uid
formal job type
status == running
worker_id
execution_attempt
lease_token
lease_expires_at > now
```

It extends expiry by 30 seconds without changing attempt or token. It never
reclaims an expired lease.

`validate_active_formal_job_lease` exposes the same ownership predicate for the
future processing layer. Future persistence writes must both validate the
active lease and carry an equivalent fence in their write transaction; a
one-time worker-start check is insufficient.

## Crash And Reclaim Sequence

```text
Worker A claims attempt 1/token A
-> A stops heartbeating
-> token A expires
-> Worker B CAS-reclaims attempt 2/token B
-> A resumes
-> A heartbeat/complete/fail/requeue all reject as stale_attempt
-> only B may modify transport state
```

Worker ID alone never proves ownership, so process restart with a reused worker
name cannot revive an old attempt.

## Fenced Finalization And Retry

Completion, permanent failure, and requeue all require the active lease
predicate. Completion writes `completed` without consuming business retry
budget. Permanent failure writes `failed` and increments `attempt_count` once.
A successful requeue writes `retrying` and increments `attempt_count` once.
When the next requeue would exhaust the budget, the ownership service returns
`retry_exhausted` without mutating the job so the worker can first terminalize
the workflow root. Requeue does not create a second job or change the payload.

Active token and worker fields are cleared on requeue/terminal transition;
`execution_attempt` remains as the monotonic fence. Existing terminal statuses
`completed`, `failed`, and `canceled` are immutable and cannot be claimed,
reclaimed, heartbeated, requeued, or finalized again.

`CANCELLATION_OUT_OF_SCOPE_FOR_9C4Z`: this slice adds no formal cancellation or
terminal-reopen API.

## Transaction Ownership

Each operation owns one short transaction:

| Operation | Commit | Rollback |
|---|---:|---:|
| claim/reclaim winner | once | on execution/commit failure |
| claim loser | zero | clears failed CAS/read transaction |
| heartbeat winner | once | on CAS loss or persistence failure |
| complete/fail/requeue winner | once | on CAS loss or persistence failure |

No lease spans a database transaction. No operation calls processing or the
network. Persistence errors return stable safe results and leave the session
usable.

## Formal And Legacy Isolation

The formal service filters exclusively by the formal job type. The legacy
query-first worker excludes that type. The formal type remains absent from the
legacy dispatcher, and direct legacy dispatch returns it untouched. Legacy job
ordering, retry, and execution behavior otherwise remain unchanged.

Task 9C.5D adds a separate formal dispatcher and handler while preserving this
isolation. The generic legacy dispatcher still never claims formal jobs, and
the formal CAS dispatcher never claims legacy jobs.

## Concurrency Evidence

`tests/test_formal_background_job_concurrency.py` uses a file-backed SQLite
database, separate SQLAlchemy sessions/connections, distinct workers, a thread
barrier after candidate discovery, real commits, and real rowcounts. The queued
claim race is repeated 20 times and produces exactly one winner per row. A
separate stale reclaim race produces one new attempt; the old owner cannot
finalize. Expiry and terminal boundaries leave no locked database residue.

This proves the local SQLite CAS path tested here. It does not prove distributed
fairness, exactly-once execution, PostgreSQL locking, network partition safety,
or clock-skew safety.

## Safe Errors

Stable ownership errors include:

- `FORMAL_JOB_WORKER_CLAIM_CONFLICT`;
- `FORMAL_JOB_STALE_EXECUTION_ATTEMPT`;
- `FORMAL_JOB_LEASE_NOT_OWNED`;
- `FORMAL_JOB_LEASE_EXPIRED`;
- `FORMAL_JOB_TERMINAL_IMMUTABLE`;
- `FORMAL_JOB_INVALID_STATE`;
- `FORMAL_JOB_EXECUTION_OWNERSHIP_PERSISTENCE_FAILED`.

Messages are bounded and reject known secret-bearing forms. Lease tokens are
internal worker capabilities: they are not logged, audited, exposed by an API,
or sent to the frontend.

## Guarantees And Non-Guarantees

Established for the local pilot:

- database-CAS ownership for formal jobs;
- one active attempt under the tested SQLite race;
- heartbeat and finite expiry;
- stale-running recovery;
- old-attempt fencing for all ownership mutations;
- terminal immutability;
- formal/legacy worker isolation.

Not established:

- a formal worker handler;
- document processing or WorkflowItem creation;
- exactly-once model calls or business writes;
- provider-call, UsageRecord, or AuditRecord idempotency;
- distributed leases or database-time clocking;
- PostgreSQL behavior;
- a formal migration framework.

## Next Gate

The two remaining Task 9C.4Y blockers were reassessed. Transaction-neutral
draft/verification composition remains necessary, but the existing term
extractor still accepts whole text and emits no governed chunk scope. Therefore
stable item bootstrap cannot yet be built.

Task 9C.5A satisfies the former blocker with:

```text
FORMAL_CHUNK_SCOPED_ITEM_BOOTSTRAP_ESTABLISHED
```

## Transaction-Neutral Business Write Fence

Task 9C.5A adds `fence_active_formal_job_lease_in_transaction`. It performs a
conditional UPDATE and requires one affected row while checking job UID,
formal job type, running status, worker ID, execution attempt, opaque lease
token, and `lease_expires_at > now`. It may extend heartbeat and expiry but does
not commit or roll back; the caller owns the transaction.

`document_alignment_item_bootstrap.py` uses this primitive in the same
SQLAlchemy session and transaction as WorkflowItem creation/reuse and
WorkflowRun status/count updates. A failed fence causes zero business writes;
commit failure rolls back the fence update and business changes. Lease tokens
are excluded from DTO repr.

This closes the SELECT-guard TOCTOU gap only for the tested local SQLite
bootstrap transaction. It does not fence provider calls outside a transaction,
provide provider exactly-once behavior, or prove PostgreSQL semantics. The next
task is `NEXT_FORMAL_VERIFICATION_TRANSACTION_ADAPTER`; it must not register the
worker, routes, or frontend.
