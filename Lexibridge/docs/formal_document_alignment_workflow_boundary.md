# Formal Document Alignment Workflow Boundary

Status:
- `CONTRACT_PROPOSED`
- `ACCEPTED_FOR_SMALL_PILOT`
- `FORMAL_WORKFLOW_MODELS_ESTABLISHED`
- `WORKFLOW_ADMISSION_SERVICE_ESTABLISHED`
- `PROCESSING_BOUNDARY_CHARACTERIZED`
- `FORMAL_JOB_EXECUTION_OWNERSHIP_ESTABLISHED_FOR_LOCAL_PILOT`
- `FORMAL_CHUNK_SCOPED_TERM_BOOTSTRAP_ESTABLISHED`
- `FORMAL_ITEM_VERIFICATION_TRANSACTION_ADAPTER_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_PROCESSING_ORCHESTRATOR_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_ESTABLISHED`
- `FORMAL_WORKFLOW_QUERY_SERVICES_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_ROUTES_AND_OPENAPI_ESTABLISHED`
- `FORMAL_WORKFLOW_PROVIDER_SELECTION_CONTRACT_ESTABLISHED`
- `FORMAL_WORKFLOW_RETRY_BUDGET_CONTRACT_ESTABLISHED`
- `FORMAL_DOCUMENT_ALIGNMENT_API_END_TO_END_VERIFIED`
- `FRONTEND_NOT_MIGRATED`
- `LEGACY_REPLACEMENT_NOT_IMPLEMENTED`
- `FORMAL_WORKFLOW_MODELS_REQUIRED_FIRST`
- `PILOT_CREATE_ALL_ONLY`
- `FORMAL_MIGRATION_REQUIRED_BEFORE_PRODUCTION`

Task: 9C.5G v3
Implementation update: authenticated local HTTP start, formal worker processing, polling, pagination, source-scoped concurrent replay, recovery, and browser API access are verified; frontend remains absent
Baseline: `9a2556f1e626fef9521d8b598c138f50407d9e03`
Workflow: `FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`
Canonical input: `GOVERNED_KNOWLEDGE_SOURCE`
Execution model: `ASYNC_JOB_ORCHESTRATION`
Data policy: `NO_LEGACY_AND_FORMAL_DUAL_WRITE`
Background job policy: `BACKGROUND_JOB_AS_TRANSPORT_ONLY`

This document defines the formal document-alignment workflow contract and the
implemented model, admission, execution-ownership, item bootstrap,
per-item verification, document processing, local worker, query, and HTTP
boundaries. It does not implement frontend changes, full formal API E2E, or a
production migration/runtime framework. Legacy
`POST /api/alignment/run` remains temporary frontend
compatibility with external execution disabled.

## Component Matrix

| Component | Existing artifact | Reuse policy | Writes | Transaction owner |
|---|---|---|---|---|
| Document parse quality | `DocumentParseRecord`, `DocumentParseBlock`, `services/document_parse_quality.py` | reuse parse and quality gate | parse records and audit during ingestion | existing parse/ingestion owners |
| Governed source | `KnowledgeSource`, `KnowledgeChunk`, `services/knowledge_ingestion.py` | canonical input and evidence source | governed source/chunk during ingestion only | ingestion route/job |
| Evidence retrieval | `services/evidence_retrieval.py` | reuse read-only lexical retrieval | none | workflow caller |
| Bilingual evidence | `services/bilingual_evidence_workflow.py` | reuse DTO and bounded evidence package | none | workflow caller |
| Chinese candidates | `services/chinese_term_candidates.py` | reuse deterministic candidate extraction | none | workflow caller |
| Draft card | `services/concept_card_drafts.py`, `ConceptAlignmentCard` | reuse safe `needs_review` draft creation | formal draft card and audit | draft service or workflow item transaction |
| Verification | `services/alignment_verification_execution.py`, `AlignmentVerificationRun` | reuse formal provider governance and parser path | verification run, provider usage, audit, optional attach | verification execution service |
| Provider governance | `services/provider_governance.py`, `services/provider_preflight.py` | required for every provider execution | policy/preflight/usage records through formal services | formal services |
| Teacher review | `services/concept_card_review.py` | final approval owner | review record, card status, audit | review service |
| Queue transport | `BackgroundJob` | transport envelope only | job progress/events | job infrastructure |
| Workflow root | `DocumentAlignmentWorkflowRun` | established in 9C.4W | formal root status/progress | future workflow service |
| Workflow item | `DocumentAlignmentWorkflowItem` | established in 9C.4W | item state/references | future workflow service |
| Workflow admission | `services/document_alignment_workflow_application.py` | established in 9C.4X | root, BackgroundJob, AuditRecord | admission application service |
| Item preparation | `services/document_alignment_item_preparation.py` | established in 9C.5C | read-only governed evidence/candidate composition | read transaction is rolled back by preparation |
| Processing orchestrator | `services/document_alignment_processing_orchestrator.py` | established in 9C.5C | root/item progress and root audit; indirect formal item writes | short lease-fenced checkpoints and established collaborators |
| Legacy run | `AlignmentRun`, `TerminologyCard`, `AICallLog`, legacy `UsageRecord` | do not reuse | legacy only while compatibility remains | legacy route/worker |

## Data Flow

```text
POST /api/document-alignment-runs
-> validate Idempotency-Key
-> validate teacher/admin permission
-> load governed KnowledgeSource
-> enforce parse/source/chunk quality gates
-> create DocumentAlignmentWorkflowRun
-> create BackgroundJob transport envelope
-> worker retrieves governed chunks
-> extract candidate concepts
-> retrieve bilingual evidence
-> generate Chinese candidate summary
-> create ConceptAlignmentCard draft
-> run formal provider policy and preflight
-> run formal alignment verification
-> persist DocumentAlignmentWorkflowItem outcome
-> aggregate workflow run status
-> teacher review
-> student sees only approved ConceptAlignmentCard
```

The workflow must not submit a full document prompt to a provider, accept
arbitrary client evidence as trusted, write legacy alignment rows, or auto
approve cards.

## State Transition Matrix

Root states:

| From | To | Trigger | Meaning |
|---|---|---|---|
| none | `queued` | start request accepted | root and BackgroundJob created |
| `queued` | `validating` | worker claimed | source and parse gates are being checked |
| `validating` | `processing` | source and chunks usable | candidate/item processing begins |
| `validating` | `blocked` | source/parse/chunk gate fails | no safe workflow output |
| `processing` | `ready_for_review` | all processable items succeeded | reviewable drafts exist with no item failures |
| `processing` | `completed_with_warnings` | some items succeeded and some blocked/failed | partial success |
| `processing` | `blocked` | all items blocked by domain gates | no reviewable output |
| `queued` | `failed` | infrastructure or persistence failure | unsafe terminal failure |
| `validating` | `failed` | infrastructure or persistence failure | unsafe terminal failure |
| `processing` | `failed` | infrastructure or persistence failure | unsafe terminal failure |

Item states:

| From | To | Trigger | Meaning |
|---|---|---|---|
| none | `candidate` | candidate selected | item identity created |
| `candidate` | `evidence_ready` | governed evidence found | evidence references are usable |
| `evidence_ready` | `draft_created` | safe draft persisted | ConceptAlignmentCard draft exists |
| `draft_created` | `verification_completed` | formal verification run completed | parser and usage/audit path completed |
| `verification_completed` | `needs_review` | output is reviewable | teacher review required |
| any nonterminal | `blocked` | policy/preflight/evidence/domain gate blocks | safe domain block |
| any nonterminal | `failed` | infrastructure/parser/persistence failure | unsafe processing failure |

No workflow state grants student visibility.

## Model Fields And Constraints

`DocumentAlignmentWorkflowRun` table:

```text
document_alignment_workflow_runs
```

Root fields:

- `id`;
- `run_uid`, unique, non-null;
- `source_uid`, non-null;
- `parse_uid`, non-null;
- `source_version`;
- `course`;
- `chapter`;
- `requested_by`, non-null;
- `request_id`;
- `idempotency_key`, non-null;
- `idempotency_fingerprint`, non-null;
- `workflow_version`, non-null;
- `retrieval_version`;
- `prompt_version`;
- `provider_policy_version`;
- `provider_preference`;
- `model_preference`;
- `status`;
- `stage`;
- `total_items`;
- `successful_items`;
- `ready_for_review_items`;
- `blocked_items`;
- `failed_items`;
- `warning_count`;
- `risk_summary`;
- `error_code`;
- `error_message`;
- `created_at`;
- `started_at`;
- `finished_at`;
- `updated_at`.

Root constraints and indexes:

- unique `run_uid`;
- `uq_document_alignment_workflow_idempotency` over
  `requested_by`, `source_uid`, `workflow_version`, `idempotency_key`;
- non-negative checks for progress and warning counts;
- `ix_document_alignment_workflow_source_status`;
- `ix_document_alignment_workflow_requested_created`.

`DocumentAlignmentWorkflowItem` table:

```text
document_alignment_workflow_items
```

Item fields:

