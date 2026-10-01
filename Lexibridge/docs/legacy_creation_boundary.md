# Legacy Alignment Creation Boundary

## Purpose

This matrix classifies every repository entry that can create an
`AlignmentRun` or an `alignment_run` `BackgroundJob`. It prepares admission
control without deleting an entry or returning HTTP 410.

## Creation Matrix

| Entry | Location | Can create new job | Current purpose | Classification | Action |
|---|---|---:|---|---|---|
| `POST /api/alignment/run`, async | `backend/app.py` `run_alignment()` | yes | active legacy API compatibility | Production compatibility | keep enabled during observation; gate first at cutover |
| `POST /api/alignment/run?sync=true`, direct term | `backend/app.py` `run_alignment()` | no; creates run/cards directly | synchronous legacy compatibility | Production compatibility | same route gate; do not retain as a bypass |
| `POST /api/alignment/run?sync=true`, document | `backend/app.py` `run_alignment()` | no; helper creates run/cards | synchronous legacy compatibility | Production compatibility | same route gate; do not retain as a bypass |
| `POST /api/documents/upload?sync=true` | `backend/app.py` upload sync branch | no; may invoke helper | old synchronous upload behavior | Migration only | identify remaining callers, then remove helper call in a separate contract task |
| `run_alignment_for_chunks()` | `backend/app.py` | no; creates run/cards | shared legacy helper used by sync paths and queued execution | Migration only | retire only after all callers are migrated or drained |
| queued document legacy processing | `backend/app.py` `process_alignment_job()` | consumes a job and reuses its linked run | queued compatibility execution | Migration only | preserve until queue drain and run-identity audit |
| `scripts/run_demo_flow.py` | demo seeding | creates terminal records | local demonstration data | Test only | migrate demo data separately from production admission |
| `scripts/pilot_readiness_check.py` | containment probe | creates isolated test records | release safety evidence | Test only | retain until deprecation contract changes |
| tests and fixtures | `tests/` | creates isolated records | characterization and regression | Test only | convert deliberately at future deprecation/removal |
| admin action | repository scan | no entry found | none | Obsolete | no implementation to remove |
| external caller | outside repository | potentially through legacy POST | unknown | Production compatibility | observe and identify owner |

The Formal Workflow frontend and Formal API do not create `AlignmentRun` or
`alignment_run` jobs.

## Admission Control

`LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED` is a default-enabled, server-owned
environment flag. When set to `false`, authenticated legacy POST requests
return HTTP 503 with `LEGACY_ALIGNMENT_ADMISSION_DISABLED` before request-mode
parsing or any domain write. The path, method, permissions, and enabled-state
response remain unchanged. Re-enabling the flag restores route admission
without changing Formal Workflow.

Recommended future cutover sequence:

1. complete the external-consumer observation window;
2. publish the migration notice and name rollback owners;
3. set `LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=false` in one controlled
   environment;
4. prove POST attempts create no `AlignmentRun`, job, event, or card;
5. drain queued/retrying work with the explicit legacy worker;
6. reconcile running jobs under the approved shutdown plan;
7. verify all creation paths, including sync upload, are closed or explicitly
   retained before considering HTTP 410.

Task 9C.5N.2 supersedes the earlier route-only limitation. The same admission
decision now covers sync upload, direct helper calls, and the legacy job
factory. Drain execution may reuse an existing linked run but cannot create a
replacement run outside Active:

```text
LEGACY_ALIGNMENT_CREATION_FREEZE_BOUNDARY_COMPLETE
```

## Migration Strategy

- Production compatibility callers migrate to the Formal Workflow API.
- Migration-only sync/helper callers receive a separate boundary task; they
  must not silently fall back to the legacy route.
- Test-only creators remain isolated evidence until the future contract is
  approved.
- Obsolete entries are removed only after retained data/read surfaces are
  classified.

No frontend, database schema, Formal API, or existing run/job record is
changed by this preparation.
