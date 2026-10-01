# Legacy Alignment Runtime Isolation

## Decision

- Task: `9C.5N.1`
- Baseline: `e58982d216d9d2977abc5c91f35a2b1c7429ade8`
- Branch: `release/pilot-v1-candidate`
- Target state: `LEGACY_ALIGNMENT_RUNTIME_ISOLATED`
- HTTP 410 authorization: not granted

This boundary separates queue ownership. It does not delete the legacy route,
alter the Formal Workflow contract, change the database schema, or make a
stale legacy job safe to rerun.

## Topology Before

```text
scripts/run_worker.py
  |-- Formal CAS claim: formal_document_alignment_workflow_v1
  `-- generic non-formal claim
        |-- document_ingestion
        |-- evaluation_run
        `-- alignment_run
```

One process alternated Formal and non-formal claims. Consequently, every
default local worker was also a legacy alignment worker.

## Topology After

```text
scripts/run_worker.py --mode standard       -> Formal + generic only
scripts/run_worker.py --mode formal         -> Formal only
scripts/run_worker.py --mode generic        -> ingestion + evaluation only
scripts/run_worker.py --mode legacy-alignment -> alignment_run only
```

The default `standard` mode never invokes the legacy alignment dispatcher.
Legacy queue consumption requires an explicit process mode. The default may
also be selected with `JOB_WORKER_QUEUE_MODE`; the command-line argument takes
precedence.

## Routing Rules

| Worker mode | Owned job types | Explicitly excluded |
|---|---|---|
| `standard` | `formal_document_alignment_workflow_v1`, `document_ingestion`, `evaluation_run` | `alignment_run` |
| `formal` | `formal_document_alignment_workflow_v1` | all non-formal jobs |
| `generic` | `document_ingestion`, `evaluation_run` | formal and `alignment_run` |
| `legacy-alignment` | `alignment_run` | formal, ingestion, and evaluation |

`claim_next_background_job()` retains its unfiltered compatibility behavior
for direct callers and existing tests. Operational worker modes use the new
filtered claim wrappers. Unsupported filtered job types fail closed with
`ValueError`.

## Formal Workflow Protection

The following Formal Workflow boundaries are unchanged:

- API paths and response contracts;
- workflow version `formal-document-alignment-v1`;
- job type `formal_document_alignment_workflow_v1`;
- idempotency scope;
- CAS lease ownership, heartbeat, stale reclaim, fencing, and retry budget;
- `RouteCoreDependencies`.

Formal dispatch continues through `run_formal_worker_once()`. No legacy
dispatcher, route flag, or legacy model was added to that call chain.

## Legacy Runtime Boundary

The explicit legacy process uses:

```text
claim_next_legacy_alignment_job()
  -> claim_next_background_job(job_types={alignment_run})
  -> run_background_job()
  -> process_alignment_job()
```

This is queue-family isolation, not lifecycle hardening. Legacy claims still
have no heartbeat, stale reclaim, lease token, ownership fencing, or automatic
run/job reconciliation. A job already in `running` is not reclaimed by the
new mode.

## Operating Rules

1. Run `standard`, `formal`, or `generic` workers for the supported pilot
   runtime.
2. Start `legacy-alignment` only under an identified compatibility or drain
   owner.
3. Do not run more than one legacy worker until claim ownership is hardened.
4. Before stopping the legacy worker, follow
   `docs/legacy_running_job_shutdown_plan.md`.
5. Do not infer HTTP 410 readiness from process isolation.

## Result

The default runtime no longer expands or executes the legacy queue. Legacy
execution remains available in a separately controllable process for the
compatibility and drain window.

```text
LEGACY_ALIGNMENT_RUNTIME_ISOLATED
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