- `id`;
- `item_uid`, unique, non-null;
- `workflow_run_id`, foreign key to `DocumentAlignmentWorkflowRun`;
- `item_key`, non-null;
- `candidate_term`, non-null;
- `normalized_term`, non-null;
- `source_chunk_refs`;
- `chinese_candidate_summary`;
- `english_evidence_refs`;
- `chinese_evidence_refs`;
- `draft_card_uid`;
- `verification_run_uid`;
- `status`;
- `stage`;
- `risk_labels`;
- `confidence_score`;
- `confidence_summary`;
- `recommendation`;
- `warning_count`;
- `error_code`;
- `error_message`;
- `retry_count`;
- `created_at`;
- `updated_at`;
- `started_at`;
- `finished_at`.

Item constraints and indexes:

- unique `item_uid`;
- `uq_document_alignment_workflow_item_key` over
  `workflow_run_id`, `item_key`;
- non-negative checks for `warning_count` and `retry_count`;
- `confidence_score` must be null or within `[0, 1]`;
- `ix_document_alignment_workflow_item_run_status`;
- `ix_document_alignment_workflow_item_draft_card`;
- `ix_document_alignment_workflow_item_verification`.

Relationship:

```text
DocumentAlignmentWorkflowRun.items
DocumentAlignmentWorkflowItem.workflow_run
```

The root uses dynamic item loading so future status APIs can page items instead
of loading a whole document workflow at once.

## Status And Stage Constants

The single source for status and stage strings is:

```text
backend/services/document_alignment_workflow_contract.py
```

Root statuses:

- `queued`;
- `validating`;
- `processing`;
- `ready_for_review`;
- `completed_with_warnings`;
- `blocked`;
- `failed`.

Root stages:

- `queued`;
- `source_validation`;
- `term_extraction`;
- `evidence_retrieval`;
- `draft_creation`;
- `verification`;
- `finalization`;
- `terminal`.

Item statuses:

- `candidate`;
- `evidence_ready`;
- `draft_created`;
- `verification_completed`;
- `needs_review`;
- `blocked`;
- `failed`.

Workflow statuses intentionally exclude `approved`, `published`, and
`student_visible`.

## Serialization Boundary

No HTTP serializer or response envelope is implemented in 9C.4W. The model
schema intentionally stores only stable references, counts, safe summaries,
status, stage, and safe error fields. Future serializers must not expose
database integer IDs, idempotency fingerprints, full evidence, raw prompts, raw
provider output, credentials, or raw exceptions.

## Admission Service Boundary

Task 9C.4X adds:

```text
backend/services/document_alignment_workflow_application.py
```

Public entry point:

```text
start_document_alignment_workflow(command, dependencies)
```

Command:

```text
StartDocumentAlignmentWorkflowCommand(
    source_uid,
    requested_by,
    request_id,
    idempotency_key,
)
```

The command is frozen and does not accept provider, model, prompt, credential,
base URL, arbitrary options, raw document, raw evidence, visibility, or
auto-approval fields. Workflow version is server-controlled.

Dependencies:

```text
DocumentAlignmentWorkflowApplicationDependencies(
    session,
    workflow_run_model,
    background_job_model,
    audit_record_model,
    source_loader,
    authorization_checker,
    source_admission_checker,
    current_time_factory,
    uid_factory,
    workflow_version,
    audit_recorder,
)
```

Dependencies are explicit collaborators, not a service locator. The service
does not import Flask, `backend.app`, route modules, worker code, provider
adapter/transport, `urllib`, `requests`, `httpx`, or `socket`.

Source snapshot:

```text
GovernedKnowledgeSourceSnapshot(
    source_uid,
    parse_uid,
    source_version,
    course,
    chapter,
    owner_user_id,
    visibility,
    source_status,
    source_trust_level,
    parse_status,
    parse_quality,
    usable_chunk_count,
)
```

The snapshot contains no raw document, chunk body, evidence, prompt, credential,
or source metadata blob.

Decision DTOs:

- `DocumentAlignmentWorkflowAuthorizationDecision`
- `DocumentAlignmentSourceAdmissionDecision`

Failure decisions are read-only: they create no workflow root, no job, and no
audit record. Safe error codes include:

- `DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE`
- `DOCUMENT_ALIGNMENT_SOURCE_NOT_GOVERNED`
- `DOCUMENT_ALIGNMENT_PARSE_BLOCKED`
- `DOCUMENT_ALIGNMENT_NO_USABLE_CHUNKS`
- `DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT`
- `DOCUMENT_ALIGNMENT_PERSISTENCE_ERROR`

Result:

```text
StartDocumentAlignmentWorkflowResult(
    outcome,
    run_uid,
    job_uid,
    status,
    stage,
    request_id,
    reused,
    error_code,
    error_message,
)
```

The result is not an HTTP response and contains no ORM object, raw exception,
database ID, credential, full payload, or route envelope.

## Server-Owned Provider Selection

Task 9C.5F.1 establishes one selection source in
`services/formal_document_alignment_provider_selection.py`. The small-pilot
default is deterministic local `mock-rule-v1`, model identity
`mock-rule-v1:v1`, prompt `alignment-v1`, plus the existing parser and output
schema versions. The selector validates that the provider registry and
sanitized provider config agree, that the provider is enabled locally, and
that it has no external transport, credential requirement, API-key variable,
or base URL.

Admission resolves this selection only after checking for an existing
source-scoped idempotent Run. A new Run persists provider, model, and prompt in
the same root/job/audit transaction. Replay returns the original frozen values
and does not overwrite them when server defaults later change. The HTTP body
continues to accept only `source_uid`; clients cannot choose these identities.

Item preparation uses only the persisted Run values. It has no provider,
model, or prompt fallback. Missing historical values fail closed with
`DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_MISSING`; unregistered, external, or
identity-drifted values fail with
`DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_INVALID`. Neither path calls a
provider, creates usage, or backfills old data. Governance evaluation,
preflight, and attach resolve the same effective built-in local policy for the
default mock provider. That policy is bounded, course-scoped by a server-only
wildcard, requires human review, allows no external call or production result,
and never enables auto-approval.

## Admission Transaction

Created path:

```text
validate command
-> load governed source snapshot
-> authorization decision
-> source admission decision
-> idempotency query
-> create DocumentAlignmentWorkflowRun
-> create BackgroundJob
-> create document_alignment_requested AuditRecord
-> flush
-> one commit
```

The service owns the transaction for admission. Successful creation commits
once. Persistence failures, audit creation failures, job construction failures,
flush failures, commit failures, and idempotency unique races all call explicit
rollback before returning a safe typed result.

Read-only paths do not commit:

- source not found;
- permission denied;
- source not governed;
- parse blocked;
- no usable chunks;
- idempotency replay;
- idempotency conflict.

The service creates only:

- `DocumentAlignmentWorkflowRun`;
- `BackgroundJob`;
- `AuditRecord` with event type `document_alignment_requested`.

It does not create `DocumentAlignmentWorkflowItem`, `AlignmentVerificationRun`,
`ConceptAlignmentCard`, provider usage, preflight, legacy `AlignmentRun`,
legacy `TerminologyCard`, legacy `UsageRecord`, or `AICallLog`.

## BackgroundJob Payload

9C.4X uses a distinct formal job type:

```text
formal_document_alignment_workflow_v1
```

The BackgroundJob payload is intentionally minimal:

```json
{
  "workflow_run_uid": "...",
  "workflow_version": "formal-document-alignment-v1"
}
```

The payload does not contain raw documents, chunks, evidence, prompts,
provider selections, credentials, base URLs, cookies, Authorization headers, or
card payloads. BackgroundJob remains transport-only and is not the business
root.

## Fingerprints And Item Keys

Admission fingerprint:

- stable JSON with `sort_keys=True` and fixed separators;
- SHA-256 hex digest;
- includes `source_uid`, `parse_uid`, `source_version`, `course`, `chapter`,
  and `workflow_version`;
- excludes `request_id`, `idempotency_key`, timestamps, generated UIDs,
  credentials, raw source content, chunks, and actor session data.

Item key:

```text
item-key-v1:<sha256>
```

`item-key-v1` normalizes term identity with Unicode NFKC, trimming, whitespace
folding, and casefolding. It normalizes source chunk IDs by trimming, removing
empty values, deduplicating, and sorting. It rejects empty term or empty chunk
scope and never includes raw terms or chunk IDs in the key string.

## Idempotency Implementation

The model scope remains:

```text
requested_by + source_uid + workflow_version + idempotency_key
```

Behavior:

| Condition | Result | Writes |
|---|---|---|
| no existing scoped run | `created` | one root, one job, one audit |
| same scope and same fingerprint | `reused` | none |
| same scope and different fingerprint | `idempotency_conflict` | none |
| unique race resolves to same fingerprint | `reused` after rollback | none beyond winning request |
| unique race resolves to different fingerprint | `idempotency_conflict` after rollback | none |

`request_id` is trace-only and never participates in idempotency.

## Partial Failure

