# ADR: Formal Document Alignment Workflow Contract

Status: ACCEPTED_FOR_SMALL_PILOT

Date: 2026-07-18

Workflow name: FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION

Initial implementation conclusion: FORMAL_WORKFLOW_MODELS_REQUIRED_FIRST

Current implementation conclusion:
FORMAL_WORKFLOW_FRONTEND_CUTOVER_ESTABLISHED

Implementation status after Task 9C.5L:

- `FORMAL_WORKFLOW_MODELS_ESTABLISHED`
- `WORKFLOW_ADMISSION_SERVICE_ESTABLISHED`
- `PROCESSING_BOUNDARY_CHARACTERIZED`
- `FORMAL_JOB_EXECUTION_OWNERSHIP_ESTABLISHED_FOR_LOCAL_PILOT`
- `FORMAL_CHUNK_SCOPED_TERM_BOOTSTRAP_ESTABLISHED`
- `FORMAL_ITEM_EXECUTION_IDEMPOTENCY_SCHEMA_ESTABLISHED`
- `FORMAL_ITEM_VERIFICATION_TRANSACTION_ADAPTER_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_PROCESSING_ORCHESTRATOR_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_ESTABLISHED`
- `FORMAL_WORKFLOW_QUERY_SERVICES_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_ROUTES_AND_OPENAPI_ESTABLISHED`
- `FORMAL_WORKFLOW_PROVIDER_SELECTION_CONTRACT_ESTABLISHED`
- `FORMAL_WORKFLOW_RETRY_BUDGET_CONTRACT_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_API_END_TO_END_VERIFIED`
- `FORMAL_WORKFLOW_FRONTEND_CUTOVER_ESTABLISHED`
- `LEGACY_ALIGNMENT_CONSUMER_BOUNDARY_IDENTIFIED`
- `LEGACY_ALIGNMENT_ROUTE_STILL_PRESENT`
- `FRONTEND_VISUAL_REDESIGN_NOT_COMPLETED`
- `HISTORICAL_RUN_LIST_NOT_IMPLEMENTED`
- `FULL_REVIEW_WORKBENCH_NOT_IMPLEMENTED`
- `PILOT_CREATE_ALL_ONLY`
- `FORMAL_MIGRATION_REQUIRED_BEFORE_PRODUCTION`

## Context

Task 9C.4S characterized legacy `POST /api/alignment/run` and concluded
`DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`. Task 9C.4T accepted
`LEGACY_ALIGNMENT_RUN_DEPRECATION_V1`. Task 9C.4U completed Phase 1 external
execution containment for the legacy endpoint, worker, retry, queued job, and
direct-helper paths.

The legacy route remains an active compatibility surface after the consumer
audit, but the teacher document-alignment start path no longer calls it. It can
still run local deterministic compatibility behavior for legacy worker/tests,
safety probes, and unknown external consumers, while external/live/custom
legacy execution is blocked with
`LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED`.

The formal system already has governed document ingestion, parse quality gates,
KnowledgeSource and KnowledgeChunk records, lexical evidence retrieval,
bilingual evidence workflow, Chinese term candidates, ConceptAlignmentCard
drafts, formal provider governance, policy, preflight, alignment verification,
UsageRecord, AuditRecord, teacher review, and student approved-only access.
Task 9C.4W establishes the document-level orchestration root and item-level
progress models needed to connect those components without reusing the legacy
execution path. Task 9C.4X establishes the first application slice:
workflow admission and start. That service validates a governed source through
explicit loaders/decisions, resolves idempotency, creates the workflow root,
creates a transport-only BackgroundJob, records `document_alignment_requested`,
and commits once. Processing orchestration, the local-pilot worker,
HTTP-neutral read-only run/item query services, and formal HTTP/OpenAPI routes
are implemented. Task 9C.5F.1 aligns the server-owned deterministic provider
selection across admission, preparation, governance, preflight, verification,
and attach. Task 9C.5F.2 freezes a three-count processing-failure budget for
new formal jobs and proves the HTTP Admission-to-requeue-to-resume path. Task
9C.5G v3 proves the local SQLite formal API from authenticated HTTP admission
through the formal worker, polling, pagination, partial/all-blocked outcomes,
source-scoped concurrent replay, retry/crash recovery, and authenticated
browser fetch. Task 9C.5H adds the minimal teacher-facing formal start,
polling, paginated items, refresh recovery, and duplicate-start prevention
without changing the formal backend contract.

