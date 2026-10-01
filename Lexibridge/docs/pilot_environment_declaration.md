# Pilot Environment Declaration

## Environment Identity

- Environment name: `pilot-internal-local`
- Purpose: controlled internal academic pilot and Legacy alignment observation
- Lifecycle: manually operated on the Project Maintainer's designated workstation
- Deployment class: single-workstation local pilot
- Production status: not production and not production-like staging
- Observation state: `ACTIVE`

```text
LEGACY_ALIGNMENT_OBSERVATION_ENVIRONMENT_READY
LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE
EXTERNAL_CONSUMER_VISIBILITY_LIMITED
```

The environment was activated for observation at `2026-07-22T15:13:47Z`.
Manual lifecycle and local-only evidence retention remain Pilot limitations.

## Application

| Field | Declared value |
|---|---|
| Product | LexiBridge AI Pilot v1.0 Candidate |
| Branch | `release/pilot-v1-candidate` |
| Environment-readiness baseline | `f04c32c38423192a3088bf32151ae51127eb3b3f` |
| Deployed application commit | `ff86db830c53cd96466e6da080206eab2d383f74` |
| Runtime | Flask, debug disabled, `127.0.0.1:5100` |
| Frontend | same-origin static frontend served by Flask |
| Provider boundary | external/live providers disabled |

The documentation commit that records activation does not change the deployed
application commit.

## Database

| Field | Declared value |
|---|---|
| Type | SQLite |
| Stable identity | `project-root/backend/lexibridge.db` |
| Day 0 size | 1,015,808 bytes |
| Day 0 source fingerprint | SHA-256 `42a195ab9033124f44f0441dc61c7c1effb5591a6b07db704429c226b5ebcaf0` |
| Day 0 modified time | `2026-07-20T00:33:06+0800` |
| Integrity | connectable; backup verification reported SQLite `ok` |
| Schema state | current candidate schema; no Alembic framework |
| Day 0 backup | `pilot-backup-54608165f43e4c1493b2248a816b7146`, verified PASS |

The source hash is a Day 0 identity, not an invariant. Legitimate Pilot writes
may change it and must be reflected in later snapshots.

## Worker Processes

| Runtime | Mode/identity | Start state | Ownership |
|---|---|---|---|
| Application | `pilot-internal-app-1`; manually detached launch; PID `72469` | active | Project Maintainer |
| Formal worker | Formal; `pilot-internal-formal-1`; manually detached launch; PID `72649` | active | Project Maintainer |
| Legacy worker | Legacy-only; `pilot-internal-legacy-1` | `STOPPED_BY_POLICY` | Project Maintainer |

The Formal worker cannot claim `alignment_run` jobs, and no Legacy worker runs
by default. There is no process supervisor; manually detached processes and
operator health checks are the declared local Pilot process model.

## Ownership

| Role | Assigned owner | Responsibility |
|---|---|---|
| Observation owner | Project Maintainer | daily metrics, retention, caller classification |
| Rollback owner | Project Maintainer | authorize and execute rollback |
| Support owner | Project Maintainer | migration notice and caller follow-up |
| Process owner | Project Maintainer | application and worker lifecycle |

## Logging And Evidence Sources

| Source | Logical retained record | Availability |
|---|---|---|
| Direct HTTP and structured app events | operator observation root `logs/application.log` | active |
| Formal worker output | operator observation root `logs/formal-worker.log` | active |
| Legacy worker state/output | operator observation root `logs/legacy-worker.log` | active; stopped-state record present |
| Job lifecycle | `BackgroundJobEvent` in declared database | available |
| Queue/workflow state | timestamped read-only snapshots | available |
| Gateway/reverse-proxy logs | none | `NOT_AVAILABLE` |
| Central metrics database | none | `NOT_AVAILABLE` |

Logs and generated snapshots are runtime evidence outside Git. They must be
retained through the 14-day window and review, but retention is manual and
local. The environment is therefore marked `LOG_RETENTION_LIMITED`.

## Metric Availability Matrix

| Metric | Source | Available | Notes |
|---|---|---|---|
| `POST /api/alignment/run` | structured application event | Yes | active after start UTC |
| `GET /api/alignment/runs` | structured application event | Yes | Day 0 probe retained |
| `AlignmentRun` creation | events and database snapshots | Yes | payload-free counts |
| Legacy `BackgroundJob` creation | events and database snapshots | Yes | filtered to `alignment_run` |
| Legacy queue state | runtime status and database snapshots | Yes | manual daily capture |
| Legacy worker activity | `BackgroundJobEvent` and Legacy worker log | Yes | worker intentionally stopped at Day 0 |
| Formal Run creation | Formal workflow snapshots | Yes | count and state distribution |
| Formal worker execution | event records and Formal worker log | Yes | active |
| Formal `legacy_alignment_requests` | Formal frontend E2E artifact | Yes | collect per operating day |
| External caller network identity | gateway/reverse-proxy logs | No | visibility remains limited |

## Active Pilot Configuration

The activation verified these non-secret settings:

```text
LEGACY_ALIGNMENT_OBSERVATION_ENABLED=true
LEGACY_ALIGNMENT_RUNTIME_STATE=active
LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=true
LOG_REDACT_SECRETS=true
AI_PROVIDER_MODE=none
```

Observation activation is not Freeze. Legacy admission remains active until a
separate approved Freeze operation, while Formal contracts remain unchanged.

## Readiness Boundary

The named environment, deployed application, database, process identities,
owners, retained local logs, Day 0 snapshot, backup, and rollback procedure
are active. The environment may collect observation evidence, but it cannot
provide authoritative gateway-level evidence about repository-external clients.