Partial success is expected. One blocked or failed concept does not fail the
whole document if at least one reviewable item is produced. A source permission
failure, parse quality block, missing governed chunks, or workflow persistence
failure can block or fail the root.

Blocked item reasons include insufficient evidence, provider policy blocked,
provider preflight blocked, no Chinese candidate, duplicate concept collision,
and verification recommendation `insufficient_evidence`.

Failed item reasons include parser failure that cannot be safely represented,
database failure, worker infrastructure failure, and unexpected internal
processing errors.

## Idempotency

The start endpoint requires `Idempotency-Key`. `request_id` is only for trace
and audit correlation and must not be used for idempotency.

Scope:

```text
user_id + knowledge_source_uid + workflow_version + Idempotency-Key
```

Rules:

| Case | Result |
|---|---|
| same key and same canonical payload | return existing run with `idempotency.reused=true` |
| same key and different canonical payload | HTTP 409 with `DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT` |
| missing key | HTTP 400 with `DOCUMENT_ALIGNMENT_IDEMPOTENCY_REQUIRED` |
| worker retry | use persisted run/item state and deterministic item keys |

## Provider Governance

Provider execution is allowed only through the formal verification execution
path:

```text
provider governance
-> provider policy
-> provider preflight
-> formal alignment verification
-> formal output parser
-> AlignmentProviderUsageRecord
-> AuditRecord
```

The workflow must not call legacy provider helpers, legacy `urllib` transport,
legacy `AICallLog`, legacy `UsageRecord`, legacy provider globals, custom base
URLs, or credential-bearing compatibility config. External providers remain
disabled by default.

## Evidence And Prompt Boundary

Trusted evidence comes only from governed `KnowledgeSource` and
`KnowledgeChunk` rows. Client-submitted evidence is not trusted evidence for
the workflow.

Workflow root and item records store references, counts, safe summaries, risk
labels, and error codes. They do not store full documents, full chunks, full
prompts, raw provider output, credentials, Authorization, Cookie, or raw
exceptions.

Prompt construction remains owned by the formal verification layer.

## Card And Verification Integration

Each processable item creates or reuses a `ConceptAlignmentCard` draft in a
teacher-review state such as `needs_review`. Formal verification may attach to
that card only through the existing attach gate.

The workflow cannot:

- create approved cards;
- publish to students;
- overwrite approved cards;
- bypass teacher review;
- use verification output as an approval decision.

Student-facing APIs continue to read only approved, course-visible cards.

## Data Ownership And Write-Set

Policy: `NO_LEGACY_AND_FORMAL_DUAL_WRITE`.

Formal workflow may write:

- `DocumentAlignmentWorkflowRun`;
- `DocumentAlignmentWorkflowItem`;
- `BackgroundJob` and job events as transport;
- `ConceptAlignmentCard` drafts;
- `AlignmentVerificationRun`;
- `AlignmentProviderUsageRecord`;
- `AuditRecord`.

Formal workflow must not write:

- legacy `AlignmentRun`;
- legacy `TerminologyCard`;
- legacy `AICallLog`;
- legacy `UsageRecord`;
- legacy `/api/alignment/run` compatibility records.

Legacy `/api/alignment/run` must not write formal workflow root/item records.

## Transaction Boundaries

The workflow uses short transactions:

| Transaction | Writes | Notes |
|---|---|---|
| start | workflow root, BackgroundJob, request audit | returns HTTP 202 |
| worker claim | job claimed, root `validating` | no provider call inside transaction |
| per-item | item state, draft reference, verification reference | computation and provider calls happen outside long transactions |
| finalization | root aggregate state, completion audit | terminal status |

The existing verification execution service currently owns its own
commit/rollback. The document workflow must either call it as an isolated
per-item unit or introduce a persistence-plan boundary before orchestration
loops over many items.

## Retry

Retries must be idempotent at root and item level.

| Retry type | Allowed behavior |
|---|---|
| HTTP start retry | returns existing run or idempotency conflict |
| worker crash retry | resumes from persisted root/item state |
| item retry | may retry provider/retrieval failure if item key prevents duplicates |
| non-retryable gate | persists blocked item or blocked root |

Usage is recorded only for actual formal provider calls and must not be double
counted by worker retry.

## Permissions

| Role | Start workflow | Read workflow | See draft details | Student visible output |
|---|---:|---:|---:|---:|
| unauthenticated | no | no | no | no |
| student | no | no | no | approved cards only through student card APIs |
| reviewer | no in V1 | course review summaries only if authorized | review-relevant safe summaries | no direct draft publishing |
| teacher | own/manageable courses | own/manageable courses | yes for course | no direct student publishing |
| admin | yes | yes | yes | no direct student publishing |

Permission checks happen before run/job creation and must not leak cross-course
source existence.

## Audit, Request ID, And Usage

Formal API responses include request IDs. Required audit events:

- `document_alignment_requested`;
- `document_alignment_started`;
- `document_alignment_blocked`;
- `document_alignment_completed`;
- `document_alignment_failed`.

Audit payloads contain safe source UID, run UID, course, counts, provider/model
summary, prompt version, risk summary, and safe errors. Audit payloads do not
contain full documents, full evidence, full prompts, raw output, credentials,
Authorization, or Cookie.

Usage is written only by formal provider execution. Policy blocked, preflight
blocked, insufficient evidence, parse blocked, and local deterministic
non-provider outcomes create no provider usage.

## API Contract

Start:

```text
POST /api/document-alignment-runs
Endpoint: create_document_alignment_run
Required header: Idempotency-Key
Success status: 202
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
  "request_id": "req-123",
  "data": {
    "run_uid": "document-alignment-run-uid",
    "status": "queued",
    "status_url": "/api/document-alignment-runs/document-alignment-run-uid",
    "items_url": "/api/document-alignment-runs/document-alignment-run-uid/items",
    "workflow_version": "formal-document-alignment-v1",
    "stage": "queued",
    "source_uid": "source-uid",
    "reused": false
  }
}
```

Task 9C.5F resolves the older planning example in favor of the implemented
admission DTO: only `source_uid` is client input. Workflow version, provider,
candidate limits, job identity, and all execution ownership fields remain
server-controlled. Successful creation and replay both return `202`,
`Location`, fixed `Retry-After: 2`, and the existing request-id envelope.

Status:

```text
GET /api/document-alignment-runs/{run_uid}
Endpoint: get_document_alignment_run
```

Items:

```text
GET /api/document-alignment-runs/{run_uid}/items
Endpoint: list_document_alignment_run_items
```

Items are paginated and return references and safe summaries only.

## Error Matrix

| Code | Timing | HTTP | Provider execution | Usage |
|---|---|---:|---:|---:|
| `DOCUMENT_ALIGNMENT_SOURCE_NOT_FOUND` | start | 404 | no | no |
| `DOCUMENT_ALIGNMENT_SOURCE_PERMISSION_DENIED` | start | 403 | no | no |
| `DOCUMENT_ALIGNMENT_SOURCE_NOT_GOVERNED` | start | 422 | no | no |
| `DOCUMENT_ALIGNMENT_PARSE_BLOCKED` | start or worker | 422 or terminal blocked | no | no |
| `DOCUMENT_ALIGNMENT_NO_USABLE_CHUNKS` | start or worker | 422 or terminal blocked | no | no |
| `DOCUMENT_ALIGNMENT_IDEMPOTENCY_REQUIRED` | start | 400 | no | no |
| `DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT` | start | 409 | no | no |
| `DOCUMENT_ALIGNMENT_INVALID_REQUEST` | start | 400 | no | no |
| `DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES` | worker | terminal blocked | no | no |
| `DOCUMENT_ALIGNMENT_PROVIDER_POLICY_BLOCKED` | item | item blocked | no | no |
| `DOCUMENT_ALIGNMENT_PROVIDER_PREFLIGHT_BLOCKED` | item | item blocked | no | no |
| `DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT` | item | item blocked | no | no |
| `DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED` | worker | failed | no further execution | no duplicate usage |
| `DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED` | worker | failed | no raw exception | no duplicate usage |

## Legacy Replacement Mapping

| Legacy dependency | Replacement contract |
|---|---|
| `POST /api/alignment/run` | `POST /api/document-alignment-runs` |
| `GET /api/alignment/runs` document list refresh | workflow status and item endpoints |
| `BackgroundJob.alignment_run_id` | BackgroundJob transport references workflow root |
| legacy `AlignmentRun` summary | `DocumentAlignmentWorkflowRun` summary |
| legacy `TerminologyCard` write | `ConceptAlignmentCard` draft plus teacher review |
| legacy `AICallLog` | formal `AlignmentVerificationRun` and AuditRecord |
| legacy `UsageRecord` | formal `AlignmentProviderUsageRecord` |
| legacy provider helper | formal provider governance, policy, preflight, verification |

Frontend cutover must replace the document action, polling, result display,
error display, and legacy run list refresh without reusing `/api/alignment/run`.

## Implementation Prerequisites

Next task:

```text
Task 9C.4W: Formal Workflow Models
```

Required before service implementation:

- `DocumentAlignmentWorkflowRun`;
- `DocumentAlignmentWorkflowItem`;
- idempotency key storage or hash fields;
- root/item status fields;
- source/parse/chunk reference fields;
- progress/count fields;
- safe error fields;
- tests proving BackgroundJob is still transport only.

Application service, route, worker, frontend cutover, legacy HTTP 410, and
dead-path removal are later tasks.

## Unique Conclusion

```text
FORMAL_WORKFLOW_MODELS_REQUIRED_FIRST
```

Existing services are reusable building blocks, but existing models cannot
represent the formal document-level workflow root or item-level progress
without overloading BackgroundJob or legacy AlignmentRun. Therefore the next
slice must establish formal workflow models before implementation.

## Task 9C.4Y Processing Boundary Characterization

Task 9C.4Y supersedes the old implementation prerequisite above without
changing production behavior. The root and item models and admission service
now exist. Processing still must not be implemented until worker ownership is
safe and explicit.

Primary conclusion: `WORKER_CLAIM_AND_LEASE_CONTRACT_REQUIRED_FIRST`

The current queue is deliberately documented as SQLite-friendly and single
worker. `claim_next_background_job` selects the first queued or retrying row,
changes it in the ORM identity map, and commits. It does not use an atomic
compare-and-set, lease generation, heartbeat, or stale-running recovery. A
second worker can therefore observe the same row before the first commit, and
a crashed worker can leave it running indefinitely. Formal document alignment
contains provider and multi-table side effects, so operational single-worker
discipline is not a sufficient correctness boundary.

### Component Matrix

| Component | Current entry point | Input | Output | DB reads | DB writes | Commit owner | Rollback owner | Reusable |
|---|---|---|---|---|---|---|---|---:|
| Admission | `start_document_alignment_workflow` | frozen start command and governed snapshot decisions | typed created/reused/blocked result | source and idempotency scope | workflow root, transport job, request audit | admission service, one commit | admission service | yes |
| Term extraction | `backend.app.extract_terms_from_text(text)` | one complete text string | legacy dictionaries with term, context, confidence, status | optional legacy KB lookup | none | none | none | only behind a future chunk-scoping adapter |
| Governed evidence | `evidence_retrieval.search_evidence` | query plus governed filters | `EvidenceSearchResult` with bounded candidates | KnowledgeSource and KnowledgeChunk | none | none | none | yes |
| Bilingual evidence | `bilingual_evidence_workflow.retrieve_bilingual_evidence` | English term, optional Chinese term, course/chapter, filters | `BilingualEvidenceResult` | governed chunks/sources and optional candidate sources | none | none | none | yes, with formal filters |
| Chinese candidates | `chinese_term_candidates.generate_chinese_term_candidates` | term, course/chapter and explicit model collaborators | ranked deterministic candidates | formal cards, governed chunks, and optional legacy models | none | none | none | yes only when legacy model arguments are `None` |
| Draft card | `concept_card_drafts.create_concept_card_draft_from_evidence` | evidence draft input | `ConceptCardDraftResult` | governed evidence and existing drafts | ConceptAlignmentCard and AuditRecord | service by default; `commit=False` is supported | service always rolls back on exception and may commit failure audit | requires a processing adapter |
| Provider policy | `provider_governance.evaluate_provider_request` | provider, actor role, course and verification input | allowed/blocked policy decision | policy and formal provider usage | none | none | none | yes |
| Provider preflight | `provider_preflight.run_provider_preflight` | provider, course, actor and replay-dry-run choice | preflight row and report | provider config and policy | AlignmentProviderPreflightRun | preflight service by default; `commit=False` is supported | caller on failure | yes behind a transaction boundary |
| Formal verification | `alignment_verification_execution.execute_alignment_verification` | typed request, actor, audit context and dependencies | typed execution result | card, policy and usage | request/completion audits, verification run, formal usage, optional card attach | execution service uses multiple commits | execution service | not directly transaction-neutral |
| Verification core | `alignment_verification.verify_alignment` | normalized evidence and provider | run and parsed output | provider registry/config | AlignmentVerificationRun | core service by default; `commit=False` is supported | caller | yes behind a processing adapter |
| Attach gate | `provider_governance.can_attach_verification_to_card` plus `alignment_verification.apply_verification_result_to_card` | run, policy, card | attached card or blocked decision | policy/card | risk labels and review status only | attach helper by default; `commit=False` is supported | caller | yes behind a processing adapter |
| Provider usage | `record_alignment_provider_usage` / `provider_governance.record_provider_usage` | provider call summary and run UID | AlignmentProviderUsageRecord | usage budgets | formal provider usage and governance audit | helper by default | caller | yes only for an actual provider invocation |
| Audit | `audit_records.create_audit_record` and domain recorders | safe event summary | AuditRecord | none | AuditRecord | recorder by default | recorder/caller according to commit flag | yes with idempotent event policy |
| Teacher review | `concept_card_review` services/routes | draft card and teacher decision | review record and card state | formal card/review data | review record, card and audit | review service | review service | separate downstream owner |
| Student access | `student_concept_cards.get_approved_card` | authorized student and card UID | approved card only | formal card | none | none | none | unchanged |
| Job claim | `claim_next_background_job` | worker ID | running BackgroundJob | first queued/retrying row | job lock fields and event | job function | no explicit rollback | no for formal processing until claim contract exists |
| Job dispatch | `run_background_job` | job ID and worker ID | terminal/retrying job | BackgroundJob | job state/events plus handler writes | generic worker | handler/generic worker | formal job type not registered |

UNKNOWN transaction owner: 0. Every current owner is identified above; the
problem is incompatible ownership and missing idempotent claim semantics, not
an unidentified commit site.

### Frozen Processing Flow

```text
BackgroundJob
-> parse only workflow_run_uid and workflow_version
-> atomically claim the expected attempt
-> load DocumentAlignmentWorkflowRun
-> verify workflow version and legal run state
-> queued -> validating
-> reload governed source and parse snapshot
-> verify source version, visibility, trust and parse quality
-> load governed source chunks
-> extract candidates per chunk
-> canonicalize, scope, sort and deduplicate candidates
-> generate item-key-v1 from normalized term and sorted chunk IDs
-> create or reuse DocumentAlignmentWorkflowItems
-> set total_items
-> validating -> processing
-> process resumable items one at a time
-> retrieve governed bilingual evidence
-> generate deterministic Chinese candidates without legacy models
-> create or reuse a protected needs_review draft
-> apply formal provider policy
-> persist formal provider preflight
-> invoke formal verification through a transaction adapter
-> apply formal parser and attach gate
-> update item references and terminal item state
-> recompute root counts from persisted items
-> finalize root and BackgroundJob
-> write one safe, idempotent root terminal audit
```

The flow never writes legacy AlignmentRun, TerminologyCard, legacy UsageRecord,
AICallLog, or a legacy alignment payload. It never trusts client evidence,
stores a full document prompt, reads a provider credential in the orchestrator,
or approves a card.

### Processing Command

The future service accepts this frozen, HTTP-neutral contract:

```text
ProcessDocumentAlignmentWorkflowCommand(
    workflow_run_uid: str,
    job_uid: str,
    worker_id: str,
    execution_attempt: int,
    lease_token: str,
    expected_job_status: str,
)
```

The persisted execution attempt and opaque lease token are both required.
Worker ID or transport status alone never proves ownership. The command contains no
raw document, chunks, evidence body, credential, provider URL, prompt, Flask
request, HTTP response, user session, ORM graph, or route dependency container.

### Processing Result

```text
ProcessDocumentAlignmentWorkflowResult(
    outcome,
    workflow_run_uid,
    job_uid,
    run_status,
    run_stage,
    total_items,
    ready_for_review_items,
    blocked_items,
    failed_items,
    warning_count,
    retryable,
    error_code,
    error_message,
)
```

Allowed outcomes are `completed`, `completed_with_warnings`, `blocked`,
`failed`, `already_terminal`, `claim_conflict`, `invalid_job`,
`invalid_run_state`, and `retryable_failure`. The result contains no ORM
object, HTTP status, Flask response, database integer ID, raw exception,
traceback, evidence body, prompt, provider output, or credential.

### Processing Dependencies

A flat service locator is rejected. The future frozen dependency contract is
grouped into these stage collaborators:

- `ItemBootstrapCollaborator`: governed source loader, chunk loader, term
  extractor, canonicalizer, item repository and bootstrap transaction;
- `EvidenceAndCandidateCollaborator`: governed bilingual evidence retrieval
  and formal-only Chinese candidate generation;
- `DraftAndVerificationCollaborator`: approved-card protection, draft reuse,
  provider policy, preflight, formal verification, usage and attach adapter;
- `WorkflowFinalizationCollaborator`: root/item repository, BackgroundJob
  finalizer, safe audit recorder and current-time factory.

The processing service also receives a claim collaborator that returns an
attempt-scoped claim. No collaborator may expose Flask, `backend.app`, route
registries, the complete model registry, environment mappings, credentials,
provider transports, legacy alignment helpers, or frontend configuration.

