# ADR: Legacy Alignment Run Deprecation Policy

Status: ACCEPTED_FOR_SMALL_PILOT

Date: 2026-07-17

Policy name: LEGACY_ALIGNMENT_RUN_DEPRECATION_V1

Endpoint role: TEMPORARY_FRONTEND_COMPATIBILITY_ONLY

## Context

Task 9C.4S characterized `POST /api/alignment/run` and concluded
`DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`.

The endpoint remains active because `frontend/index.html` still calls it from
`runAlignmentForDocument(...)` for the document alignment button. It is not an
alias for the formal `POST /api/alignment/verify` route.

The legacy route currently:

- writes `AlignmentRun`;
- writes `BackgroundJob`;
- writes `TerminologyCard`;
- can write legacy `UsageRecord`;
- can write `AICallLog`;
- bypasses formal provider policy;
- bypasses formal provider preflight;
- bypasses the formal output parser;
- bypasses the formal attach gate;
- does not attach formal `request_id`;
- does not create formal `AuditRecord`;
- can reach legacy `urllib` transport intent when a live default provider has a usable credential.

The route cannot be deleted immediately because the frontend still depends on
it. It also cannot be moved unchanged into an application service because that
would preserve a weaker duplicate execution path beside the governed formal
verification workflow.

## Decision

`POST /api/alignment/run` is a temporary frontend compatibility endpoint for
the small pilot only. It is not a public execution API, must not receive new
client integrations, must not grow new provider or business capabilities, and
must eventually be disabled and removed.

The approved policy is:

- Policy: `LEGACY_ALIGNMENT_RUN_DEPRECATION_V1`.
- Status: `ACCEPTED_FOR_SMALL_PILOT`.
- Current endpoint role: `TEMPORARY_FRONTEND_COMPATIBILITY_ONLY`.
- External execution: `LEGACY_EXTERNAL_EXECUTION_PROHIBITED`.
- Transitional execution modes: `LOCAL_OR_DETERMINISTIC_ONLY`.
- Replacement architecture: `FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`.
- Direct alias to `/api/alignment/verify`: `PROHIBITED`.
- Dual write: `NO_LEGACY_AND_FORMAL_DUAL_WRITE`.
- Legacy records after cutover: `RETAIN_READ_ONLY_AFTER_CUTOVER`.
- Frontend migration: `REPLACEMENT_FIRST_THEN_CUTOVER`.
- Disable response after zero callers: HTTP 410 with `LEGACY_ALIGNMENT_RUN_DEPRECATED`.
- Final removal: after a disabled checkpoint and zero new legacy writes.

This is not production-ready provider execution policy.

## Current Legacy Risks

The current endpoint is risk-bearing because it blends HTTP compatibility,
document-level orchestration, provider execution, parser fallback, card
mutation, background job creation, usage writes, and transaction ownership in a
legacy handler and helper chain.

Specific risks:

- a live default legacy provider with a usable key can enter the legacy
  OpenAI-compatible `urllib` transport path;
- formal provider policy is not invoked;
- formal provider preflight is not invoked;
- formal output parsing/schema is not used;
- formal provider usage records are not written;
- formal request/completion/failed audit records are not written;
- formal attach gates are not used;
- success and error responses do not use the formal `request_id` contract;
- legacy and formal data models are split.

## Endpoint Lifecycle

### PHASE_0_CURRENT_AUDITED_STATE

The endpoint and frontend caller exist. Task 9C.4S is the audit baseline. The
legacy live transport risk is known. New callers are not allowed.

### PHASE_1_EXTERNAL_EXECUTION_CONTAINMENT

Keep the endpoint and existing frontend contract, but block legacy external
execution. The route must not read or pass real credentials into legacy
execution, must not enter `urllib` transport, and must return a stable safe
blocked result for prohibited live/external execution. This phase must not
rewrite the whole route or extract the old execution chain as a service.

### PHASE_2_REPLACEMENT_WORKFLOW

Build a new formal document alignment workflow. It must be document-level
orchestration, not a transparent call to `/api/alignment/verify`. It must use
formal governance components and must not dual-write legacy and formal tables
from one request.

### PHASE_3_FRONTEND_CUTOVER

Move the frontend to the replacement workflow after backend contract tests and
replacement E2E exist. Prove the legacy caller count is zero with static
reference scanning and dynamic E2E/no-call verification.

### PHASE_4_DISABLE_LEGACY_ENDPOINT

After all callers are gone, return a stable disabled/deprecated response. The
recommended response is HTTP 410 with `LEGACY_ALIGNMENT_RUN_DEPRECATED`. The
endpoint must not create `AlignmentRun`, `BackgroundJob`, `TerminologyCard`,
`UsageRecord`, `AICallLog`, or any formal verification records.

### PHASE_5_REMOVE_DEAD_PATH

Remove the old handler, unused helpers, and old transport branches after the
disabled checkpoint. Update OpenAPI, frontend references, docs, and tests.
Historical database records remain unless a separate data migration task
archives or maps them.

## External Provider Containment

