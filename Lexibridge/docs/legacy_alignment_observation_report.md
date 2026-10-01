# Legacy Alignment Observation Report

## Report Status

- Preparation task: `9C.5O`
- Activation task: `9C.5O.3`
- Application baseline: `ff86db830c53cd96466e6da080206eab2d383f74`
- Report generated: `2026-07-22`
- Target environment: `pilot-internal-local`
- Target database: `project-root/backend/lexibridge.db` (SQLite)
- Observation state: `ACTIVE`
- Observation start: `2026-07-22T15:13:47Z`
- Provisional observation end: `2026-08-05T15:13:47Z`
- Actual target-environment active days: `0`
- External consumer status: `UNKNOWN_EXTERNAL_LEGACY_CONSUMER`
- Activation record: `docs/legacy_alignment_observation_window.md`

```text
LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE
LOG_RETENTION_LIMITED
EXTERNAL_CONSUMER_VISIBILITY_LIMITED
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```

The Day 0 environment, process, database, queue, log, owner, notice, and
rollback evidence is recorded in
`docs/legacy_alignment_observation_day0.md`. The required continuous 14-day
window with at least five actual operating days has started but has not elapsed.
No gateway or reverse-proxy source exists, so this report does not infer zero
external traffic from repository scans, local logs, or E2E runs.

## Observation Window

The window is active in the single declared target environment. It must run
for at least 14 continuous 24-hour periods and cover at least five actual
operating days. Any unexplained Legacy POST or new creation signal restarts the
zero-creation interval after the caller is classified.

| Field | Current value | Exit requirement |
|---|---|---|
| Start time | `2026-07-22T15:13:47Z` | retained UTC deployment timestamp |
| End time | provisional `2026-08-05T15:13:47Z` | at least 14 days after start and five operating days |
| Environment | `pilot-internal-local` active | every target Pilot environment |
| Database | Day 0 SQLite snapshot retained | daily and event snapshots |
| Worker state | Formal active; Legacy stopped by policy | daily process inventory |
| Legacy POST metrics | active local structured log | attributed request series |
| Legacy GET metrics | active; one Day 0 collection probe | retained read-usage series |
| External signal | unavailable | gateway/access-log evidence plus owner review |

## Traffic Telemetry

`LEGACY_ALIGNMENT_OBSERVATION_ENABLED=true` emits payload-free structured
events for:

- `POST /api/alignment/run`;
- `GET /api/alignment/runs` and run detail;
- `GET /api/admin/alignment-runs`;
- `POST /api/documents/upload?sync=true`;
- internal `AlignmentRun` and `alignment_run` job creation signals.

Events retain timestamp, route template, method, status, safe result, caller ID
and role, sync/async mode, and creation counts. They do not retain request
bodies, terms, prompts, outputs, credentials, authorization headers, cookies,
or raw exceptions. Logs are summarized without database writes:

```bash
python scripts/legacy_alignment_observation_report.py \
  --log /path/to/application.jsonl \
  --environment TARGET_ENVIRONMENT \
  --database TARGET_DATABASE_LABEL \
  --window-start START_UTC \
  --window-end END_UTC \
  --active-days N \
  --external-consumer-status UNKNOWN_EXTERNAL_LEGACY_CONSUMER \
  --json-output /path/to/legacy-observation-report.json
```

Activation alone does not satisfy the duration, active-day, zero-creation, or
external-consumer evidence gates. Queue, worker shutdown, rollback, and Formal
regression evidence remain separate retirement gates.

## Current Metrics

| Signal | Target-environment result | Repository/local evidence |
|---|---|---|
| Legacy POST requests | 0 at Day 0 activation | Formal frontend E2E must continue to report `legacy_alignment_requests=0` |
| Legacy GET history | 1 deliberate unauthenticated collection probe, HTTP 401 | frontend still actively loads `GET /api/alignment/runs` |
| Legacy creation | 0 at Day 0 activation | Freeze rehearsal separately blocked one POST with no run/job creation |
| Internal creation | 0 at Day 0 activation | telemetry covers helper and job-factory signals |
| Legacy queue | queued/running/retrying/failed all 0 | daily snapshots required |
| External consumer | unknown | no gateway/access-log source is connected |

Day 0 activation and local tests are not counted as an operating day.

## Controlled Freeze Evidence

Command:

```bash
python scripts/run_legacy_alignment_shutdown_rehearsal.py \
  --json-output /private/tmp/lexibridge-9c5o-controlled-freeze.json
```

Result on `2026-07-22`: `PASS` in isolated temporary SQLite.

| Phase | Queued | Running | Retrying | Failed | Result |
|---|---:|---:|---:|---:|---|
| Freeze snapshot | 1 | 1 | 0 | 0 | new HTTP/internal creation blocked |
| Drained snapshot | 0 | 0 | 0 | 1 | queued work completed; stale work safely failed |
| Disabled | 0 | 0 | 0 | 1 | Legacy claim paused |
| Rollback to Active | not a drain metric | not a drain metric | not a drain metric | not a drain metric | Legacy POST restored with HTTP 200 |

This is a non-production rehearsal. Target database counts and process-manager
shutdown remain pending.

## Formal-Only Runtime Evidence

The Formal API and recovery E2E were run with:

```text
LEGACY_ALIGNMENT_RUNTIME_STATE=disabled
LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=false
```

The normal HTTP worker flow, polling, pagination, permissions, idempotency,
retryable requeue, claim-crash stale reclaim, partial resume, terminal recovery,
and retry exhaustion all passed with zero external dependency requests. The
frozen contracts remained:

- workflow version: `formal-document-alignment-v1`;
- job type: `formal_document_alignment_workflow_v1`;
- idempotency scope: requested by, source UID, workflow version, and key.

```text
FORMAL_ONLY_RUNTIME_CONFIRMED
```

## Remaining Evidence

Before this report can enter review:

1. retain 14 continuous days and five actual operating days;
2. attribute every Legacy POST and internal creation signal;
3. capture daily process, queue, workflow, and traffic snapshots;
4. capture authoritative queue snapshots before, during, and after any drain;
5. rehearse Legacy worker shutdown against the actual manual process lifecycle;
6. retain zero active Legacy counts for the approved hold period;
7. keep Formal and readiness gates green throughout the window;
8. review the external-visibility limitation without claiming zero consumers.

## Activation Verification

The following Gates passed on `2026-07-22`. They verify the activation change
and Formal regression boundary, but do not advance the operating-day count.

| Gate | Result | Artifact or detail |
|---|---|---|
| Observation documentation contract | PASS | 8 tests |
| Full pytest | PASS | 1115 tests, 6 existing deprecation warnings |
| Release safety | PASS | no finding |
| Developer check | PASS | 1115 tests, migration, and backend smoke |
| Formal frontend with Legacy Disabled | PASS | `/private/tmp/lexibridge-9c5o3-formal-frontend.json`; three Formal POSTs, zero Legacy POSTs |
| Teacher browser E2E | PASS | `/private/tmp/lexibridge-9c5o3-teacher.json` |
| Full browser E2E | PASS | `/private/tmp/lexibridge-9c5o3-full.json` |
| Browser console/page errors | PASS | zero unexpected errors |
| External provider requests | PASS | zero actual dependency requests |
| Pilot readiness | `READY_WITH_CONDITIONS` | `/private/tmp/lexibridge-9c5o3-readiness.json` |

The browser flows continue to issue the active compatibility history GET, but
Formal execution made zero requests to the Legacy POST and used no fallback.