### BackgroundJob Claim And Lease

| Capability | Current implementation | Required for formal workflow | Gap |
|---|---:|---:|---|
| queued/running/completed/failed/retrying | yes | yes | none |
| worker ID and locked timestamp | yes | yes | fields exist |
| attempt and max attempts | yes; default maximum is 3 | yes | none |
| job type and minimal payload | yes | yes | formal type is not in worker dispatch |
| atomic claim | formal path uses conditional SQL UPDATE and requires rowcount 1 | yes | established for tested SQLite path |
| compare-and-set finalization | worker, attempt, token, status and expiry fence | yes | established for formal transport state |
| lease generation | unpredictable token plus monotonic execution attempt | yes | established |
| lease expiry | explicit UTC text deadline; expiry at `lease_expires_at <= now` | yes | established for single-node pilot |
| heartbeat | fenced renewal extends expiry by 30 seconds | required before long work | established |
| stale-running recovery | CAS replacement with new attempt/token | yes | established |
| formal job cancellation policy | generic cancel currently applies | explicit formal policy required | blocking contract |
| formal manual retry policy | generic failed-job retry currently applies | attempt-aware retry required | blocking contract |
| PostgreSQL locking behavior | unverified | required before production | deferred production validation |

The legacy queue remains query-first for legacy job types. Formal jobs use the
dedicated ownership service and are excluded from generic claim/dispatch. Real
file-backed SQLite tests synchronize two sessions after candidate discovery and
repeat queued claim races 20 times with exactly one winner. PostgreSQL and
distributed clock semantics remain unverified. BackgroundJob remains
transport-only; its status never replaces workflow root status.
Legacy job execution still retains its historical single worker operational
assumption; the formal CAS contract does not retroactively harden legacy jobs.

### Root State Machine

`ready_for_review`, `completed_with_warnings`, `blocked`, and `failed` are
terminal for processing V1. No V1 API reopens a terminal root. A retryable
worker failure leaves the root in `validating` or `processing` while the job is
requeued; `failed` is written only after the retry budget is exhausted or a
non-retryable system failure occurs.

| From | To | Trigger | Persistence owner | Audit event |
|---|---|---|---|---|
| `queued` | `validating` | atomic job claim succeeds | claim/root transaction | `document_alignment_started` |
| `validating` | `processing` | source snapshot and bootstrap succeed | bootstrap transaction | `document_alignment_items_created` |
| `validating` | `blocked` | source changed, parse blocked, no candidates, or item limit exceeded | bootstrap/finalization transaction | `document_alignment_blocked` |
| `validating` | `failed` | non-recoverable persistence failure | finalization transaction | `document_alignment_failed` |
| `processing` | `ready_for_review` | at least one needs-review item and no blocked/failed item | finalization transaction | `document_alignment_ready_for_review` |
| `processing` | `completed_with_warnings` | at least one needs-review item plus blocked/failed items | finalization transaction | `document_alignment_completed_with_warnings` |
| `processing` | `blocked` | all items are domain-blocked | finalization transaction | `document_alignment_blocked` |
| `processing` | `failed` | all items fail or retry budget ends on systemic failure | finalization transaction | `document_alignment_failed` |

Canonical notation: queued -> validating, validating -> processing,
processing -> ready_for_review, and processing -> completed_with_warnings.
Illegal transitions return `DOCUMENT_ALIGNMENT_INVALID_RUN_STATE` without
provider execution. A repeated worker on a terminal root returns
`already_terminal` and performs no writes, usage, or duplicate terminal audit.

### Item State Machine

| From | To | Trigger | Stage after transition |
|---|---|---|---|
| none | `candidate` | deterministic bootstrap | `candidate` |
| `candidate` | `evidence_ready` | governed bilingual evidence gate passes | `draft_creation` |
| `evidence_ready` | `draft_created` | safe draft created or reused | `verification` |
| `draft_created` | `verification_completed` | formal run persisted and parsed | `verification` |
| `verification_completed` | `needs_review` | attach allowed or safely recorded as reviewable | `terminal` |
| any nonterminal | `blocked` | domain, policy, evidence, approved-card, or attach gate | `terminal` |
| any nonterminal | `failed` | exhausted retryable infrastructure, parser, or persistence failure | `terminal` |

Canonical notation: candidate -> evidence_ready, evidence_ready -> draft_created,
draft_created -> verification_completed, and verification_completed -> needs_review.
No item becomes approved, published,
or student-visible.

### Candidate Contract And Chunk Scope

The future frozen candidate DTO is:

```text
DocumentAlignmentTermCandidate(
    candidate_term: str,
    normalized_term: str,
    source_chunk_ids: tuple[str, ...],
    source_scope_summary: str,
    extraction_score: float | None,
    extraction_source: str,
)
```

The current extractor is a text-level legacy helper. It accepts one text value
and returns no chunk UID or normalized term, so it is not a direct formal
processing collaborator. The future bootstrap adapter calls deterministic
extraction per governed KnowledgeChunk, then applies Unicode NFKC, outer trim,
internal whitespace collapse, and casefold to the normalized term. Display
text is retained separately.

Candidates without a governed chunk UID are rejected. Duplicate occurrences
of one normalized term are one V1 item: their chunk UIDs are unioned, deduped,
and sorted before `item-key-v1` is generated. V1 does not create multiple items
for the same normalized term in different contexts; it records
`multi_context_term_scope` when multiple chunks contribute. This explicit
pilot limitation avoids unstable context clustering.

Ordering is deterministic: descending extraction score, then normalized term,
then the sorted chunk UID tuple. Empty terms, terms longer than 220 characters,
and empty chunk scopes are rejected. At most 20 chunk references may scope one
candidate. More references are reduced deterministically to the first 20 by
chunk UID and add `candidate_chunk_scope_truncated`.

V1 accepts at most 50 canonical candidates. More than 50 blocks bootstrap with
`DOCUMENT_ALIGNMENT_ITEM_LIMIT_EXCEEDED`; it does not silently truncate and
does not invoke provider execution. Zero candidates blocks the root with
`DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES`. Term extraction exceptions are
retryable only when caused by infrastructure or database access; invalid or
empty extraction output is non-retryable.

### WorkflowItem Bootstrap

Bootstrap verifies that every source chunk belongs to the admitted
`source_uid`, matches the frozen `parse_uid` and source version, and remains
visible to the requesting course scope. The future service builds
`item-key-v1` from normalized term and sorted scoped chunk IDs. It then creates
or reuses by `(workflow_run_id, item_key)`.

One short bootstrap transaction creates missing items, updates
`total_items`, and changes validating -> processing. Existing items are
reused. A repeated bootstrap with the same canonical set is a no-op. A source
version change or a candidate set that disagrees with already persisted items
blocks the root with `DOCUMENT_ALIGNMENT_SOURCE_CHANGED`; persisted items are
retained for audit. Item creation failure rolls back the bootstrap transaction
and is retryable as `DOCUMENT_ALIGNMENT_ITEM_PERSISTENCE_FAILED` until the job
attempt budget is exhausted. One aggregate `document_alignment_items_created`
audit is written; item creation does not emit one audit per row.

### Approved Card Protection And Duplicate Drafts

An existing approved ConceptAlignmentCard is never overwritten, downgraded,
or re-verified automatically. The item records the existing formal card UID,
becomes non-retryable `blocked` with
`DOCUMENT_ALIGNMENT_APPROVED_CARD_PROTECTED`, creates no draft or verification
run, and produces no provider usage. Teacher review and existing student
visibility remain unchanged.

An exact existing `draft` or `needs_review` card matching English term,
Chinese term, course, chapter, and retrieval version is reused. Different
evidence scope does not overwrite the old draft; the future collaborator must
return `DOCUMENT_ALIGNMENT_DRAFT_CONFLICT` until a revision policy exists.
`force_create` is prohibited in formal processing. Reuse stores the existing
card UID on the WorkflowItem. A persisted item verification UID is reused; an
unlinked verification run is not guessed by latest-row order.

### Governed Evidence Policy

Evidence retrieval uses only active governed KnowledgeSource and
KnowledgeChunk records allowed by course permission, chapter scope,
visibility, trust level, parse status, and quality gates. English evidence
comes from English course material or governed bilingual references. Chinese
evidence comes from governed Chinese reference material or governed bilingual
references. Cross-course, private, low-quality, blocked, or client-supplied
chunks are excluded.

The V1 provider gate requires at least one English and one Chinese evidence
candidate, with each top lexical score at least `0.35`. Missing one side or a
score below the threshold blocks the item with
`DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT`; provider policy, preflight, and
provider execution are not called. Evidence is deduped by evidence UID/chunk
UID and ranked by existing retrieval score. WorkflowItem stores reference IDs,
counts, retrieval version, and risk summary only. It never stores complete
evidence bodies, source documents, client evidence, prompts, or credentials.

### Chinese Candidate Policy

Allowed sources are existing formal ConceptAlignmentCards, governed bilingual
chunks, and deterministic rules already present in the formal candidate
service. The formal caller passes `term_model=None` and
`terminology_card_model=None`, which disables legacy Term and TerminologyCard
candidate paths. External translation and client-trusted candidates are
prohibited.

