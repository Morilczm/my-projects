# Formal Document Alignment Processing Orchestrator

Status: `FORMAL_DOCUMENT_ALIGNMENT_PROCESSING_ORCHESTRATOR_ESTABLISHED`

Task: 9C.5C

Baseline: `ff1b543d71454667f7bc4a0bd72a0b756d94ab12`

Scope: internal local-pilot application service. Task 9C.5D now invokes this
service through the formal worker; no route, OpenAPI contract, frontend caller,
external provider, production daemon, or production migration is established.

## Service Boundary

```text
active formal BackgroundJob lease
-> validate job/run identity
-> bootstrap or resume WorkflowItems
-> prepare governed evidence and one Chinese candidate
-> persist evidence_ready checkpoint
-> invoke formal per-item verification adapter
-> recompute progress from persisted items
-> continue business-level partial failure
-> stop infrastructure or lease failure
-> finalize WorkflowRun and root audit
-> return typed result
```

`document_alignment_processing_orchestrator.py` remains HTTP-neutral and
worker-neutral. Task 9C.5D's handler owns claim-result mapping to BackgroundJob
complete, fail, or requeue. The orchestrator does not mutate a job's terminal
state or clear its lease.

## Contracts

`ProcessDocumentAlignmentWorkflowCommand` is frozen and contains only:

- workflow run UID;
- formal job UID;
- worker ID;
- execution attempt;
- repr-hidden lease token.

`ProcessDocumentAlignmentWorkflowResult` is frozen and contains the safe root
status/stage, progress counts, invocation counts, stopped item UID, retryable
flag, and bounded safe error. It contains no ORM object, evidence body,
candidate body, prompt, provider output, credential, or lease token.

Dependencies are grouped as bootstrap, preparation, item verification, and
lease collaborators plus the four formal models needed for root coordination.
The service does not receive Flask, routes, a worker dispatcher, transport,
credentials, legacy services, or an unrestricted application registry.

## Component And Transaction Matrix

| Component | Actual entry | Write owner | Rollback owner |
|---|---|---|---|
| Lease heartbeat | `heartbeat_formal_background_job` | formal lease service | formal lease service |
| Lease fence | `fence_active_formal_job_lease_in_transaction` | surrounding short transaction | surrounding owner |
| Item bootstrap | `bootstrap_document_alignment_workflow_items` | bootstrap service | bootstrap service |
| Chinese candidates | `generate_chinese_term_candidates` | read-only | preparation rollback |
| Bilingual evidence | `retrieve_bilingual_evidence` | read-only | preparation rollback |
| Evidence-ready checkpoint | processing orchestrator | processing orchestrator | processing orchestrator |
| Draft/preflight/verification/attach | `execute_document_alignment_item_verification` | per-item adapter | per-item adapter |
| Progress recount | processing orchestrator | processing orchestrator | processing orchestrator |
| Root finalization/audit | processing orchestrator | processing orchestrator | processing orchestrator |
| BackgroundJob terminal mapping | `document_alignment_worker_handler.py` | formal ownership service | formal ownership service |
| Retry-exhausted root finalization | processing orchestrator public helper | processing orchestrator | processing orchestrator |

There are no unknown transaction owners in the composed V1 path. Collaborator
commits remain explicit boundaries: bootstrap and the per-item adapter own their
short transactions; preparation is read-only; the orchestrator owns only its
evidence checkpoint, progress recount, and root finalization transactions.

## Preparation

Preparation reloads the run, item, source, and item-scoped chunks. Source UID,
parse UID, version, active state, and parse quality must still match. English
evidence is restricted to the item's source chunk references. Chinese evidence
comes from governed same-course/chapter retrieval. Candidate selection is
stable by descending score, candidate UID, then casefolded value.

Only one selected Chinese value and one provenance reference enter the 9C.5B
prepared input. Bounded 500-character snippets exist only in memory. Workflow
items persist references, candidate/provenance summary, count, and risk labels,
not snippets or raw document text.

## Processing And Resume

Items are read in database ID order with item key as tie-break. Processing is
single-threaded. `needs_review`, `blocked`, and `failed` are skipped. Candidate
items are prepared and checkpointed. `evidence_ready`, `draft_created`, and
`verification_completed` rebuild bounded input and resume through the existing
adapter. A completed verification and attach retry retain the adapter's
execution-key reuse and do not create a second logical usage or audit record.

Heartbeat occurs at entry, before and after bootstrap, before each item, after
preparation, after adapter return, and before root finalization. Each business
write is protected by the formal transaction lease fence. Stale/expired typed
lease outcomes stop immediately.

## Partial Failure And Progress

Evidence insufficiency and no governed Chinese candidate block that item and
continue. Policy/preflight/approved-card/parser/attach business outcomes are
owned by the adapter and later items continue. Database, session, unavailable
chunk, retryable adapter, or unknown infrastructure failure stops the current
invocation and leaves the root nonterminal.

Source identity/version drift is run-level consistency failure. Under an
active fence, all unstarted candidate items are blocked with
`DOCUMENT_ALIGNMENT_SOURCE_CHANGED`; completed items and cards remain intact.

Progress is recomputed from database item states after each item and at
finalization. No increment-only counters are trusted. V1 warning count is:

```text
needs_review items with nonempty risk labels + blocked items + failed items
```

## Root Finalization And Audit

| Item aggregate | Root status |
|---|---|
| all needs_review | ready_for_review |
| needs_review plus blocked/failed | completed_with_warnings |
| all blocked | blocked |
| no needs_review and any failed | failed |
| any nonterminal item | remain processing |

Root terminalization and its audit are one fenced transaction. Root event
identity is a SHA-256 identity derived from identity version, run UID, workflow
version, and event type. Worker, attempt, lease, request ID, timestamp, and
random UID are excluded. Unique conflicts reuse the logical event.

## Safety And Data Ownership

The path may write only formal workflow/item/execution, ConceptAlignmentCard,
formal preflight/verification/usage, AuditRecord, and lease heartbeat fields.
It does not write legacy AlignmentRun, TerminologyCard, UsageRecord, AICallLog,
legacy jobs, or student state. Cards remain `needs_review`; approved cards are
never changed or reverified; external/live/custom provider execution remains
fail-closed.

## Evidence And Limits

Tests cover real bootstrap, governed evidence/candidate composition, the real
item adapter, partial outcomes, source drift, resume, fault checkpoints,
approved-card protection, secret persistence, no-network, and five rounds of
same-lease competition using two independent SQLite sessions/connections.

The concurrency result proves database identity convergence for this SQLite
test shape. It does not establish safe parallel item scheduling, provider
exactly-once, PostgreSQL locking behavior, multi-host worker operation, or
production recovery. Formal migration, PostgreSQL verification, monitoring,
query services, routes, OpenAPI, and frontend cutover remain required. The
local worker dispatch added by Task 9C.5D is not a production runtime.

Task 9C.5D now provides the formal dispatcher and worker handler described by
the earlier plan. Next permitted task:

```text
Task 9C.5E: Formal Document Alignment Query Services
```