Policy: `LEGACY_EXTERNAL_EXECUTION_PROHIBITED`.

Legacy `/api/alignment/run` must not continue to call live/external providers,
must not use legacy `urllib` transport, must not pass real credentials to
legacy execution, and must not regain the old live provider path. Formal
external provider support, if later needed, must be designed in the replacement
workflow with explicit provider policy, preflight, redaction, timeout, usage,
and audit behavior.

The next production-code task after this ADR must be the security containment
task for legacy external execution.

Implementation status after Task 9C.4U:

- `PHASE_1_EXTERNAL_EXECUTION_CONTAINMENT_COMPLETE` for all currently reachable
  legacy execution entries.
- `POST /api/alignment/run` keeps its frontend compatibility contract but
  returns `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` for external/live
  intent before creating run/job/card records.
- `process_alignment_job(...)` has an independent worker gate and terminates
  external/live legacy jobs with `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED`
  before provider execution.
- `/api/jobs/<id>/retry` refuses to requeue a quarantined external legacy
  alignment job.
- Direct legacy alignment helpers fail closed for external/live default
  provider configuration.
- The deprecated endpoint is not HTTP 410 yet because current frontend callers
  still exist.
- The replacement workflow, frontend cutover, disabled endpoint response, and
  dead-path removal remain future phases.

## Transitional Provider Modes

During the compatibility period, only local or deterministic behavior may
remain:

- `none` or disabled provider: allowed to return a local blocked or local-only result;
- local heuristic: allowed for compatibility, with no auto approval;
- mock/fake/replay modes: allowed only where they are actually supported by the
  existing path and remain fully no-network;
- external/live modes: prohibited.

Every transitional mode must be no-network, must not read or pass raw
credentials, must not auto approve, must not bypass teacher review, and must be
limited to the controlled small pilot.

## Replacement Architecture

Replacement architecture: `FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`.

The replacement is a document-level workflow:

```text
document input
-> parse record
-> parse quality gate
-> term extraction
-> bilingual evidence retrieval
-> Chinese candidate generation
-> ConceptAlignmentCard draft
-> formal provider policy
-> formal provider preflight
-> formal alignment verification
-> teacher review
-> student-visible approved card
```

`/api/alignment/verify` remains an important controlled verification step, but
it is not the document workflow itself.

The replacement workflow must track evidence, risk, confidence, provider
results, and review status for each concept/term. It must not auto approve
cards from provider output.

## Why Formal Verify Is Not A Direct Replacement

`POST /api/alignment/verify` verifies one structured request and writes formal
verification data. Legacy `POST /api/alignment/run` accepts document-level
requests, can create background jobs, extracts terms, mutates legacy
`TerminologyCard`, and returns three different response shapes.

Therefore:

- `/api/alignment/run -> /api/alignment/verify` is prohibited as a transparent alias;
- the old `run_alignment` endpoint name must not be reused for the replacement;
- `/api/alignment/verify` must not be expanded into a document orchestration API
  without a separate route contract task.

## Data Ownership

Legacy endpoint data ownership remains separate from the formal workflow:

- legacy endpoint: `AlignmentRun`, `BackgroundJob`, `TerminologyCard`, legacy
  `UsageRecord`, and `AICallLog`;
- formal workflow: formal run/usage/audit/draft objects to be defined in the
  replacement contract.

The legacy endpoint must not be represented as a formal verification record.

## No-dual-write Policy

Policy: `NO_LEGACY_AND_FORMAL_DUAL_WRITE`.

One request must not write both legacy and formal run models. One request must
not create both legacy `TerminologyCard` and formal `ConceptAlignmentCard`.
Implicit dual-write is prohibited even if it appears convenient for migration.

Data migration, archival, or mapping must be a separate explicit task with its
own tests and rollback plan.

## Legacy Data Retention

Existing legacy records remain after frontend cutover:

- `AlignmentRun`;
- `BackgroundJob`;
- `TerminologyCard`;
- legacy `UsageRecord`;
- `AICallLog`.

They become read-only compatibility/history data. They must not be automatically
deleted, automatically converted, backfilled into formal verification records,
or presented as if they were produced by the formal workflow.

## Frontend Migration

Frontend migration order:

1. replacement backend ready;
2. replacement contract tests passing;
3. replacement E2E ready;
4. feature/UI switch to the replacement;
5. static scan proves no legacy frontend references;
6. dynamic E2E proves no calls to `/api/alignment/run`;
7. legacy endpoint can move to disabled response.

Do not disable the legacy endpoint before the frontend cutover.

Current frontend dependency:

- file: `frontend/index.html`;
- caller: `runAlignmentForDocument(documentId, courseId, scopeType)`;
- UI: document list action button for teacher/admin course documents;
- payload: `document_id`, optional `course_id`, `scope_type`;
- response dependency: `payload.data.job_id` for queued success or generic
  `status=success`;
- follow-up calls: `loadJobs()` and `loadAlignmentRuns()`;
- success display: queued job message or generic completed message;
- error display: API error message plus alignment failure text.

## Deprecation Response

After caller count is zero, Phase 4 should return:

- HTTP status: 410 Gone;
- error code: `LEGACY_ALIGNMENT_RUN_DEPRECATED`;
- safe message: stable, non-sensitive, no traceback;
- no provider execution;
- no database business writes;
- no credential reads;
- no raw exception.

The exact request-id behavior should be defined in the Phase 4 route contract.
HTTP 410 must not be enabled while the current frontend still calls the route.

## OpenAPI Lifecycle

OpenAPI policy:

- Phase 0-1: mark the route deprecated but keep the current contract;
- Phase 2: add the formal replacement API;
- Phase 3: update frontend to use the replacement;
- Phase 4: document the legacy route as deprecated/disabled;
- Phase 5: remove it from public OpenAPI or move it to a legacy archive.

This ADR does not modify OpenAPI.

## Transaction Policy

Phase 1 containment must preserve the existing transaction contract except for
blocking external execution. It must not use the security task as an opportunity
to redesign all legacy writes.

The replacement workflow must:

- use an explicit application service;
- separate long provider execution from long database transactions;
- audit run/job state transitions;
- persist typed results or persistence plans;
- recover the session after failures;
- avoid partial card approval states.

## Rollback Policy

Before Phase 4/5, frontend cutover may temporarily roll back to the safe
legacy local-only mode through an explicit feature/config switch. Rollback must
not restore legacy external/live provider execution or `urllib` transport.

After the endpoint returns 410 or the dead path is removed, rollback to the old
execution chain is no longer promised.

## Security Boundary

The legacy endpoint must remain no-new-client and no-new-provider. It must not
accept or persist raw credentials, authorization headers, cookies, private
keys, credential-bearing URLs, raw provider responses, or tracebacks.

Legal course content and evidence remain business data and must not be erased
by broad keyword filtering. Secret handling must focus on credential-like
fields, transport errors, configuration, and logs.

## Completion Criteria

The legacy endpoint can enter removal only when all are true:

- frontend references: 0;
- JavaScript API client references: 0;
- E2E references: 0;
- scripts references: 0;
- non-characterization tests references: 0;
- OpenAPI migrated;
- replacement workflow E2E passing;
- replacement readiness passing;
- legacy endpoint has run as disabled for one explicit checkpoint;
- new legacy business writes are 0;
- no-network gate passes.

## Rejected Alternatives

### Directly Extract The Existing Handler As A Service

Rejected. It would formalize a weaker duplicate execution path that bypasses
policy, preflight, formal parser, usage, audit, request-id, and attach gates.

### Direct Route Module Migration

Rejected for the next step. Moving the route before containment would preserve
the external execution risk and make the route look safer than it is.

### Transparent Forward To `/api/alignment/verify`

Rejected. The legacy route is document-level orchestration and writes different
data with different responses. Formal verify is a controlled verification step,
not the full document workflow.

### Dual-write Legacy And Formal Data

Rejected. Dual-write would blur data ownership, create rollback and consistency
risks, and make it unclear which model is authoritative.

### Immediate Endpoint Deletion

Rejected. The frontend still calls the route, so deletion would break the
document alignment flow.

### Retrofit Full Governance Into The Old Route Forever

Rejected. Long-term governance belongs in a replacement document workflow, not
in an ever-growing legacy route.

### Continue Legacy External/Live Provider Execution

Rejected. The old route can reach legacy `urllib` transport without formal
policy/preflight/usage/audit boundaries.

### Return 410 Before Frontend Cutover

Rejected. HTTP 410 is the right disabled response only after zero callers are
proven.

### Automatically Migrate All Legacy Records

Rejected for this policy. Existing records are retained read-only. Any archival
or mapping requires a separate data task.

### Restore Real LLM In This Stage

Rejected. External LLM execution remains disabled in readiness and must be
introduced only through the governed replacement workflow.

## Consequences

This ADR intentionally slows down the final route extraction. The next code
task is not a route move; it is external execution containment for the legacy
route. After containment, the project can design a formal document alignment
workflow without preserving legacy execution semantics as a new service.

The endpoint remains a pilot compatibility liability until Phase 1 is complete.
The risk is documented and must not be treated as resolved by this ADR.

## Pilot Limitations

This policy is accepted only for local and small controlled pilot use:

- SQLite remains acceptable only inside the pilot boundary;
- external LLM providers remain disabled by default;
- the legacy route remains active only for existing frontend compatibility;
- no production migration, observability, or concurrency guarantees are added.

## Future Production Work

Future work must be split into separate tasks:

1. `Task 9C.4U`: Disable Legacy Alignment External Execution.
2. `Task 9C.4V`: Formal Document Alignment Workflow Contract and Boundary.
3. `Task 9C.4W`: Formal Document Alignment Application Service.
4. `Task 9C.4X`: Formal Document Alignment Route.
5. `Task 9C.4Y`: Frontend Cutover.
6. `Task 9C.4Z`: Disable Legacy Alignment Run Endpoint.
7. `Task 9C.5A`: Remove Dead Legacy Execution Path and App.py Cleanup.

None of those phases is implemented by this ADR.
