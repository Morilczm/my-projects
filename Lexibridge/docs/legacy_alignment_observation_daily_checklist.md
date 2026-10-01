# Legacy Alignment Observation Daily Checklist

Use one copy of this checklist for every actual operating day in
`pilot-internal-local`. Store generated logs and snapshots outside Git and link
them by non-secret artifact ID. Day 0 is recorded separately and does not count
as an operating day.

## Daily Identity

- Observation start: `2026-07-22T15:13:47Z`
- Provisional review threshold: `2026-08-05T15:13:47Z`
- UTC date:
- Operating day number:
- Collection start/end UTC:
- Operator: Project Maintainer
- Application commit:
- Database snapshot ID:
- Evidence artifact IDs:

## Runtime Health

- [ ] Application process identity and health recorded.
- [ ] Formal worker identity, mode, and health recorded.
- [ ] Legacy worker identity is recorded as stopped or intentionally active.
- [ ] External provider requests remain zero.
- [ ] Application and worker logs remain readable and retained.
- [ ] Pre-start or unrelated diagnostics are excluded by timestamp.

## Legacy Traffic

| Signal | Count | Caller/result classification | Evidence ID |
|---|---:|---|---|
| `POST /api/alignment/run` | | | |
| `GET /api/alignment/runs` and detail | | | |
| Admin Legacy history GET | | | |
| Sync upload creation path | | | |
| Internal AlignmentRun creation | | | |
| Legacy BackgroundJob creation | | | |

- [ ] Every Legacy POST and creation signal is attributed or escalated.
- [ ] Unauthenticated test probes are distinguished from Pilot callers.
- [ ] No request body, credential, prompt, output, or private evidence is stored.

## Queue And Worker

| Signal | Start | End | Notes |
|---|---:|---:|---|
| queued Legacy jobs | | | |
| running Legacy jobs | | | |
| retrying Legacy jobs | | | |
| failed Legacy jobs | | | |
| Legacy worker claims | | | |
| Legacy completions | | | |
| Legacy failures | | | |

- [ ] Oldest active age and lifecycle-integrity result recorded.
- [ ] Every running/retrying job has an owner and disposition.
- [ ] No orphan cleanup, replay, migration, or deletion was improvised.

## Formal Workflow

- [ ] Formal run creation succeeds.
- [ ] Formal worker execution and terminal state are verified.
- [ ] Lease, heartbeat, stale reclaim, fencing, and retry behavior remain intact.
- [ ] Formal frontend artifact reports `legacy_alignment_requests=0`.
- [ ] Browser console errors, page errors, and external provider requests are 0.

## Freeze, Rollback, And Incidents

- Freeze state: not executed / active / recovered
- Rollback used: yes / no
- Incident or caller-support record:
- Observation interval restart required: yes / no
- Rollback decision owner and UTC:

Freeze is never implied by observation. Use the approved Freeze checklist and
rollback procedure for any state change.

## Daily Sign-Off

- [ ] Required metrics have retained evidence.
- [ ] External-consumer status remains evidence-based, not assumed.
- [ ] Any gap or `LOG_RETENTION_LIMITED` incident is recorded.
- [ ] This date qualifies as an actual operating day.
- Operator sign-off:
- UTC sign-off time:

Review remains blocked until at least 14 continuous calendar days and five
signed operating days exist, with queue, caller, rollback, and Formal evidence
reviewed by the assigned owner.
