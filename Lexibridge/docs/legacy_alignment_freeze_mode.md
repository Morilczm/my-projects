# Legacy Alignment Freeze Mode

## State Machine

```text
ACTIVE -> FREEZE -> DRAINING -> DISABLED
   ^                                |
   `------------- rollback --------'
```

| State | New `AlignmentRun`/job | Legacy worker claim | History reads | Purpose |
|---|---:|---:|---:|---|
| `ACTIVE` | allowed when route admission flag is true | allowed | allowed | compatibility window before freeze |
| `FREEZE` | blocked | paused | allowed | establish counts and classify running work |
| `DRAINING` | blocked | allowed through dedicated worker | allowed | complete queued/retrying work only |
| `DISABLED` | blocked | paused | allowed | hold zero active queue after drain |

`LEGACY_ALIGNMENT_RUNTIME_STATE` defaults to `active`. Creation additionally
requires `LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=true`; setting that flag to
false closes creation even if the state is still Active.

## Operator Sequence

1. Confirm Formal Workflow is healthy and external-consumer observation is
   running.
2. Set route admission false and runtime state to `freeze`.
3. Restart the affected application/worker processes so configuration is
   authoritative.
4. Inspect without writes:

   ```bash
   python scripts/legacy_alignment_runtime.py status
   ```

5. Resolve each running job by waiting, approved cancel/reconciliation, or the
   fenced safe-failure process.
6. Set runtime state to `draining` and run exactly one dedicated worker:

   ```bash
   python scripts/run_worker.py --mode legacy-alignment
   ```

7. Require queued, running, and retrying counts to remain zero.
8. Set runtime state to `disabled`, stop the Legacy worker, and keep history
   reads available.

## Safe-Failure Boundary

The operator tool defaults to dry-run:

```bash
python scripts/legacy_alignment_runtime.py safe-fail \
  --job-id JOB_ID \
  --expected-locked-by WORKER_ID \
  --stale-before ISO_TIMESTAMP \
  --actor OPERATOR_ID
```

Apply additionally requires all of the following:

- `LEGACY_ALIGNMENT_RUNTIME_STATE=freeze` or `draining`;
- creation admission closed;
- `LEGACY_ALIGNMENT_SAFE_FAILURE_APPLY_ENABLED=true`;
- explicit `--apply`;
- matching owner fence and stale cutoff;
- a non-terminal linked `AlignmentRun`.

Apply atomically fails the Job and linked Run, appends a sanitized JobEvent,
and writes an `AuditRecord`. It never migrates or requeues work.

## Rollback

Rollback requires a named owner, zero competing Legacy worker processes, and
an incident record. Restore Active plus route admission true, then restart at
most one dedicated Legacy worker. Do not replay a safely failed or uncertain
running job.

Freeze readiness does not establish external-consumer absence or authorize
HTTP 410.

```text
LEGACY_ALIGNMENT_FREEZE_READY
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