Task 9C.4Y characterizes the processing boundary without implementing it. The
Task 9C.4Z then establishes a dedicated formal-job CAS claim, 30-second lease,
heartbeat, stale-running reclaim, attempt fencing, terminal immutability, and
formal/legacy worker isolation for the local SQLite pilot. This is
`AT_LEAST_ONCE_TRANSPORT` plus `ATTEMPT_FENCED_OWNERSHIP`, not exactly-once or a
formal processing worker. Task 9C.5A adds pure, governed chunk-scoped candidate
generation and an attempt-fenced, idempotent WorkflowItem bootstrap. It
processes each chunk independently, preserves chunk UID provenance, applies
`item-key-v1`, and persists item/root changes in the same short transaction as
a conditional BackgroundJob lease fence. Draft/preflight/verification/attach
collaborators still have independent commit defaults.

## Decision

Define a new formal workflow contract:

```text
FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION
```

Its responsibility is:

```text
governed document source
-> validate ownership and parse quality
-> obtain governed chunks
-> extract or receive term candidates
-> retrieve governed bilingual evidence
-> generate Chinese term candidates
-> create ConceptAlignmentCard drafts
-> invoke formal provider policy and preflight
-> invoke formal alignment verification
-> persist per-item outcome
-> expose progress and review readiness
-> hand off to teacher review
```

It is not a wrapper around legacy `run_alignment`, not a transparent alias for
`POST /api/alignment/verify`, and not a synchronous whole-document route.

The approved design direction is:

- Canonical input: `GOVERNED_KNOWLEDGE_SOURCE`.
- Execution model: `ASYNC_JOB_ORCHESTRATION`.
- Business root: new `DocumentAlignmentWorkflowRun`.
- Per-concept state: new `DocumentAlignmentWorkflowItem`.
- BackgroundJob role: transport envelope only.
- API family:
  - `POST /api/document-alignment-runs`
  - `GET /api/document-alignment-runs/{run_uid}`
  - `GET /api/document-alignment-runs/{run_uid}/items`
- Idempotency: required `Idempotency-Key` header for start requests.
- Data policy: `NO_LEGACY_AND_FORMAL_DUAL_WRITE`.
- Provider policy: formal governance, policy, preflight, parser, usage, and
  audit only.
- Student visibility: never from workflow output; only approved
  ConceptAlignmentCard records are student visible.

## Canonical Input

The start request requires a governed `knowledge_source_uid`.

The workflow derives these fields from `KnowledgeSource` and linked records:

- `parse_uid`
- `document_id`
- `course_id`
- `course`
- `chapter`
- `language`
- `visibility`
- `trust_level`
- `quality_status`
- source version information
- governed `KnowledgeChunk` rows

The request may include safe options:

- provider preference, if allowed by formal policy;
- candidate limit within server limits;
- dry-run-like local deterministic flags only if formal policy accepts them;
- workflow version, defaulting to the current server version.

The request must not include raw file bytes, full document text, arbitrary
trusted evidence JSON, raw provider prompts, provider credentials, custom base
URLs, `auto_approve`, or student visibility flags.

## Async Model

The workflow uses `ASYNC_JOB_ORCHESTRATION`.

The start route validates request and permission, creates a workflow root,
creates a BackgroundJob envelope, commits, and returns quickly with HTTP 202.
It does not process the whole document in the HTTP request.

Task 9C.4X implements the HTTP-neutral equivalent of that start operation as
`start_document_alignment_workflow(...)`. No route calls it yet. The command is
limited to `source_uid`, `requested_by`, `request_id`, and `idempotency_key`;
workflow version is server-controlled. The service creates only
`DocumentAlignmentWorkflowRun`, `BackgroundJob`, and `AuditRecord`.

BackgroundJob is a queue/worker transport record. It is not the source of
business truth. Domain status, progress counts, item state, idempotency, and
terminal errors belong to `DocumentAlignmentWorkflowRun` and
`DocumentAlignmentWorkflowItem`.

V1 does not expose user-initiated cancellation. Worker crash/retry behavior is
handled by job infrastructure, while item-level retry remains an implementation
choice under this contract.

