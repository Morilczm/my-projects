# Formal Document Alignment Query Services

Status: `FORMAL_DOCUMENT_ALIGNMENT_QUERY_SERVICES_ESTABLISHED`

Task: 9C.5E

Scope: HTTP-neutral, read-only service contract for the local SQLite pilot.

## Boundary

`backend/services/document_alignment_workflow_queries.py` reads
`DocumentAlignmentWorkflowRun`, `DocumentAlignmentWorkflowItem`, and a bounded
`KnowledgeSource`/course authorization summary. It does not register a route,
start a worker, invoke processing, call a provider, or mutate database state.
`WorkflowRun` is the business-status source of truth; transport ownership and
payload details are deliberately outside these DTOs.

Task 9C.5D remains valid: the generic worker excludes the formal job type, the
formal dispatcher uses CAS claim/lease ownership, and the formal handler only
maps a strict payload to the processing orchestrator and terminal/retry
ownership operations. Query code does not repair Root/Job divergence.

## Permission Policy

| Actor | Run | Items | Draft/verification UID | Safe error |
|---|---:|---:|---:|---:|
| Admin | yes | yes | yes | yes |
| Requesting teacher | yes | yes | yes | yes |
| Active course teacher/owner/admin member | yes | yes | yes | yes |
| Unrelated teacher | no | no | no | no |
| Student | no | no | no | no |
| Anonymous | no | no | no | no |

Private/personal sources additionally require ownership for non-admin actors.
Unauthorized and absent runs both return the service outcome `not_found`; this
is the V1 anti-enumeration policy. Students continue to use only the existing
approved-card APIs.

## Contracts

`DocumentAlignmentQueryActor` contains only `actor_uid` and `role`.

`DocumentAlignmentWorkflowRunSummary` exposes stable run/source display data,
business status/stage, persisted counts, computed progress, bounded safe error,
terminal/review flags, and consistency warnings. It excludes database IDs and
all job ownership, payload, lease, heartbeat, and worker fields.

`DocumentAlignmentWorkflowItemSummary` exposes item UID, candidate term,
status/stage, source reference count, normalized risk labels, safe card and
verification UIDs, persisted confidence/recommendation, bounded safe error,
retry count, timestamps, and consistency warnings. It excludes item keys,
chunk IDs/text, evidence, candidate provenance, execution identities,
preflight/usage/audit identities, prompts, and provider output.

## Progress

For a non-terminal run with items:

```text
floor((ready_for_review_items + blocked_items + failed_items) * 100 / total_items)
```

The value is clamped to 0-100. A terminal root returns 100. A non-terminal
root with no items returns 0. Progress is computed at read time and never
persisted by the query service.

## Pagination And Filters

- Pages are one-based.
- Default page size: 20.
- Maximum page size: 100.
- Ordering: `WorkflowItem.id`, then `item_key`.
- V1 filters: one allowlisted item status and `reviewable_only`.
- `reviewable_only` means `needs_review` only.
- An out-of-range page returns an empty tuple.

The service uses a SQL count plus `ORDER BY`/`LIMIT`/`OFFSET`; it does not load
all items for Python pagination. Query-count tests prove run query count is
independent of 1/10/50 items and item-page query count is bounded without
per-item card or verification queries.

## Safety And Consistency

Safe error messages are capped at 500 characters and credential/header-shaped
content is replaced by a generic summary. Display filenames are reduced to the
basename. Legal course text is not removed merely because it contains words
such as `password` or `token`.

The service reports `DOCUMENT_ALIGNMENT_QUERY_DATA_INCONSISTENT` for impossible
root counts, terminal roots with non-terminal items, or item status/reference
contradictions. It does not repair counts, statuses, or references. Queries use
`no_autoflush`; no commit, heartbeat, lease fence, or business write occurs.

## Limitations

- Task 9C.5F exposes these DTOs through formal HTTP routes and OpenAPI. Task
  9C.5G v3 verifies HTTP polling and browser-session access; frontend polling
  is not complete.
- SQLite query behavior is covered; PostgreSQL plans and permissions are not.
- No admin transport diagnostics are exposed.
- The local worker is not a supervised production runtime.
- Production migrations, live providers, and multi-host operation remain out
  of scope.

The next permitted slice is Task 9C.5H, Formal Workflow Frontend Cutover and
Legacy-Independent Teacher Experience.
