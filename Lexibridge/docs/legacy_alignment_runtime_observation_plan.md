# Legacy Alignment Runtime Observation Plan

## Purpose

This plan defines the evidence required to move legacy alignment from active
compatibility into a future deprecation execution task. It does not collect
production telemetry by itself and does not authorize HTTP 410.

- Task: `9C.5N`
- Baseline: `d4ec0790c53f05f5f3d598908ac4da60f5c2ea80`
- Runtime-isolation amendment: Task `9C.5N.1`, baseline
  `e58982d216d9d2977abc5c91f35a2b1c7429ade8`
- Freeze-preparation amendment: Task `9C.5N.2`, baseline
  `9762b03197b0a919b72fd6ced913982d0da4a794`
- Target POST: `/api/alignment/run`
- Separate read surfaces: `/api/alignment/runs`,
  `/api/alignment/runs/{run_id}`, and `/api/admin/alignment-runs`
- External consumer status: `UNKNOWN_EXTERNAL_LEGACY_CONSUMER`

## Observation Window

The minimum observation window is **14 consecutive calendar days in every
target pilot environment**, and it must contain at least **5 scheduled active
teaching days**. If the 14-day period contains fewer than 5 active teaching
days, observation continues until the fifth active teaching day is complete.

The window may start only after:

1. the Formal Workflow frontend is deployed in that environment;
2. the migration notice identifies the formal replacement;
3. sanitized route and job metrics are available;
4. target databases and worker instances are enumerated;
5. an observation owner and rollback/incident owner are named.

Any legacy POST during the window must be attributed to a known caller and
resolved. The zero-POST interval restarts after the last unexplained or
unmigrated call. Deployments that change legacy admission, worker dispatch,
or telemetry also restart the window.

## Required Signals

| Signal | Required Measurement | Frequency | Exit Evidence |
|---|---|---|---|
| Legacy POST requests | Count by environment, status code, authenticated role/integration class, and sync/async mode | continuous; daily summary | zero after the final caller is migrated for the full window |
| Legacy GET history usage | Count list/detail/admin reads separately | continuous; daily summary | read-retention decision documented; GET traffic does not imply POST execution use |
| Queued jobs | Count `alignment_run` jobs and oldest age | at least hourly and before/after worker maintenance | zero at window exit and immediately before cutover |
| Running jobs | Count, owner, lock age, and linked run state | at least hourly | zero; every stale candidate has an approved disposition |
| Retrying jobs | Count, attempt distribution, error-code class, and oldest age | at least hourly | zero at window exit |
| Worker activity | Claims, completions, retries, failures, cancels, worker identifier, and last legacy activity | continuous; daily summary | no unexplained activity and a tested shutdown procedure |
| External consumer signal | Sanitized gateway/application access evidence plus client-owner confirmations | continuous plus weekly review | `NO_KNOWN_EXTERNAL_LEGACY_CONSUMER` decision with retained evidence |
| Lifecycle integrity | Missing-run jobs, active runs without jobs, and run/job terminal mismatches | daily and before cutover | zero unresolved mismatches |
| Rollback ownership | Named primary/secondary owner, decision authority, and contact path | before window starts | approved owner record and rehearsal evidence |

Metrics must not retain request bodies, prompts, outputs, credentials, tokens,
cookies, authorization headers, private evidence, or raw exception traces.
Caller identity should use the minimum stable operational identifier needed
to contact an owner.

## Collection Boundary

Repository scanning proves only that the Formal frontend has no legacy POST
consumer. It cannot prove that deployed scripts or clients are absent.
Evidence must come from every target environment's sanitized gateway or
application access metrics and authoritative database queries.

The repository now has unified production creation admission, explicit worker
modes, a read-only queue snapshot, fenced safe failure, and an isolated
shutdown rehearsal. Task 9C.5O adds payload-free structured request and
creation signals plus `scripts/legacy_alignment_observation_report.py` for
offline aggregation. Target environments still need to deploy and retain those
logs, and there is no automated target-environment job/run reconciliation
report. Those remaining gaps must be addressed operationally before the
observation window can produce complete evidence.

## Worker Shutdown Readiness

A future shutdown procedure must:

1. stop or explicitly gate new legacy creation without affecting Formal API;
2. leave the legacy dispatcher available while queued/retrying work drains;
3. identify and disposition every running job because no stale reclaim exists;
4. verify linked `AlignmentRun` and card state after each disposition;
5. prove queued, running, and retrying counts remain zero;
6. disable legacy polling without stopping formal worker processing;
7. preserve read-only legacy history where required;
8. include a reversible re-enable or incident rollback procedure.

`scripts/run_worker.py` now excludes legacy polling in its default `standard`
mode and provides an explicit `legacy-alignment` mode for drain. This makes
worker shutdown separable from Formal Workflow. The procedure still requires
an environment rehearsal and approved stale-running disposition before it is
retirement evidence.

## External Consumer Review

The observation owner must inventory:

- teacher scripts, notebooks, bookmarks, and demo tooling;
- scheduled automation and integration accounts;
- clients maintained in deployment or configuration repositories;
- sanitized traffic not attributable to the production frontend;
- support reports received during the window.

No caller found in the application repository is not sufficient to replace
`UNKNOWN_EXTERNAL_LEGACY_CONSUMER` with
`NO_KNOWN_EXTERNAL_LEGACY_CONSUMER`.

## Rollback Requirements

Before deprecation execution, the owner must document:

- the exact route/admission change and rollback trigger;
- how legacy admission can be restored without reverting Formal Workflow;
- how queued work and partially updated runs are reconciled;
- how the legacy worker is restarted without duplicate execution;
- who can authorize rollback and who handles user communication;
- the maximum decision and restoration time for the controlled pilot.

## Window Exit Report

The retained report must include:

1. environment list and observation timestamps;
2. active teaching days covered;
3. POST and GET request summaries;
4. caller inventory and migration confirmations;
5. queue/running/retrying daily series and final snapshot;
6. worker activity and stale-job disposition report;
7. lifecycle-integrity results;
8. migration notice version;
9. worker shutdown rehearsal result;
10. rollback owners and approval decision.

Only a complete report can support a future deprecation execution decision.
Until then:

```text
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