## Workflow Root

Use a new model:

```text
DocumentAlignmentWorkflowRun
```

Task 9C.4W model fields:

- `run_uid`, unique;
- `source_uid`;
- `parse_uid`;
- `source_version` or stable content/version reference;
- `course_id`;
- `course`;
- `chapter`;
- `requested_by`;
- `request_id`;
- `idempotency_key`;
- `idempotency_fingerprint`;
- `workflow_version`;
- `provider_preference`;
- `provider_preference`;
- `model_preference`;
- `provider_policy_version`;
- `status`;
- `stage`;
- `total_items`;
- `successful_items`;
- `ready_for_review_items`;
- `blocked_items`;
- `failed_items`;
- `warning_count`;
- `created_at`;
- `started_at`;
- `finished_at`;
- `error_code`;
- `error_message`.

Existing models are insufficient. `BackgroundJob` lacks stable business
identity, source/version/idempotency fields, item outcome counts, and document
workflow terminal semantics. Legacy `AlignmentRun` is rejected as a formal root
because it carries legacy provider and TerminologyCard semantics.

## Item Model

Use a new model:

```text
DocumentAlignmentWorkflowItem
```

Task 9C.4W model fields:

- `item_uid`, unique;
- `workflow_run_id`;
- deterministic item key for retry/idempotent item writes;
- candidate term;
- normalized term;
- source chunk reference list;
- Chinese candidate summary;
- English and Chinese evidence reference lists;
- draft ConceptAlignmentCard UID;
- AlignmentVerificationRun UID;
- item status;
- risk labels;
- confidence summary;
- safe error code;
- safe error message;
- retry count;
- warning count;
- recommendation;
- confidence score and summary;
- created_at;
- updated_at;
- finished_at.

The item model must not duplicate full evidence text, full prompts, raw
provider output, credentials, legacy AlignmentRun, legacy TerminologyCard,
legacy UsageRecord, legacy AICallLog, or complete source documents.

## State Machines

Root states:

- `queued`
- `validating`
- `processing`
- `ready_for_review`
- `completed_with_warnings`
- `blocked`
- `failed`

The root never uses `approved`, `published`, or `student_visible`.

Allowed root transitions:

| From | To | Trigger | DB owner | Audit event |
|---|---|---|---|---|
| none | queued | accepted start request | start service | document_alignment_requested |
| queued | validating | worker claim | worker orchestration | document_alignment_started |
| validating | blocked | source, permission, or parse gate blocked | worker orchestration | document_alignment_blocked |
| validating | processing | source and chunks usable | worker orchestration | document_alignment_started |
| processing | ready_for_review | all processed and all successful items reviewable | worker orchestration | document_alignment_completed |
| processing | completed_with_warnings | at least one item reviewable and at least one blocked or failed | worker orchestration | document_alignment_completed |
| processing | blocked | all items blocked with no reviewable output | worker orchestration | document_alignment_blocked |
| queued | failed | infrastructure/persistence failure | worker orchestration | document_alignment_failed |
| validating | failed | infrastructure/persistence failure | worker orchestration | document_alignment_failed |
| processing | failed | infrastructure/persistence failure | worker orchestration | document_alignment_failed |

Item states:

- `candidate`
- `evidence_ready`
- `draft_created`
- `verification_completed`
- `needs_review`
- `blocked`
- `failed`

Insufficient evidence, provider policy blocked, provider preflight blocked, no
Chinese candidate, duplicate term that cannot safely map to a draft, and
verification recommendation `insufficient_evidence` are item-level `blocked`
states unless a safe draft exists. Parser failure and persistence failure are
`failed`. Successful verification still ends as `needs_review`, not approved.

## Partial Failure

The workflow supports partial success. A single failed item does not fail the
whole document. Global source, permission, parse, or persistence failures can
block or fail the root.

Terminal root rules:

- at least one reviewable item and no item problems: `ready_for_review`;
- at least one reviewable item and some blocked/failed items:
  `completed_with_warnings`;
- all items blocked by domain gates: `blocked`;
- unsafe infrastructure or persistence failure: `failed`.

Failed and blocked items remain recorded. V1 does not expose an item retry API.

## Idempotency

`request_id` is trace and audit correlation only. It is not idempotency.

