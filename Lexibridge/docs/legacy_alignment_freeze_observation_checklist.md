# Legacy Alignment Freeze Observation Checklist

## Use Boundary

This checklist records evidence for a named target environment. It does not
authorize HTTP 410, delete data, or replace the rollback procedure. Every
entry needs a UTC timestamp, operator, environment, database identity, and
artifact location.

Target environment: `pilot-internal-local`.

Current execution status: `OBSERVATION_ACTIVE_FREEZE_NOT_EXECUTED`.

## Before Freeze

- [ ] Record observation, rollback, and support owners.
- [ ] Record application instances and Formal/Legacy worker process modes.
- [ ] Record database type, stable identity, and snapshot timestamp.
- [ ] Confirm `LEGACY_ALIGNMENT_OBSERVATION_ENABLED=true` and log retention.
- [ ] Capture Legacy POST/GET metrics up to the Freeze timestamp.
- [ ] Capture queued, running, retrying, and failed Legacy job counts.
- [ ] Capture oldest active job age and every running owner/lock timestamp.
- [ ] Check missing-run jobs, active runs without jobs, and terminal mismatch.
- [ ] Confirm the Formal API and Formal worker are healthy.
- [ ] Confirm rollback settings and the authorized decision owner.

## During Freeze

- [ ] Set `LEGACY_ALIGNMENT_RUNTIME_STATE=freeze`.
- [ ] Set `LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=false`.
- [ ] Verify Legacy POST returns the approved 503 migration response.
- [ ] Verify HTTP, sync upload, internal helper, and job-factory paths create no
      new `AlignmentRun` or `alignment_run` BackgroundJob.
- [ ] Verify Legacy history GET remains available.
- [ ] Verify Formal API admission, worker lease, heartbeat, stale reclaim,
      fencing, retry budget, polling, and item pagination remain healthy.
- [ ] Record every blocked Legacy caller and support action.
- [ ] Confirm no unplanned Legacy worker claim occurs while Freeze is active.

## Drain And Shutdown

- [ ] Classify every running/retrying Legacy job and confirm former owners are
      stopped before any disposition.
- [ ] Change to `draining` only with admission still disabled.
- [ ] Run no more than one explicit `--mode legacy-alignment` worker.
- [ ] Record claim, completion, retry, and failure events.
- [ ] Use fenced safe failure only with reviewed owner and stale-cutoff proof.
- [ ] Require queued, running, and retrying counts to reach zero.
- [ ] Recheck lifecycle integrity and orphan counts.
- [ ] Change to `disabled` and stop the Legacy worker.
- [ ] Keep Formal workers running and repeat the Formal health checks.

## After Freeze

- [ ] Capture final queue, worker, traffic, and Formal snapshots.
- [ ] Confirm no new Legacy run/job creation after the Freeze timestamp.
- [ ] Confirm every stale or failed job has a retained disposition record.
- [ ] Confirm no orphan or unresolved lifecycle mismatch exists.
- [ ] Confirm Legacy history reads and historical data remain available.
- [ ] Confirm the rollback procedure remains executable while the route exists.
- [ ] Record whether rollback was required and restart the observation window
      after any rollback to Active.
- [ ] Store evidence with the observation report and owner approval.

## Current Evidence

The `2026-07-22` isolated SQLite rehearsal passed Freeze, drain, Disabled, and
rollback checks. It is preparation evidence only. No checkbox above is marked
complete for a target environment.

The `pilot-internal-local` Day 0 activation snapshot confirmed:

| Check | Result |
|---|---|
| Persistent SQLite identity | declared |
| Database readiness/integrity | PASS |
| Legacy queued/running/retrying | 0 / 0 / 0 at Day 0 snapshot |
| Formal worker | active in dedicated Formal mode |
| Legacy worker | identified and `STOPPED_BY_POLICY` |
| Observation/rollback/support owner | Project Maintainer |
| Backup, verification, isolated restore | PASS |
| External access-log visibility | limited; gateway source not available |

These activation checks do not mark any operational Freeze checkbox complete.
Counts and process state must be captured again at the separately authorized
Freeze timestamp.

```text
LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE
OBSERVATION_ACTIVE_FREEZE_NOT_EXECUTED
```
