# Legacy Alignment Migration Notice

## Notice Status

- Audience: controlled Pilot operator and known Legacy alignment client owners
- Publication status: `DISTRIBUTED`
- Distribution UTC: `2026-07-22T15:17:39Z`
- Recipient scope: Project Maintainer / controlled Pilot operator
- Distribution channel: shared release branch and Task 9C.5O.3 operational handoff
- Distribution owner: Project Maintainer
- Observation environment: `pilot-internal-local`
- Observation start: `2026-07-22T15:13:47Z`
- Earliest review UTC: `2026-08-05T15:13:47Z`

The distribution record covers the known single-person controlled Pilot. No
external client-owner list exists, so it is not evidence that repository-
external consumers are absent. This notice does not announce retirement, HTTP
410, route removal, or a committed retirement date.

## Legacy API Status

`POST /api/alignment/run` remains a deprecated active compatibility surface.
Its URL, method, permissions, request, response, and local compatibility
behavior remain unchanged. External provider execution remains disabled.

The read-only history surfaces remain active:

- `GET /api/alignment/runs`;
- `GET /api/alignment/runs/{run_id}`;
- `GET /api/admin/alignment-runs`.

## Supported Replacement

New teacher workflows must use:

- `POST /api/document-alignment-runs`;
- `GET /api/document-alignment-runs/{run_uid}`;
- `GET /api/document-alignment-runs/{run_uid}/items`.

Clients must preserve Formal permission, source identity, Idempotency-Key,
polling, and server-side pagination contracts. They must not fall back to the
Legacy POST when a Formal request fails.

## Observation Timeline

The observation window is active from `2026-07-22T15:13:47Z`. Review cannot
occur before 14 continuous calendar days and five actual operating days have
retained evidence. Any unexplained Legacy creation, incomplete drain, caller
uncertainty, rollback, or Formal regression extends or restarts the relevant
evidence interval.

## Client Action

Known Legacy POST client owners must:

1. identify the client, environment, schedule, and owner;
2. migrate execution to the Formal API;
3. confirm whether Legacy history reads remain necessary;
4. report blocked migration before observation review.

Do not put credentials, tokens, prompts, outputs, or request payloads into
migration evidence.

## Contacts

- Observation owner: Project Maintainer
- Rollback owner: Project Maintainer
- Support owner/contact path: Project Maintainer pilot coordination channel

```text
LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE
EXTERNAL_CONSUMER_VISIBILITY_LIMITED
LEGACY_ALIGNMENT_410_NOT_AUTHORIZED
```