The start API requires `Idempotency-Key`.

Scope:

```text
user_id + knowledge_source_uid + workflow_version + idempotency_key
```

Rules:

- same key and same canonical payload: return the existing run with
  `idempotency.reused=true`;
- same key and different canonical payload: return HTTP 409 conflict;
- repeated worker execution uses item keys and persisted run/item state, not the
  HTTP request ID;
- small-pilot retention is 30 days for active idempotency records or until the
  workflow root is archived by a later policy.

Task 9C.4X implements the backing service behavior for this policy:

- fingerprint is stable SHA-256 over source UID, parse UID, source version,
  course, chapter, and workflow version;
- request ID, idempotency key, timestamps, generated UIDs, credentials, and raw
  source content are excluded from the fingerprint;
- same scope and same fingerprint returns the existing run without creating a
  second job or audit record;
- same scope and different fingerprint returns
  `DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT`;
- idempotency unique-constraint races are rolled back and re-resolved by
  querying the persisted run.

Task 9C.4X also defines `item-key-v1`: normalize the term using Unicode NFKC,
trim and fold whitespace, casefold, normalize chunk references by trimming,
deduplicating, and sorting, then store only `item-key-v1:<sha256>`.

## Provider Governance

The workflow may invoke provider execution only through:

- formal provider governance;
- formal provider policy;
- formal provider preflight;
- formal alignment verification execution service;
- formal output parser/schema;
- formal AlignmentProviderUsageRecord;
- formal AuditRecord.

It must not call legacy provider helpers, `urllib`, legacy AICallLog, legacy
UsageRecord, or any credential-bearing legacy configuration. External provider
defaults remain disabled. Provider blocked, preflight blocked, and insufficient
evidence cases produce no provider usage.

## Evidence And Prompt Boundary

Evidence comes only from governed `KnowledgeSource` and `KnowledgeChunk`
records through the evidence retrieval and bilingual evidence workflow. The
client may not submit arbitrary evidence and have it treated as trusted.

The workflow does not store full prompts or raw provider output. Formal
verification owns prompt construction and records prompt/schema summaries on
`AlignmentVerificationRun`. Workflow root and items store only references,
counts, risk labels, and safe summaries.

## Card And Verification Integration

Each processable concept creates or reuses a safe ConceptAlignmentCard draft.
Draft status is `needs_review` or another formally safe review state. Formal
verification can be attached only through the existing attach gate and provider
policy.

The workflow cannot auto approve a card, cannot publish to students, and cannot
overwrite an approved card. Teacher review remains the owner of approval.

## Data Ownership

Policy: `NO_LEGACY_AND_FORMAL_DUAL_WRITE`.

Formal workflow reads governed source/chunk data and writes only formal
workflow root/item records, BackgroundJob transport records, ConceptAlignmentCard
draft/review-ready data, AlignmentVerificationRun, AlignmentProviderUsageRecord,
and AuditRecord.

Formal workflow must not write legacy `AlignmentRun`, legacy
`TerminologyCard`, legacy `AICallLog`, or legacy `UsageRecord`.

Legacy `/api/alignment/run` must not begin writing formal workflow root/item
records during the compatibility period.

## Transaction Boundaries

The workflow must not hold a long database transaction around term extraction,
evidence retrieval, provider execution, or other long-running work.

Transaction plan:

1. Start transaction: validate request, permission, source identity, create
   workflow run, create BackgroundJob envelope, create request audit, commit.
2. Worker claim transaction: claim job, mark run started/validating, commit.
3. Per-item transactions: write item/draft/verification references in short
   commits; pure computation and provider execution happen outside long
   transactions.
4. Finalization transaction: aggregate item states, set terminal run status,
   write completion audit, commit.

The existing formal verification execution service owns its own commit/rollback
today. Before document workflow orchestration calls it in a loop, the next
implementation slice must either call it as an isolated per-item unit or create
a persistence-plan boundary that prevents uncontrolled nested transactions.

## Retry

Worker infrastructure retry covers crash, transient database errors, and
temporary infrastructure failures.