Candidates retain safe provenance, score, source/card/chunk references, and
risk labels. They are sorted by score and deterministic candidate UID. The top
candidate is selected only after the governed evidence gate; ambiguity is
preserved as a risk. No candidate blocks the item with
`DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE`; no draft or provider run
is created. Multiple candidates are stored as a bounded safe summary, not full
snippets. Formal processing does not create a draft without a Chinese
candidate.

### Card Draft Policy

The draft collaborator consumes the English display term, selected Chinese
candidate summary, English/Chinese evidence references, course, chapter,
concept scope, risk labels, source UID, chunk UIDs, retrieval version, workflow
run UID, and item UID. The current card model has no workflow foreign key, so
workflow UIDs belong in safe audit context and WorkflowItem references rather
than an invented card field.

Every created card is `needs_review`; approved, published, and student-visible
requests are rejected. The formal collaborator must call the existing draft
service with legacy candidate models disabled and transaction ownership made
explicit. The current service's exception path rolls back and can commit a
failure audit, so the processing orchestrator must not call it directly until
a transaction adapter defines failure behavior.

### Formal Verification Policy

The only allowed sequence is provider governance -> provider policy -> formal
provider preflight -> formal verification -> formal parser -> formal attach
gate. The workflow default provider is deterministic `mock-rule-v1`; fake and
replay providers are permitted only when policy and preflight allow them.
External/live provider remains disabled by default and is not enabled by this
design. New formal Runs freeze `mock-rule-v1`, `mock-rule-v1:v1`, and
`alignment-v1` during admission; preparation cannot substitute another
identity when those fields are absent.

The current alignment verification execution service evaluates provider
policy but does not call `run_provider_preflight`; the processing collaborator
must add preflight explicitly. It must not use the legacy urllib path, legacy
provider helpers, or arbitrary provider URLs. Policy/preflight/evidence blocks
create no actual provider usage. Verification always keeps
`can_auto_approve=false`; attach only adds safe verification risk labels and
keeps a draft in `needs_review`.

### Transaction Matrix

| Operation | Current service | Current commit owner | Desired processing boundary |
|---|---|---|---|
| worker claim | `claim_next_background_job` | generic worker | atomic claim transaction with attempt-scoped lease |
| run start | no processing service | none | same short transaction as valid claim |
| item bootstrap | no service | none | one bootstrap transaction |
| evidence retrieval | evidence and bilingual services | no commit | read phase outside a long write transaction |
| candidate generation | Chinese candidate service | no commit | read phase outside a long write transaction |
| card draft | draft service | service by default | short per-item adapter transaction; no hidden failure-audit commit |
| provider policy | governance service | no commit | read decision before provider execution |
| preflight | preflight service | service by default | short explicit preflight transaction with `commit=False` composition |
| verification request audit | verification execution service | immediate internal commit | future adapter must make event idempotent and separate from compute |
| provider execution | verification core | provider call occurs before run persistence | no workflow-level transaction while waiting on provider |
| verification persistence | verification core/execution service | execution service | short idempotent per-item persistence transaction |
| provider usage | governance usage recorder | helper by default | same persistence transaction as unique provider attempt |
| attach | verification attach helper | helper by default | same per-item persistence transaction after attach gate |
| item update | no service | none | same per-item persistence transaction as references |
| root finalization | no service | none | one aggregate finalization transaction |
| job finalization | generic worker | generic worker | same attempt-checked finalization transaction or a compensating transport update |
| root audit | no service | none | idempotent transition/terminal audit in finalization transaction |

The intended phases are claim, read/compute, bootstrap, per-item compute,
per-item persistence, and finalization. No database transaction is held around
whole-document work or an external provider call. Existing commit flags make
lower-level composition possible, but `execute_alignment_verification` and
the draft failure path are not transaction-neutral. After claim/lease is
fixed, a dedicated verification/draft transaction adapter remains required
before provider-backed processing can be implemented.

### Partial Failure And Finalization

Item failure never rolls back already committed successful items. Valid drafts
and verification runs remain. Failed or blocked items keep only safe errors and
references. Root counts are recomputed from persisted items, not incremented
blindly, so repeated finalization is idempotent.

- `total_items == 0`: root `blocked` with
  `DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES`;
- all items blocked by domain gates: root `blocked`;
- one or more `needs_review` and no blocked/failed items: root
  `ready_for_review`;
- one or more `needs_review` plus blocked/failed items: root
  `completed_with_warnings`;
- all items failed after retry budgets are exhausted: root `failed`;
- systemic database, worker ownership, or finalization failure: root `failed`
  only after safe retries are exhausted.

No partial outcome approves a card, deletes a draft, or hides prior successful
work.

### Retry, Resume, And Repeated Execution

New formal jobs freeze `max_attempts=3`, meaning three counted
processing-failure outcomes and at most two successful requeues. The
authoritative constants are `FORMAL_DOCUMENT_ALIGNMENT_MAX_ATTEMPTS_V1` and
`FORMAL_DOCUMENT_ALIGNMENT_MAX_REQUEUES_V1`.
V1 exposes no item or root retry API. Generic cancel/retry endpoints must not
mutate a formal job until the claim task defines formal cancellation and retry
rules.

`execution_attempt` identifies lease ownership generations and increments on
queued/retrying claim or stale-running reclaim. Heartbeat and requeue do not
change it. `attempt_count` starts at zero; claim, heartbeat, stale reclaim, and
completion do not consume it. Requeue consumes one count, and
retry-exhausted/permanent failure consumes the final count. Historical jobs
retain their stored budget; Admission replay never overwrites policy or
counters.

If a claim or stale reclaim crashes or loses ownership before returning a typed
processing outcome, it does not consume `attempt_count`. Therefore
`execution_attempt` may exceed `max_attempts`, and V1 does not persist a
separate crash/reclaim-generation cap. This is an explicit single-node pilot
limitation, not a bounded total-execution guarantee.

- a `needs_review item` is terminal and is never reprocessed;
- a `blocked non-retryable item` is terminal and is never reprocessed;
- a failed retryable item resumes from its last persisted stage;
- an `evidence_ready` item reuses evidence references if source/retrieval
  versions match, otherwise it restarts evidence retrieval;
- a `draft_created` item reuses its exact draft UID and does not create a new
  card;
- a `verification_completed item` reuses its verification run UID and never
  calls the provider again;
- a terminal root returns `already_terminal` without writes;
- root finalization is a count recomputation plus legal-state compare-and-set;
- stale workers may not persist after their attempt lease is superseded.

The current verification model has no workflow-item idempotency key. A crash
after provider persistence but before item linkage can cause a duplicate call
on retry. The later transaction adapter must persist a unique attempt mapping
before enabling any non-deterministic provider. Until then, deterministic
mock/fake/replay is the only safe processing target and processing remains
unimplemented.

### Audit Policy

Root-level events are:

- `document_alignment_started`;
- `document_alignment_items_created`;
- `document_alignment_ready_for_review`;
- `document_alignment_completed_with_warnings`;
- `document_alignment_blocked`;
- `document_alignment_failed`.

`document_alignment_requested` remains admission-owned. Transition audits are
written only when a compare-and-set changes state, so repeated workers do not
duplicate `started` or terminal events. One aggregate retry audit may be
written per job attempt; item-level audit is not added because draft,
preflight, verification, usage, and attach components already record bounded
formal events. Summary fields are limited to run/job/source UID, course,
workflow/provider/model/prompt versions, counts, risk summary, and safe errors.
Chunks, evidence bodies, prompts, raw output, credentials, Authorization,
Cookie, and traceback are prohibited.

### Usage Policy

Local term extraction, evidence retrieval, Chinese candidate generation,
policy blocks, preflight blocks, and insufficient evidence produce zero usage.
Only an actual provider execution creates a formal
AlignmentProviderUsageRecord. The unique provider-attempt mapping required by
the later transaction adapter prevents repeated usage for one call. The root
stores aggregate counts only and never copies provider usage details. Formal
processing never writes legacy UsageRecord or AICallLog.

### No Dual Write

| Processing stage | Formal tables written | Legacy tables written |
|---|---|---|
| admission | DocumentAlignmentWorkflowRun, BackgroundJob, AuditRecord | none |
| claim | BackgroundJob, BackgroundJobEvent, DocumentAlignmentWorkflowRun, AuditRecord | none |
| bootstrap | DocumentAlignmentWorkflowItem, DocumentAlignmentWorkflowRun, BackgroundJob lease heartbeat/expiry | none |
| evidence/candidates | none | none |
| draft | ConceptAlignmentCard, AuditRecord, WorkflowItem references | none |
| preflight | AlignmentProviderPreflightRun, AuditRecord | none |
| verification/attach | AlignmentVerificationRun, AlignmentProviderUsageRecord, ConceptAlignmentCard risk/review fields, AuditRecord, WorkflowItem references | none |
| finalization | DocumentAlignmentWorkflowRun, BackgroundJob, BackgroundJobEvent, AuditRecord | none |

