# Legacy Alignment Controlled Freeze Rollback

## Ownership

- Target environment: `pilot-internal-local`
- Change owner: Project Maintainer
- Rollback owner: Project Maintainer
- Incident/support path: Project Maintainer pilot coordination channel
- Current authorization: observation `ACTIVE`; Freeze requires separate approval

```text
LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE
ROLLBACK_READY_FREEZE_NOT_EXECUTED
```

The Project Maintainer is the decision and execution owner for this
single-person controlled Pilot. A hosted or multi-operator environment must
replace this assignment with named operational contacts.

## Preconditions

1. record the target environment, database, application instances, and worker
   processes;
2. capture a read-only Legacy queue snapshot;
3. confirm Formal API and Formal worker health;
4. confirm no competing Legacy worker is active before changing worker state;
5. retain the approved trigger and rollback decision owner.

## Freeze

Set and deploy:

```text
LEGACY_ALIGNMENT_RUNTIME_STATE=freeze
LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=false
```

Restart affected application and Legacy worker processes. Verify Legacy POST
returns HTTP 503 `LEGACY_ALIGNMENT_ADMISSION_DISABLED`, internal helper/job
creation is rejected, history GET remains available, and Formal admission and
workers continue normally.

## Drain And Shutdown

1. capture queued, running, retrying, and failed counts;
2. classify running jobs and confirm former owners are stopped;
3. set runtime state to `draining` while admission remains false;
4. run exactly one `--mode legacy-alignment` worker;
5. wait for queued/retrying work or use the reviewed fenced safe-failure action;
6. require queued, running, and retrying counts to reach zero;
7. set runtime state to `disabled` and stop the Legacy worker;
8. keep Formal workers running.

Never delete, blindly replay, or migrate a Legacy job into Formal Workflow.

## Rollback To Active

Rollback is allowed only while the compatibility route remains present:

1. confirm no old Legacy worker remains active;
2. set `LEGACY_ALIGNMENT_RUNTIME_STATE=active`;
3. set `LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=true`;
4. restart affected application processes;
5. issue one authorized local-provider compatibility probe;
6. require the probe to create exactly one linked run/job and return HTTP 200;
7. start at most one dedicated Legacy worker if queue processing is required;
8. record the reason, owner, timestamps, queue deltas, and affected callers;
9. restart the full observation window.

Do not requeue a safely failed or uncertain running job as part of rollback.

## Verified Rehearsal

The isolated `2026-07-22` rehearsal verified:

- Freeze POST returned 503 and created no Legacy records;
- helper/job-factory creation was blocked;
- queued and running counts drained to zero;
- Legacy claim stopped in Disabled;
- Active restoration allowed an HTTP 200 Legacy creation;
- Formal contracts remained unchanged.

The rehearsal used temporary SQLite and did not validate a target process
manager or target-database rollback. Day 0 now records the authoritative local
Pilot database, manual process identities, and Project Maintainer ownership;
an operational Freeze has still not occurred.

```text
LEGACY_ALIGNMENT_ROLLBACK_REHEARSAL_PASS
TARGET_ENVIRONMENT_ROLLBACK_PENDING
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
