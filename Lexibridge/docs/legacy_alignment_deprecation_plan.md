# Legacy Alignment Deprecation Plan

## Decision

- Task: `9C.5M`
- Baseline: `4319d35751ba5468961081b17c0d7a49a5997762`
- Runtime containment amendment: Task `9C.5N`, baseline
  `d4ec0790c53f05f5f3d598908ac4da60f5c2ea80`
- Runtime isolation amendment: Task `9C.5N.1`, baseline
  `e58982d216d9d2977abc5c91f35a2b1c7429ade8`
- Freeze preparation amendment: Task `9C.5N.2`, baseline
  `9762b03197b0a919b72fd6ced913982d0da4a794`
- Controlled observation amendment: Task `9C.5O`, baseline
  `388666a192df9d33044541aaca4ddf42e6aa7bd2`
- Route: `POST /api/alignment/run`
- Current state: `ACTIVE_COMPATIBILITY_SURFACE`
- Boundary status: `LEGACY_ALIGNMENT_DEPRECATION_BOUNDARY_ESTABLISHED`
- HTTP 410 readiness: `NOT_READY`

This document defines the evidence required to enter a deprecation window. It
does not change the route, response, permission model, frontend, worker,
database schema, provider behavior, or formal workflow.

## Scope Boundary

The POST execution route is the retirement target. These related surfaces are
separate decisions:

- `GET /api/alignment/runs` remains an active frontend history view;
- `GET /api/alignment/runs/{run_id}` remains a compatibility detail view;
- `GET /api/admin/alignment-runs` remains an admin read view;
- legacy `AlignmentRun` and `TerminologyCard` data may require long-term
  read-only retention after POST admission ends.

HTTP 410 for the POST must not implicitly delete those read contracts or data.

## 410 Readiness Gates

| Gate | Required Evidence | Current Evidence | Status |
|---|---|---|---|
| Frontend consumer = 0 | Static scan and browser request count show no production legacy POST/fallback | 9C.5K/9C.5L and formal UI E2E show `legacy_alignment_requests=0` | satisfied |
| External consumer = no known | Client-owner inventory plus route traffic observation shows no caller | No repository executable client found, but no gateway/access telemetry or external client registry exists | blocked: `UNKNOWN_EXTERNAL_LEGACY_CONSUMER` |
| Queued legacy jobs = 0 | Authoritative target database query at window start and immediately before cutover | Repository-local SQLite snapshot is 0 only | conditional; not environment-authoritative |
| Running legacy jobs = 0 | Authoritative query plus explicit disposition for stale-running jobs | Isolated safe-failure and drain rehearsal passed; target database evidence is unavailable | blocked pending target execution |
| Retrying legacy jobs = 0 | Authoritative query and retry drain/quarantine report | Repository-local SQLite snapshot is 0 only | conditional |
| No lifecycle mismatch | No missing-run jobs; no active runs linked to terminal/missing jobs | Repository-local snapshot has no mismatch; code permits mismatch after crash/failure/cancel | blocked pending environment audit |
| Legacy creation controlled | Admission is disabled or intentionally accepted for an approved observation window | All repository production creation paths share admission; isolated Freeze/rollback rehearsal passed; release defaults remain Active | partially satisfied; blocked pending target freeze deployment |
| Worker shutdown procedure exists | Legacy polling can stop without halting Formal Workflow, with drain and stale-job handling | Explicit modes, snapshot, fenced safe failure, isolated shutdown rehearsal, and local Formal-only runtime pass | partially satisfied; blocked pending target-environment rehearsal |
| Migration notice exists | OpenAPI/operator notice names formal replacement, timeline, owner, and support path | OpenAPI identifies the formal replacement; no dated timeline, owner, or support path exists | partially satisfied; blocked |
| Monitoring window complete | Approved duration with route-call and queue-state evidence retained | Payload-free route/creation telemetry and report tooling exist; target deployment is 0 of 14 days and 0 of 5 operating days | blocked: `OBSERVATION_WINDOW_PENDING` |
| Compatibility tests reclassified | Tests are tagged as keep, convert-to-410, or remove-after-retirement | Inventory exists; conversion decision is not implemented | blocked |
| Rollback and incident owner defined | Named owner and reversible cutover procedure exist | Reversible procedure and isolated rollback rehearsal exist; target owner/support path is unassigned | blocked |

## Required Monitoring Window

Before 410 is authorized, the pilot operator must select an explicit window
and record, per environment:

- authenticated `POST /api/alignment/run` call count and caller identity class;
- response status distribution without request bodies or credentials;
- `alignment_run` jobs by `queued`, `running`, `retrying`, `failed`,
  `completed`, and `canceled`;
- age of the oldest queued/retrying/running legacy job;
- jobs missing a linked `AlignmentRun`;
- active runs with no job or with a terminal/missing job;
- manual retry/cancel operations;
- worker crashes or legacy jobs stuck in `running`;
- support reports from pilot teachers, scripts, and external API owners.

The concrete minimum window and required evidence are defined in
`docs/legacy_alignment_runtime_observation_plan.md`. Repository scanning alone
cannot substitute for runtime evidence.

## Queue Drain And Running-Job Policy

Before disabling admission:

1. identify every target database and worker instance;
2. record initial legacy queue counts without mutating data;
3. stop or gate new legacy POST admission only in a future approved task;
4. keep the legacy worker and dispatch code available while queued/retrying
   work drains;
5. investigate every running job because automatic legacy stale reclaim does
   not exist;
6. choose an explicit operator action for each stale job: complete, cancel,
   fail safely, or requeue under a separately reviewed procedure;
7. verify linked `AlignmentRun` status and legacy card writes after drain;
8. require queued/running/retrying and lifecycle-mismatch counts to remain zero
   immediately before 410.