Legacy `/api/alignment/run` remains separate and does not write formal workflow
roots/items or the formal workflow job type. Any future formal/legacy dual
write is `FORMAL_LEGACY_DUAL_WRITE_DETECTED` and blocks implementation.

### Safe Error Taxonomy

All messages are bounded safe summaries. Client-visible means future teacher or
admin workflow query, not student access. Usage means formal provider usage.

| Code | Scope | Retryable | Terminal | Client-visible | Usage | Draft | Verification run |
|---|---|---:|---:|---:|---:|---:|---:|
| `DOCUMENT_ALIGNMENT_RUN_NOT_FOUND` | root | no | yes | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_JOB_NOT_FOUND` | root | no | yes | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_JOB_MISMATCH` | root | no | yes | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_WORKFLOW_VERSION_MISMATCH` | root | no | yes | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_INVALID_RUN_STATE` | root | no | current state unchanged | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_WORKER_CLAIM_CONFLICT` | root | yes | no | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_SOURCE_CHANGED` | root | no | blocked | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_PARSE_BLOCKED` | root | no | blocked | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES` | root | no | blocked | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_ITEM_LIMIT_EXCEEDED` | root | no | blocked | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED` | root | yes until attempts exhausted | failed when exhausted | yes | no | possible prior | possible prior |
| `DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED` | root | yes until attempts exhausted | failed when exhausted | yes | no duplicate | possible prior | possible prior |
| `DOCUMENT_ALIGNMENT_CHUNK_NOT_AVAILABLE` | item | no if source changed | blocked | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT` | item | no | blocked | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE` | item | no | blocked | yes | no | no | no |
| `DOCUMENT_ALIGNMENT_DRAFT_CONFLICT` | item | no | blocked | yes | no | no new | no |
| `DOCUMENT_ALIGNMENT_APPROVED_CARD_PROTECTED` | item | no | blocked | yes | no | no new | no |
| `DOCUMENT_ALIGNMENT_PROVIDER_POLICY_BLOCKED` | item | no | blocked | yes | no | existing draft possible | no provider run |
| `DOCUMENT_ALIGNMENT_PROVIDER_PREFLIGHT_BLOCKED` | item | no | blocked | yes | no | existing draft possible | no provider run |
| `DOCUMENT_ALIGNMENT_VERIFICATION_FAILED` | item | yes for infrastructure only | failed when exhausted | yes | only if provider was called | yes | possible |
| `DOCUMENT_ALIGNMENT_VERIFICATION_PARSE_FAILED` | item | no for same output | failed | yes | yes for actual call | yes | failed run |
| `DOCUMENT_ALIGNMENT_ATTACH_BLOCKED` | item | no | blocked | yes | actual call only | yes | yes |
| `DOCUMENT_ALIGNMENT_ITEM_PERSISTENCE_FAILED` | item | yes until attempts exhausted | failed when exhausted | yes | no duplicate | possible prior | possible prior |

No result returns a raw exception, traceback, prompt, evidence body, provider
output, credential, or URL query secret.

### Worker Handler Boundary

The future formal worker handler may only validate the job type, parse the two
minimal payload keys, obtain an attempt-scoped claim, construct
`ProcessDocumentAlignmentWorkflowCommand`, call the processing orchestrator,
map the typed result to transport status, record a safe worker error, and honor
retryability. It must not query chunks, extract terms, retrieve evidence,
create cards, invoke providers, run verification, calculate root counts, write
WorkflowItems, or touch legacy records directly.

### Read And Query Boundary

The future run query returns run UID, safe source summary, course/chapter,
status, stage, progress counts, safe error, created/started/finished times, and
request trace summary. Job status may be exposed only as transport diagnostics;
`BackgroundJob is not business status truth`.

The item query requires course permission, uses pagination and stable ordering
by item ID/item UID, and returns item UID, display term, status, risk/confidence
summary, draft card UID, verification run UID, safe error, and timestamps. It
never returns prompts, raw output, evidence bodies, credentials, or drafts to
students. Frontend polling targets WorkflowRun status, not BackgroundJob.

### Unique Processing Conclusion And Next Task

Historical 9C.4Y conclusion: `WORKER_CLAIM_AND_LEASE_CONTRACT_REQUIRED_FIRST`.

Task 9C.4Z conclusion:
`FORMAL_JOB_EXECUTION_OWNERSHIP_ESTABLISHED_FOR_LOCAL_PILOT`.

Task 9C.5A establishes the governed chunk-scoped candidate contract and
attempt-fenced, idempotent WorkflowItem bootstrap:

```text
FORMAL_CHUNK_SCOPED_ITEM_BOOTSTRAP_ESTABLISHED
```

The processing orchestrator still cannot be implemented directly. The next
task must establish transaction-neutral draft/preflight/verification/attach
composition before provider-backed orchestration.

## Task 9C.4Z Formal Job Ownership Update

The implemented contract is documented in
`docs/formal_background_job_execution_ownership.md`. It provides
`FORMAL_BACKGROUND_JOB_EXECUTION_OWNERSHIP_ESTABLISHED_FOR_LOCAL_PILOT`,
`AT_LEAST_ONCE_TRANSPORT`, and `ATTEMPT_FENCED_OWNERSHIP` with
`FORMAL_JOB_DEFAULT_LEASE_SECONDS = 30`. Expiry uses
`lease_expires_at <= now`. The clock policy remains
`SINGLE_NODE_CLOCK_TRUSTED_FOR_PILOT` and
`DATABASE_TIME_REQUIRED_FOR_DISTRIBUTED_PRODUCTION`.

`CANCELLATION_OUT_OF_SCOPE_FOR_9C4Z`. The additive schema remains
`PILOT_CREATE_ALL_ONLY`; `FORMAL_MIGRATION_REQUIRED_BEFORE_PRODUCTION` and
`POSTGRESQL_LEASE_SEMANTICS_NOT_VERIFIED` remain explicit conditions.

## Task 9C.5A Chunk-Scoped Candidate And Item Bootstrap

### Candidate Contract

`backend/services/document_alignment_term_candidates.py` is a pure module with
frozen governed-chunk, canonical-candidate, and extraction-result DTOs. Its
fixed version is `formal-chunk-term-extraction-v1`. It calls the injected
deterministic extractor once per chunk in stable `(chunk_index, chunk_uid)`
order and never concatenates a whole document.

Normalization is Unicode NFKC, trim, whitespace collapse, and casefold for
identity while retaining the earliest stable display form. Equal normalized
terms aggregate unique sorted chunk refs, occurrence count, and earliest chunk
index. Non-contiguous indexes add `MULTI_CONTEXT_TERM_CANDIDATE`. Semantic
sense clustering is not implemented. V1 limits are 50 canonical items and 100
unique chunk refs per candidate; excess returns an explicit error with no
silent truncation and no item writes.

### Bootstrap And Transaction Fence

`bootstrap_document_alignment_workflow_items(command, dependencies)` uses
frozen typed DTOs. The command contains only workflow/job/worker/attempt/token
identity, with the token excluded from repr. Dependencies are explicit and do
not include Flask, routes, provider, evidence, card, verification, worker
dispatch, or legacy services.

The read/compute phase loads root/source/chunks, captures source, parse,
version, and chunk membership signatures, rolls back the read transaction, and
computes candidates. The short persistence phase first calls
`fence_active_formal_job_lease_in_transaction`, a conditional UPDATE checking
job UID, formal type, running status, worker, attempt, opaque token, and
unexpired lease. It reloads root/source/chunks, rejects drift, creates or reuses
items, updates root status/counts, and commits once. Fence heartbeat/expiry and
all item/root writes use the same session, transaction, and commit.

Queued and validating roots can bootstrap. A processing root is reusable only
when its existing item count equals `total_items`; a missing or partial set is
invalid. Terminal roots are immutable. Success sets status `processing`, stage
`evidence_retrieval`, and `total_items` to the canonical count. No-candidate
and hard-limit results block the root under an active fence without items.
Extraction failures are retryable and roll back the fence, leaving root state
unchanged.

Every item uses existing `item-key-v1` and database uniqueness on
`(workflow_run_id, item_key)`. Repeated runs reuse field-identical items without
resetting downstream status or card/verification refs. Field conflict returns
`DOCUMENT_ALIGNMENT_ITEM_IDEMPOTENCY_CONFLICT`. Only the named item-key unique
conflict is eligible for rollback, fence reacquisition, and consistent-row
recovery; other integrity errors are persistence failures.

### Write Set And Proof Boundary

Bootstrap writes only WorkflowItem, WorkflowRun, and the formal BackgroundJob
lease heartbeat/expiry. It writes no card, verification, preflight, usage,
audit, or legacy record and performs no network call.
`BOOTSTRAP_AUDIT_DEFERRED_UNTIL_EVENT_IDEMPOTENCY_CONTRACT` is explicit.