Formal document-alignment V1 freezes `max_attempts=3` when Admission creates a
BackgroundJob. This means at most three counted processing-failure outcomes
and two requeues. `execution_attempt` is the lease ownership generation and
advances on claim or stale reclaim. `attempt_count` is the consumed business
failure budget: claim, heartbeat, and stale reclaim do not change it; requeue
increments it once; retry-exhausted failure consumes the final count. Existing
jobs retain their creation-time `max_attempts`, including historical value
`1`; no backfill is performed.

A claim or stale reclaim that loses ownership or crashes before producing a
typed processing outcome does not consume `attempt_count`. Consequently,
`execution_attempt` may exceed `max_attempts`; V1 has no separate persisted cap
on repeated pre-outcome crash/reclaim generations. The retry budget is not a
bound on every process invocation. A supervised production runtime must add an
operational crash-loop policy and alerting before this can be treated as a
bounded distributed execution guarantee.

Only typed outcomes `retryable_interruption` and `persistence_error` may
requeue. A bare `retryable=True` cannot override invalid state, ownership loss,
terminal state, or a business block. Unknown processing outcomes fail closed:
the handler finalizes the Root as failed before failing the still lease-owned
BackgroundJob. Exhaustion uses the same Root-first ordering, including count
recomputation and idempotent failure audit.

Item retry covers retryable provider or retrieval failures only if the item key
prevents duplicate draft or verification creation. Non-retryable blocked states
include permission, parse quality, provider policy, provider preflight,
insufficient evidence, and invalid source.

Usage is recorded only for actual formal provider executions. A retry must not
double-count the same actual call.

## Permissions

Start permission:

- admin: allowed across courses;
- teacher: allowed only for governed sources in courses they can manage;
- reviewer: not allowed to start V1 workflow;
- student: not allowed.

Read permission:

- admin;
- creator;
- teacher with course access;
- reviewer with active course review permission may read review-relevant
  summaries but not source-private text;
- student cannot read workflow drafts or verification output.

Permission checks occur before run/job creation and must not leak source
existence across courses.

## Audit And Request ID

The start API and status APIs use formal response envelopes with request IDs.

Required audit events:

- `document_alignment_requested`
- `document_alignment_started`
- `document_alignment_blocked`
- `document_alignment_completed`
- `document_alignment_failed`

Audit payloads contain source UID, course, run UID, counts, provider/model
summary, prompt version, risk summary, and safe error codes. They must not
contain full documents, full chunks, full evidence, full prompts, raw provider
output, credentials, Authorization, or Cookie values.

## Usage

Usage is created only by formal provider execution. Blocked before provider,
insufficient evidence, policy blocked, and preflight blocked outcomes have usage
zero. Workflow root may aggregate usage totals by reference or summary but must
not duplicate usage details. Legacy UsageRecord is never written.

## API Contract

Start endpoint:

```text
POST /api/document-alignment-runs
Endpoint: create_document_alignment_run
HTTP status: 202
Required header: Idempotency-Key
```

Request:

```json
{
  "source_uid": "source-uid"
}
```

Response:

```json
{
  "status": "success",
  "request_id": "req-...",
  "data": {
    "run_uid": "workflow-run-uid",
    "status": "queued",
    "status_url": "/api/document-alignment-runs/workflow-run-uid",
    "items_url": "/api/document-alignment-runs/workflow-run-uid/items",
    "workflow_version": "formal-document-alignment-v1",
    "stage": "queued",
    "source_uid": "source-uid",
    "reused": false,
    "items_url": "/api/document-alignment-runs/workflow-run-uid/items"
  }
}
```

The runtime contract deliberately does not expose the transport job UID,
payload, worker, attempt, lease, or token. The server owns workflow version,
provider selection, and processing limits; the V1 HTTP body therefore accepts
only `source_uid` and rejects unknown fields.

Status endpoint:

```text
GET /api/document-alignment-runs/{run_uid}
Endpoint: get_document_alignment_run
```

Items endpoint:

```text
GET /api/document-alignment-runs/{run_uid}/items
Endpoint: list_document_alignment_run_items
```

Items are paginated and do not return raw prompts or raw provider output.

## Error Taxonomy

Synchronous start errors:

- `DOCUMENT_ALIGNMENT_SOURCE_NOT_FOUND`
- `DOCUMENT_ALIGNMENT_SOURCE_PERMISSION_DENIED`
- `DOCUMENT_ALIGNMENT_SOURCE_NOT_GOVERNED`
- `DOCUMENT_ALIGNMENT_PARSE_BLOCKED`
- `DOCUMENT_ALIGNMENT_NO_USABLE_CHUNKS`
- `DOCUMENT_ALIGNMENT_IDEMPOTENCY_REQUIRED`
- `DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT`
- `DOCUMENT_ALIGNMENT_INVALID_REQUEST`

Asynchronous terminal errors:

- `DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES`
- `DOCUMENT_ALIGNMENT_PROVIDER_POLICY_BLOCKED`
- `DOCUMENT_ALIGNMENT_PROVIDER_PREFLIGHT_BLOCKED`
- `DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT`
- `DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED`
- `DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED`

No error includes a raw exception.

## Frontend Cutover

Task 9C.5H completes the minimal replacement frontend migration:

1. replacement backend route and service available;
2. contract tests and worker tests pass;
3. replacement E2E covers start, polling, item results, warnings, blocked
   outcomes, refresh recovery, pagination, and errors;
4. document action switches from `/api/alignment/run` to the new start API;
5. frontend polls the workflow status and item endpoints;
6. static scan proves `/api/alignment/run` frontend references are zero;
7. dynamic E2E proves legacy route call count is zero;
8. only then can the legacy endpoint move toward a separate consumer audit and
   HTTP 410 readiness decision.

## Readiness And Observability

Future readiness checks must cover:

- workflow route registered;
- worker handler registered;
- queue runnable;
- external provider disabled by default;
- provider policy and preflight available;
- source and parse gate available;
- no legacy/formal dual-write;
- no auto approval;
- request ID and AuditRecord creation;
- stuck job count;
- failed job count;
- oldest queued age.

Metrics:

- `document_alignment_runs_total`;
- counts by root status;
- `document_alignment_items_total`;
- `items_ready_for_review`;
- `items_blocked`;
- `evidence_insufficient`;
- `provider_blocked`;
- average processing time;
- draft count per document.

## Model And Migration Decision

The current models are not sufficient for the formal workflow root or item
progress. New workflow models are required before an application service.

Small-pilot implementation may continue using the current `create_all` pattern
because the repository has not yet introduced a formal migration framework and
This design began as `PROPOSED_FOR_SMALL_PILOT`; its current status is
`ACCEPTED_FOR_SMALL_PILOT`. Production rollout requires a
separate migration hardening task before real deployment.

Main conclusion:

```text
FORMAL_WORKFLOW_MODELS_REQUIRED_FIRST
```

This is the historical Task 9C.4V model prerequisite, satisfied by Task
9C.4W. It is not the current processing-planning conclusion.

## Processing Boundary Decision

Task 9C.4Y freezes the command/result contracts, grouped collaborators,
root/item state machines, candidate and item bootstrap rules, governed
evidence and Chinese candidate policies, approved-card protection,
formal-only verification sequence, short transaction boundaries, partial
failure aggregation, retry/resume behavior, safe errors, audit/usage rules,
worker adapter, and paginated query boundary in
`docs/formal_document_alignment_workflow_boundary.md`.

The formal processing worker must not be registered until BackgroundJob has an
atomic claim and attempt-owned lease contract. A claim must identify its
worker/attempt, support heartbeat and stale-running recovery, and reject an old
worker that tries to persist progress or finalize after ownership changed.
BackgroundJob remains transport-only; WorkflowRun and WorkflowItem remain the
business state truth.

Historical Task 9C.4Y conclusion:
`WORKER_CLAIM_AND_LEASE_CONTRACT_REQUIRED_FIRST`.

Task 9C.4Z satisfies that local-pilot ownership prerequisite. Task 9C.5A then
satisfies the chunk-scoped candidate and item persistence prerequisite:

```text
FORMAL_CHUNK_SCOPED_ITEM_BOOTSTRAP_ESTABLISHED
```

Task 9C.5B correctly stopped at its schema gate. Task 9C.5B.1 adds a persistent
per-item execution mapping, stable safe-input/execution identities, and
nullable unique identities for formal verification, preflight, usage, and
audit records:

```text
FORMAL_ITEM_EXECUTION_IDEMPOTENCY_SCHEMA_ESTABLISHED
```

