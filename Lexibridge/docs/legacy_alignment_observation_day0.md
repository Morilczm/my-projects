# Legacy Alignment Observation Day 0

## Snapshot Identity

| Field | Value |
|---|---|
| Observation state | `ACTIVE` |
| Snapshot role | Day 0 activation baseline; not an operating day |
| Start UTC | `2026-07-22T15:13:47Z` |
| Provisional end UTC | `2026-08-05T15:13:47Z` |
| Environment | `pilot-internal-local` |
| Application commit | `ff86db830c53cd96466e6da080206eab2d383f74` |
| Observation owner | Project Maintainer |
| Rollback owner | Project Maintainer |
| Support owner | Project Maintainer |

```text
LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE
LOG_RETENTION_LIMITED
EXTERNAL_CONSUMER_VISIBILITY_LIMITED
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```

The start timestamp was recorded after runtime and evidence checks passed. It
was not copied from a local rehearsal. This document records the initial state
against which daily deltas are measured.

## Database Snapshot

| Field | Day 0 value |
|---|---|
| Type | SQLite |
| Stable identity | `project-root/backend/lexibridge.db` |
| SHA-256 | `42a195ab9033124f44f0441dc61c7c1effb5591a6b07db704429c226b5ebcaf0` |
| Size | 1,015,808 bytes |
| Modified time | `2026-07-20T00:33:06+0800` |
| Backup ID | `pilot-backup-54608165f43e4c1493b2248a816b7146` |
| Backup SHA-256 | `87c8a515b718874b9b44fe7ba1c1d39d4e07c27b34f41345c40402915d864b92` |
| Backup verification | PASS; SQLite integrity `ok`; no warnings |

The backup and generated snapshots are retained outside the repository in the
operator observation root. No database write, schema change, or restore was
performed as part of this activation record.

## Runtime Snapshot

| Runtime | Identity | Day 0 state |
|---|---|---|
| Application | `pilot-internal-app-1`; manually detached launch; PID `72469`; `127.0.0.1:5100` | active; `/api/test` healthy; debug disabled |
| Formal worker | `pilot-internal-formal-1`; Formal mode; manually detached launch; PID `72649` | active; interval 2 seconds |
| Legacy worker | `pilot-internal-legacy-1`; Legacy-only mode | `STOPPED_BY_POLICY`; no process |

External providers were disabled. The Formal and Legacy worker claim domains
remain isolated. Failed pre-start process-launch diagnostics are excluded from
observation evidence by the recorded start UTC.

## Day 0 Operational Note

After release gates, a sandboxed health check incorrectly reported localhost
as unreachable even though PID `72469` still owned port 5100. A recovery
attempt was rejected because that port was already in use. It also briefly
started a second Formal worker; the duplicate was identified by PID, stopped,
and never had a queued job to claim. The authoritative application PID
`72469` and Formal worker PID `72649` remained active throughout. The source
database hash stayed
`42a195ab9033124f44f0441dc61c7c1effb5591a6b07db704429c226b5ebcaf0`,
confirming that the diagnostic and cleanup did not change the declared data.

The original detached launch-control sessions are no longer available; the
application and worker processes are adopted by PID 1 and require manual PID
health checks and shutdown. This reinforces `LOG_RETENTION_LIMITED` and the
absence of a production process supervisor.

## Queue And Workflow Snapshot

| Signal | Day 0 count/state |
|---|---:|
| Legacy runtime state | `active` |
| Legacy creation allowed | `true` |
| Legacy worker claim allowed | `true` |
| Legacy queued jobs | 0 |
| Legacy running jobs | 0 |
| Legacy retrying jobs | 0 |
| Legacy failed jobs | 0 |
| AlignmentRun total | 1 |
| AlignmentRun completed | 1 |
| Legacy BackgroundJob total | 0 |
| Formal WorkflowRun total | 0 |
| Formal WorkflowRun active | 0 |
| Formal BackgroundJob total | 0 |
| BackgroundJobEvent total | 6 |

The Legacy worker claim policy is available because runtime state is Active,
but no Legacy worker process was started. Observation start did not execute
Freeze and did not create, replay, migrate, or delete a job.

## Logging And Metric Activation

Retained logical sources in the operator observation root:

- `logs/application.log` for HTTP and structured application events;
- `logs/formal-worker.log` for the dedicated Formal worker;
- `logs/legacy-worker.log` for the explicit Legacy stopped-state record;
- timestamped queue, workflow, traffic, and process snapshots.

At `2026-07-22T15:16:22Z`, a deliberate unauthenticated localhost probe to
`GET /api/alignment/runs` returned HTTP 401. It produced one payload-free
structured observation event and no creation signal:

| Metric | Day 0 activation result |
|---|---:|
| Legacy GET requests | 1 |
| Access-denied results | 1 |
| Legacy POST requests | 0 |
| AlignmentRun creation signals | 0 |
| Legacy BackgroundJob creation signals | 0 |
| Attributed external consumers | unknown |

This probe verifies collection, not real consumer traffic. Gateway and reverse
proxy logs are unavailable, so external consumers cannot be reported as zero.

## Notice And Rollback

The migration notice was distributed at `2026-07-22T15:17:39Z` to the known
controlled Pilot scope through the shared release branch and operational task
handoff. The Project Maintainer owns observation, rollback, and support.
`docs/legacy_alignment_rollback_procedure.md` remains the executable rollback
record while the Legacy route exists.

## Contract Boundary

Observation activation changed documentation and runtime evidence only. It did
not change the Legacy route, Formal API, workflow version, Formal job type,
Idempotency scope, frontend, provider boundary, or database schema.

The observation clock is active, but zero operating days have closed. Day 1 is
recorded only after the first post-start operating-day checklist is completed.