SQLite integration uses two independent SQLAlchemy sessions/connections. Five
concurrent rounds each produced exactly one `created` and one `reused`, two
final items, no double winner, no `database locked`, and no rerun. A real stale
reclaim prevented the old attempt from writing items or root state. This is a
local-pilot transaction fence, not distributed exactly-once. PostgreSQL
locking, provider-call idempotency, and Usage/Audit event idempotency remain
unverified.

Unique conclusion:

```text
FORMAL_CHUNK_SCOPED_ITEM_BOOTSTRAP_ESTABLISHED
```

Historical next slice after Task 9C.5A:
`NEXT_FORMAL_VERIFICATION_TRANSACTION_ADAPTER` (completed by Task 9C.5B retry).

## Task 9C.5B.1 Formal Item Execution Identity Schema

Task 9C.5B stopped before implementation because WorkflowItem linkage and
random verification/preflight/usage/audit UIDs could not prevent duplicate
logical execution. Task 9C.5B.1 establishes the schema foundation documented
in `docs/formal_item_verification_execution_identity.md`:

- `DocumentAlignmentItemVerificationExecution` stores one logical execution
  mapping and safe recovery state;
- safe input fingerprints use only normalized values and governed references;
- `item-verification-execution-v1:<sha256>` identifies the stable combination
  of item input and provider/model/retrieval/prompt/parser/schema versions;
- verification, preflight, and provider usage records have nullable unique
  `execution_key` columns;
- AuditRecord has nullable unique `event_identity`;
- old rows remain null with no guessed backfill;
- named SQLite unique indexes enforce one winner for concurrent duplicate
  mapping insertion.

The mapping can represent preparation, draft, preflight, provider completion,
verification persistence, attach pending/completed, review, block, and failure
states. It stores no evidence body, prompt, raw provider output, credential,
lease token, worker, request ID, or arbitrary metadata.

This result is exactly:

```text
FORMAL_ITEM_EXECUTION_IDEMPOTENCY_SCHEMA_ESTABLISHED
```

It does not establish provider exactly-once, adapter behavior, or processing.
SQLite additive upgrade and concurrent uniqueness are tested; formal migration
and PostgreSQL constraint semantics remain unverified. The next permitted
slice is the retried Task 9C.5B transaction-neutral adapter.

## Task 9C.5B Formal Per-Item Verification Adapter

Task 9C.5B (retry) adds
`backend/services/document_alignment_item_verification_adapter.py`. Its frozen
command carries only run/item/job ownership plus a prepared, bounded in-memory
input. Its result exposes safe execution, item, draft, preflight, verification,
usage, audit, retry, confidence, recommendation, and error summaries without
ORM objects, evidence bodies, provider output, credentials, or lease tokens.

The adapter uses the existing execution fingerprint/key and event-identity
algorithms. Every business persistence checkpoint executes the active formal
job lease fence in the same short transaction. Draft creation and safe
verification persistence use internal transaction-neutral helpers; the public
draft and verification APIs retain their existing commit behavior.
The fence additionally verifies that the BackgroundJob payload names the same
workflow root/version and that persisted item key, term, selected candidate,
candidate provenance, and bilingual evidence references match the prepared
input. A valid lease for a different formal run cannot authorize item writes.
V1 deliberately accepts one selected Chinese candidate and one provenance
reference; it does not infer candidate-to-provenance pairing from independently
sorted collections.

The persisted lifecycle is:

```text
prepared -> draft_ready -> preflight_passed -> provider_started
-> provider_completed -> verification_persisted -> attach_pending
-> needs_review
```

Preflight block, policy block, parser/provider failure, stale attempts, lease
expiry, and persistence failure return typed safe outcomes. Approved cards are
referenced but never changed or reverified. Attach failure preserves a
`verification_completed` item and `attach_pending` execution so retry does not
invoke the provider again. Verification, preflight, usage, and audit records
reuse their database identities; the execution mapping remains the recovery
source of truth.
Attach performs an affected-row checked update constrained to non-approved
cards. Tests approve the card through an independent database connection while
the provider computes, then prove that the attach path returns blocked and
preserves every approved-card field.

Provider input may include bounded governed snippets in memory. Persistence is
limited to evidence reference IDs/counts, fingerprints, versions, parsed safe
fields, and bounded safe errors. No legacy AlignmentRun, TerminologyCard,
UsageRecord, or AICallLog is written. No card is auto-approved or made student
visible.

The guarantee remains `AT_LEAST_ONCE_TRANSPORT`. A deterministic provider may
be invoked again after a crash at `provider_started`, but database uniqueness
keeps one logical verification, preflight, usage, and audit event per execution
identity. External/live/custom providers are prohibited, so this does not claim
provider exactly-once or solve external billing ambiguity. SQLite concurrent
sessions are tested; PostgreSQL and formal migrations remain unverified.

Current status:

```text
FORMAL_ITEM_VERIFICATION_TRANSACTION_ADAPTER_ESTABLISHED
FORMAL_DOCUMENT_ALIGNMENT_PROCESSING_ORCHESTRATOR_ESTABLISHED
FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_ESTABLISHED
FORMAL_WORKFLOW_QUERY_SERVICES_ESTABLISHED
FORMAL_DOCUMENT_ALIGNMENT_ROUTES_AND_OPENAPI_ESTABLISHED
FORMAL_DOCUMENT_ALIGNMENT_API_END_TO_END_VERIFIED
FRONTEND_NOT_MIGRATED
```

## Task 9C.5C Formal Processing Orchestrator

Task 9C.5C adds `document_alignment_item_preparation.py` and
`document_alignment_processing_orchestrator.py`. Preparation composes the
existing governed Chinese-candidate and bilingual-evidence services, selects
one candidate with deterministic score/UID/value ordering, constrains English
evidence to the item's governed source chunks, and keeps bounded snippets in
memory. The persisted checkpoint contains only evidence reference IDs, one
candidate/provenance summary, risk labels, and state.

The orchestrator accepts a frozen command containing run/job/worker/attempt and
a repr-hidden lease token. It validates the formal BackgroundJob payload,
heartbeats synchronously at every specified boundary, invokes the existing
item bootstrap, iterates by database ID plus item key, and invokes only the
9C.5B adapter for draft, policy, preflight, provider, verification, usage,
audit, and attach. It never completes, fails, or requeues BackgroundJob.

Business blocks are persisted per item and later items continue. Infrastructure
errors, unavailable chunks, retryable adapter outcomes, stale attempts, and
expired leases stop the invocation without root terminalization. Source
identity/version drift preserves completed items and atomically blocks all
unstarted candidates while the lease is active. Counts are always recomputed
from database item states. V1 warning count is the number of needs-review items
with nonempty risk labels plus blocked items plus failed items.

Root terminal rules are: all needs-review -> `ready_for_review`; mixed
needs-review and blocked/failed -> `completed_with_warnings`; all blocked ->
`blocked`; no needs-review with any failed -> `failed`. Nonterminal items keep
the root processing. Terminal audits use a stable event identity derived only
from run UID, workflow version, and event type.

Repeated invocation skips terminal items, reconstructs bounded in-memory input
for resumable item states, reuses per-item execution identities, and rebuilds
root counts. Five two-session SQLite duplicate-invocation rounds converged
without duplicate item, draft, preflight, verification, usage, or audit rows.
This is a defensive idempotency result, not permission for parallel item
processing and not PostgreSQL proof. The declared policy remains
`SINGLE_SEQUENTIAL_ORCHESTRATOR_PER_LEASE` and provider execution remains
at-least-once for deterministic providers.

## Task 9C.5D Formal Worker Handler

Task 9C.5D adds `document_alignment_processing_composition.py`,
`document_alignment_worker_handler.py`, and
`formal_background_job_dispatch.py`. The formal dispatcher uses the existing
CAS ownership service and never calls the generic claim. The handler validates
the exact two-field job payload, builds the established processing command,
invokes the orchestrator once, reloads root state, and maps typed outcomes to
attempt-fenced complete, requeue, or fail operations.

Claim/reclaim advances only `execution_attempt`. Requeue and permanent fail
consume `attempt_count` once. Retry exhaustion first invokes the lease-fenced
root failure finalizer, then fails the job. A reclaimed attempt recognizes a
root already failed by retry exhaustion and completes the pending job failure
rather than incorrectly marking the transport completed.

The worker requeue allowlist is outcome-based: only
`retryable_interruption` and `persistence_error` qualify. Ownership loss,
lease expiry, invalid state, terminal state, business blocks, and unknown
outcomes cannot become requeueable through a standalone boolean flag. Unknown
outcomes instead follow the permanent fail-closed path, with Root finalization
persisted before BackgroundJob failure.

The local worker script alternates first opportunity between formal and legacy
dispatch while processing at most one job per iteration. This is local pilot
fairness, not a durable scheduler or production daemon. Formal/legacy
dispatch isolation, approved-card immutability, no dual write, no network,
ten dispatcher claim races, and crash/requeue recovery are covered by worker
tests. PostgreSQL worker semantics remain unverified.

Next permitted slice: `Task 9C.5H: Formal Workflow Frontend Cutover and Legacy-Independent Teacher Experience`.