Task 9C.5B (retry) consumes those identities in a lease-fenced per-item
adapter. It creates or reuses a safe draft, enforces formal policy and
preflight, creates or reuses one verification/usage/audit identity, persists
reference-only verification summaries, and resumes protected attach without
re-running a completed verification. External/live/custom providers remain
fail-closed. A crash after `provider_started` may replay only the currently
allowed deterministic provider; this is not provider exactly-once.
The adapter also binds the active formal job payload to the workflow root and
binds prepared candidate/evidence identity to the persisted item at every
write fence. V1 accepts one already-selected Chinese candidate plus one
provenance reference; candidate ranking remains an upstream responsibility.
Provider completion is checkpointed before verification persistence, and the
approved-card attach uses a conditional update so a concurrent teacher
approval cannot be overwritten.

Task 9C.5C composes the established boundaries in
`backend/services/document_alignment_processing_orchestrator.py`. The
HTTP-neutral and worker-neutral service validates the formal job/run identity
and active lease, invokes the existing bootstrap, prepares one item at a time
through the governed bilingual evidence and Chinese-candidate services, calls
only the per-item verification adapter for draft/provider/verification work,
recalculates progress from persisted items, and finalizes the workflow root
with an idempotent root audit. It preserves completed items across business
blocks and source drift, stops on infrastructure or lease failures, and leaves
BackgroundJob completion/failure/requeue to the future formal worker handler.
The V1 execution policy is `SINGLE_SEQUENTIAL_ORCHESTRATOR_PER_LEASE`.

Task 9C.5D adds a separate formal dispatcher, strict payload handler, explicit
production dependency composition, typed result-to-job mapping,
retry-exhaustion root finalization, stale-reclaim recovery, and local worker
rotation. Claim/reclaim advance only `execution_attempt`; requeue or permanent
failure consumes `attempt_count` once. Completion requires a matching terminal
root, and the generic legacy worker continues to exclude formal jobs.

Task 9C.5E adds permission-gated run summaries and database-paginated item
summaries. Admins, requesters, and authorized course teachers may read them;
students, anonymous users, and unrelated teachers cannot. Transport ownership,
raw content, and internal execution identities are excluded, and queries do
not write or repair state.

This establishes an executable and teacher-facing local-pilot path with formal
HTTP/OpenAPI and a minimal frontend caller. There is still no supervised
production runtime, formal historical run list, or full review workbench.
Deterministic provider replay remains at-least-once after the existing
provider-started crash point. The concurrent duplicate-invocation tests use
SQLite and independent sessions; PostgreSQL locking, migration, and
operational recovery remain unverified.

## Rejected Alternatives

1. Wrap legacy `run_alignment` as a service.
2. Alias `/api/alignment/run` to `/api/alignment/verify`.
3. Process an entire document synchronously in the request.
4. Use BackgroundJob as all domain state.
5. Dual-write legacy and formal data.
6. Auto approve cards.
7. Accept client-submitted arbitrary evidence as trusted evidence.
8. Default to live/external provider.
9. Hold long database transactions around provider execution.
10. Use request ID as idempotency key.
11. Overwrite approved cards from workflow output.
12. Delete legacy endpoint before frontend cutover.

## Consequences

The model, admission, formal BackgroundJob ownership, chunk-scoped item
bootstrap, execution identities, lease-fenced per-item verification adapter,
document processing/root finalization, formal local-pilot worker handler,
read-only query services, narrow formal HTTP/OpenAPI adapters, and local API
polling/recovery/browser-session verification, and the minimal teacher
frontend cutover are implemented. The next permitted slice audits remaining
legacy consumers before any retirement action:

```text
Task 9C.5I: Legacy Alignment Consumer Audit, Deprecation Boundary and 410 Readiness
```

The legacy endpoint remains active pending that audit and still has external
execution disabled. HTTP 410 and legacy path removal remain later decisions.
A formal historical run list, complete review workbench, and visual redesign
are outside the minimal cutover.

## Pilot Limitations

This ADR is not production-ready. It does not enable real providers. The local
worker is not a supervised production daemon. The formal
tables are still `PILOT_CREATE_ALL_ONLY`; production migrations and PostgreSQL
claim/locking and idempotency-constraint validation remain required. Provider
success followed by persistence failure is recoverable only by deterministic
replay under the same execution key; external provider replay and exactly-once
charging are deliberately unsupported.