This task does not choose or execute a mutation procedure for stale jobs.

## Consumer Confirmation Procedure

The following evidence is required to replace
`UNKNOWN_EXTERNAL_LEGACY_CONSUMER` with
`NO_KNOWN_EXTERNAL_LEGACY_CONSUMER`:

1. search the repository and maintained deployment/configuration repositories;
2. identify owners of documented API clients, browser bookmarks, teaching
   scripts, notebooks, scheduled jobs, and integration accounts;
3. inspect sanitized gateway/application access metrics for the approved
   observation window;
4. publish the formal replacement endpoints and migration deadline;
5. obtain explicit confirmation from known client owners;
6. retain the evidence with the release decision.

No request payload, token, credential, prompt, output, or private evidence may
be added to monitoring artifacts.

## Test Retirement Matrix

| Test Class | During Window | At HTTP 410 | After Dead-Code Removal |
|---|---|---|---|
| Formal zero-legacy/fallback tests | keep unchanged | keep unchanged | keep unchanged |
| Formal worker no-legacy-dispatch tests | keep unchanged | keep unchanged | keep unchanged |
| Legacy external/no-network containment | keep while execution exists | replace with no-transport 410 assertions | remove only with retired execution code |
| Legacy local route/worker success | keep during drain | split: route expects 410; direct worker drain test remains until queue retirement | remove only after worker/data decision |
| Legacy permission/response characterization | keep during window | convert to approved deprecation response contract | remove only after route removal |
| Legacy GET history/admin tests | keep; separate scope | keep unless read surfaces are separately migrated | follow independent read-retention decision |
| Readiness legacy safety probes | keep | update to assert approved disabled/410 behavior and zero transport | retain a no-regression retirement Gate |

Tests are evidence and must be converted deliberately; their existence is not
a reason to preserve obsolete runtime behavior forever.

## Migration Notice Requirements

The future notice must:

- identify `POST /api/document-alignment-runs` as the supported replacement;
- include status and item polling endpoints;
- state the compatibility-window start and end dates;
- state the planned HTTP status/error envelope after the window;
- identify an owner/support path;
- distinguish POST retirement from legacy GET history retention;
- avoid promising production readiness beyond the controlled pilot boundary.

OpenAPI now identifies the formal replacement and preserves the active
compatibility contract. A dated operator/client notice with an owner and
support path is still required.

## Runtime Containment Amendment

Tasks 9C.5N through 9C.5N.2 confirm that runtime containment is isolated and
freeze tooling exists, but retirement evidence is not operationally complete:

- legacy claim records `locked_by` and `locked_at` but does not use heartbeat,
  stale reclaim, lease ownership, or fencing;
- running legacy jobs have no safe automatic recovery path;
- cancel/retry update the shared job but do not guarantee linked
  `AlignmentRun` terminal consistency;
- sync upload and helper-backed execution are now covered by the same admission
  decision as the default async legacy POST;
- default and Formal worker modes no longer poll legacy jobs; an explicit
  legacy mode remains available for controlled compatibility drain;
- a unified default-enabled admission boundary covers route, sync upload,
  helper, and job-factory creation;
- Active/Freeze/Draining/Disabled states, read-only queue inspection, fenced
  safe failure, and an isolated shutdown rehearsal are present;
- payload-free request and internal-creation telemetry plus a report tool are
  present, but no target environment has begun the required window;
- the external consumer state remains unknown until the observation window
  completes.

See `docs/legacy_alignment_runtime_inventory.md`,
`docs/legacy_alignment_runtime_isolation.md`,
`docs/legacy_creation_boundary.md`,
`docs/legacy_running_job_shutdown_plan.md`, and
`docs/legacy_alignment_runtime_observation_plan.md` for the evidence and
operational requirements.

## Entry Criteria For A Legacy 410 Task

A future Task 9C.5P may begin only when all of the following are documented:

1. production frontend legacy POST and fallback counts remain zero;
2. external consumer status is `NO_KNOWN_EXTERNAL_LEGACY_CONSUMER` after the
   approved observation window;
3. authoritative queued, running, and retrying legacy job counts are zero in
   every target environment;
4. no orphan or run/job lifecycle mismatch remains;
5. a stale-running job disposition is approved;
6. legacy creation is disabled or intentionally accepted under the approved
   cutover procedure;
7. a legacy worker shutdown procedure is rehearsed without stopping Formal
   Workflow processing;
8. a dated migration notice has been published;
9. compatibility tests have an approved conversion map;
10. rollback/incident ownership is assigned;
11. Formal Workflow and all release/readiness Gates remain green.

## Current Blockers

- `UNKNOWN_EXTERNAL_LEGACY_CONSUMER` due to absent runtime traffic evidence;
- release defaults intentionally remain Active until the observation owner
  authorizes a target-environment freeze;
- explicit legacy worker mode still claims and executes queued/retrying jobs
  when an operator starts it;
- no automatic legacy stale-running reclaim exists; fenced operator safe
  failure is available but requires a confirmed stopped owner and explicit
  environment/apply gates;
- worker shutdown and rollback are separable and rehearsed in isolation, but
  not yet against target process managers and authoritative databases;
- local zero queue counts are not authoritative for other environments;
- OpenAPI names the formal replacement, but no dated notice, owner, or support
  path exists;
- observation telemetry is available, but no target deployment, named owner,
  completed 14-day window, or five actual operating days exist;
- legacy compatibility tests have not yet been converted to a 410 contract.

## Authorization Result

The retirement boundary is now explicit, but HTTP 410 and code removal are not
authorized.

```text
LEGACY_ALIGNMENT_DEPRECATION_BOUNDARY_ESTABLISHED
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
