# Legacy Alignment Observation Window

## Activation Status

- Task: `9C.5O.3`
- Application baseline: `ff86db830c53cd96466e6da080206eab2d383f74`
- Environment: `pilot-internal-local`
- Current state: `ACTIVE`
- Start UTC: `2026-07-22T15:13:47Z`
- Provisional 14-day end UTC: `2026-08-05T15:13:47Z`
- Actual operating days completed: `0`
- Required operating days: `5`

```text
LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE
LIMITED_OBSERVABILITY
EXTERNAL_CONSUMER_VISIBILITY_LIMITED
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```

The observation clock started only after the application, retained local
logs, Formal worker, database identity, initial queue snapshot, owners, and
rollback procedure were verified. The start was not backdated to a rehearsal.
The activation record is Day 0; the first completed post-start operating-day
checklist will count as Day 1.

## State Machine

```text
PREPARED -> ACTIVE -> COMPLETED -> REVIEWED
```

| State | Entry evidence |
|---|---|
| `PREPARED` | Telemetry, procedures, environment, and local rehearsals exist |
| `ACTIVE` | Named environment/database/processes/owners, retained logs, Day 0 snapshot, notice record, and UTC start exist |
| `COMPLETED` | At least 14 continuous calendar days and five actual operating days have retained evidence |
| `REVIEWED` | Owners review traffic, queue, workers, callers, rollback, and Formal evidence |

This task enters only `ACTIVE`. Calendar duration, operating-day coverage,
traffic classification, and retirement review remain open.

## Environment Declaration

| Scope | Activated value |
|---|---|
| Application | commit `ff86db830c53cd96466e6da080206eab2d383f74`, Flask debug disabled, `127.0.0.1:5100` |
| Database | SQLite, `project-root/backend/lexibridge.db` |
| Formal worker | `pilot-internal-formal-1`, Formal mode, active at start |
| Legacy worker | `pilot-internal-legacy-1`, `STOPPED_BY_POLICY` at start |
| Legacy runtime | `active`; route admission enabled |
| Application log | retained local `application.log` in the operator observation root |
| Formal worker log | retained local `formal-worker.log` in the operator observation root |
| Legacy worker log | retained local `legacy-worker.log` with stopped-state record |
| Gateway/reverse-proxy logs | `NOT_AVAILABLE` |

The exact process IDs and database snapshot are in
`docs/legacy_alignment_observation_day0.md`. Runtime evidence is kept outside
the repository and contains no credentials, prompts, provider output, request
bodies, or private evidence payloads.

## Ownership

| Role | Responsibility | Owner |
|---|---|---|
| Observation owner | Daily metrics, caller attribution, evidence retention | Project Maintainer |
| Rollback owner | Freeze rollback decision and execution | Project Maintainer |
| Support owner | Migration questions and caller communication | Project Maintainer |

These assignments cover the single-person controlled Pilot only. A hosted or
multi-operator environment must declare its own named operational contacts.

## Duration Rules

1. Retain evidence continuously from `2026-07-22T15:13:47Z`.
2. Do not review completion before `2026-08-05T15:13:47Z`.
3. Extend beyond that time until five actual operating days are complete.
4. Restart the zero-creation interval after any unexplained Legacy creation.
5. Do not count local rehearsals or Day 0 as an operating day.

## Metrics And Sources

| Signal | Required dimensions | Active source | Status |
|---|---|---|---|
| Legacy POST | timestamp, caller ID/role, result, status, sync/async, creation counts | payload-free `legacy_alignment_request` application event | active, local retention |
| Legacy history GET | timestamp, caller ID/role, route, status | payload-free `legacy_alignment_request` application event | active, local retention |
| AlignmentRun creation | timestamp, caller/source, count | request and internal creation events plus database snapshot | active |
| Legacy BackgroundJob creation | timestamp, caller/source, count | creation events plus database snapshot | active |
| Queue state | queued, running, retrying, failed, oldest active age | runtime status tool and database snapshot | manual daily capture |
| Legacy worker | claim, completion, retry, failure, worker ID | `BackgroundJobEvent` and worker log | active when worker is intentionally started |
| Formal runs | count, terminal distribution, worker execution | Formal database snapshot, event records, worker log | active |
| Formal Legacy POST count | `legacy_alignment_requests` | Formal frontend E2E/network artifact | per operating day |
| External consumer signal | gateway/access logs and client-owner confirmation | no gateway source | unavailable |

Local application logs and database snapshots are retained, but there is no
central log store or gateway telemetry. Log survival depends on the operator's
workstation and detached process lifecycle. The observation therefore remains
`LIMITED_OBSERVABILITY`, and repository-external consumers remain unknown.
Pre-start process-launch diagnostics are excluded by the recorded start UTC.

## Collection Cadence

- retain Legacy HTTP and creation events continuously;
- capture process, queue, workflow, and database summaries at least daily;
- capture the same summaries before and after any Freeze/drain action;
- run Formal network verification on every actual operating day;
- classify unattributed callers and active/failed jobs daily;
- use `docs/legacy_alignment_observation_daily_checklist.md` for sign-off;
- keep generated artifacts outside Git and redact raw payloads and secrets.

## Legacy GET Consumer Decision

Decision: **B - retain as a read-only compatibility surface**.

`frontend/index.html` function `loadAlignmentRuns()` uses
`GET /api/alignment/runs` for legacy history display. The Formal API does not
currently expose an equivalent history-list contract. This route remains
active and unchanged; its usage is observed separately from Legacy creation.

## Freeze Boundary

Starting the observation window did not execute Freeze. At activation the
Legacy runtime is `active` and route admission remains enabled so real caller
signals can be observed. Freeze requires a separately authorized operation
using `docs/legacy_alignment_freeze_observation_checklist.md`.

## Activation Evidence

The activation gate passed at `2026-07-22T15:13:47Z` with:

- stable environment and database identity;
- active application and dedicated Formal worker;
- Legacy worker intentionally stopped and separately identifiable;
- retained local application and worker logs;
- initial database, queue, workflow, and process snapshot;
- assigned observation, rollback, and support owners;
- verified Formal health with external providers disabled;
- migration notice distribution record;
- executable rollback procedure.

See `docs/legacy_alignment_observation_day0.md` for the immutable Day 0 values.
