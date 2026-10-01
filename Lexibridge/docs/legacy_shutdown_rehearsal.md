# Legacy Alignment Shutdown Rehearsal

## Rehearsal Record

- Task: `9C.5N.2`
- Date: `2026-07-22`
- Environment: isolated temporary SQLite and upload directory
- Production data: not accessed
- External provider requests: none
- Command: `python scripts/run_legacy_alignment_shutdown_rehearsal.py --json-output <temporary-artifact>`
- Verdict: `PASS`

## Scenario

The rehearsal created two isolated compatibility jobs while Active:

- one queued local deterministic job;
- one stale running job owned by a simulated stopped worker.

It then executed the approved transition sequence:

1. `FREEZE`: route admission false, new job creation rejected, Legacy claim
   paused, HTTP POST returned the migration 503 with zero new records, and the
   queue snapshot recorded one queued and one running job;
2. safe failure: owner and stale cutoff matched, Job and linked Run became
   failed, one JobEvent and one AuditRecord were written;
3. `DRAINING`: the dedicated Legacy worker completed the queued job while
   reusing its linked `AlignmentRun`;
4. queue verification: queued, running, and retrying counts reached zero;
5. `DISABLED`: Legacy claim remained paused;
6. rollback rehearsal: Active and route admission were restored, and an
   authorized Legacy POST returned HTTP 200;
7. Formal contract constants remained
   `formal-document-alignment-v1` and
   `formal_document_alignment_workflow_v1`.

## Verified Controls

| Control | Result |
|---|---|
| New Legacy creation blocked in Freeze | PASS |
| Freeze HTTP migration response and zero creation | PASS |
| Freeze does not claim queued Legacy work | PASS |
| Queue snapshot reports queued/running/retrying/failed | PASS |
| Safe failure owner fence and stale cutoff | PASS |
| Job/Run safe failure is atomic | PASS |
| Safe failure JobEvent and AuditRecord | PASS |
| Dedicated drain completes existing queued work | PASS |
| Drain creates no replacement `AlignmentRun` | PASS |
| Disabled state pauses Legacy claim | PASS |
| Active rollback restores admission | PASS |
| Active rollback restores HTTP creation | PASS |
| Formal Workflow contract unchanged | PASS |

## Limitations

This rehearsal proves repository tooling against an isolated non-production
database. It does not prove target-environment queue counts, identify external
consumers, rehearse process-manager commands, assign production rollback
owners, or complete the observation window. Those remain retirement gates.

```text
LEGACY_ALIGNMENT_SHUTDOWN_REHEARSAL_PASS
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
