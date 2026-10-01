# Formal Document Alignment HTTP API

Status: `FORMAL_DOCUMENT_ALIGNMENT_API_END_TO_END_VERIFIED`

Scope: SQLite, single-node, deterministic-provider small pilot. This document
does not claim frontend cutover, PostgreSQL validation, live-provider
readiness, distributed-worker behavior, or production deployment.

## Endpoints

| Method | Path | Endpoint | Success |
|---|---|---|---|
| POST | `/api/document-alignment-runs` | `create_document_alignment_run` | `202 Accepted` |
| GET | `/api/document-alignment-runs/{run_uid}` | `get_document_alignment_run` | `200 OK` |
| GET | `/api/document-alignment-runs/{run_uid}/items` | `list_document_alignment_run_items` | `200 OK` |

All three routes are registered with `app.add_url_rule` from
`backend/routes/document_alignment_workflow_routes.py`. The module has no ORM,
transaction, worker, provider, or transport responsibility.

## Start Contract

The caller must be an authenticated teacher or administrator and must send:

```http
Idempotency-Key: 1..128 printable characters
Content-Type: application/json
```

```json
{"source_uid": "governed-source-uid"}
```

Unknown fields, body actor/role values, body idempotency values, malformed JSON,
and non-JSON content are rejected. Workflow version, provider, candidate limit,
job type, worker, and execution settings are server-owned.

The server resolves and freezes the deterministic local provider identity when
Admission creates a Run. The current pilot identity is `mock-rule-v1`, model
`mock-rule-v1:v1`, and prompt `alignment-v1`; none is accepted from HTTP input
or exposed as credential-bearing provider configuration. Historical Runs
without a frozen selection fail closed during processing and are not silently
backfilled.

Creation and replay both return `202`, the canonical status `Location`, fixed
`Retry-After: 2`, `X-Request-ID`, and the normal API envelope. Replay returns
the same run with `reused: true`; canonical payload drift under the same scope
returns `409`. The scope is requesting actor + source UID + workflow version +
Idempotency-Key. Reusing the same key for a different source creates a distinct
Run rather than a conflict. The response never includes a job UID or transport
state.

## Read Contract

The run route returns the safe query-service summary. The item route accepts
only `page`, `page_size`, `status`, and `reviewable_only`. Page numbering starts
at 1, the default page size is 20, and the maximum is 100. Boolean values are
exact lowercase `true` or `false`; status uses the formal item allowlist.
Pagination and ordering occur in SQL using item database identity followed by
`item_key`, while database integer IDs remain hidden from the response.

Administrators may read all runs. The requesting teacher and an active teacher
authorized for the governed course may read. Unrelated teachers receive the
same `404` as an absent run. Students and anonymous callers are denied. Student
access remains limited to the existing approved-only Concept Card APIs.

## Error Mapping

| Outcome | HTTP |
|---|---:|
| Invalid JSON, header, body, pagination, filter | 400 |
| Anonymous or invalid authentication | 401 |
| Authenticated role not allowed | 403 |
| Missing or anti-enumerated source/run | 404 |
| Admission idempotency conflict | 409 |
| Non-JSON POST | 415 |
| Governance, parse quality, or usable-chunk admission block | 422 |
| Safe persistence/internal failure | 500 |

Errors use the existing `status/error_code/message/request_id` envelope. Error
messages are bounded to 500 characters and pass a final secret/trace sanitizer.

## Security Boundary

Run and item resources exclude job UID, payload, worker, attempt, heartbeat,
lease, token, execution key, input fingerprint, preflight/usage/audit identity,
raw chunks, evidence, prompts, provider output, credentials, absolute source
paths, and database integer IDs. Actor identity comes only from the existing
bearer-auth context. The routes do not widen CORS, disable authentication, or
provide debug role overrides.

## Transaction Boundary

POST delegates all workflow-root, transport-envelope, and request-audit writes
to `start_document_alignment_workflow`, which owns one commit and rollback.
GET routes delegate to read-only query services. Routes do not commit, rollback,
flush, repair progress, run a worker, or invoke a provider.

## OpenAPI And Non-Guarantees

`docs/openapi.yaml` defines authentication, the idempotency header, strict body,
`202` and response headers, run/item schemas, bounded pagination, status enums,
and safe errors. Parsed-YAML tests compare these operations to Flask runtime
registration and formal constants.

Task 9C.5G v3 validates real HTTP start, formal worker execution, polling,
pagination, source-scoped and concurrent replay, partial/all-blocked outcomes,
retry/crash/terminal recovery, permissions, and authenticated same-origin
browser fetch. The evidence is local SQLite and single-node only. The frontend
continues to use the contained legacy endpoint until a later cutover task.

## Transport Retry Policy

The POST body remains limited to `source_uid`. Clients cannot choose or inspect
`max_attempts`, `attempt_count`, `execution_attempt`, worker identity, or lease
state. Admission freezes new formal V1 jobs at three counted
processing-failure outcomes, allowing at most two successful requeues. Idempotent replay
reuses the original job and never resets its stored policy or counters.
Historical jobs keep their creation-time value. Pre-outcome crash/reclaim
generations are not counted and have no separate V1 persisted cap. This local
policy does not make provider execution exactly-once and remains unverified on
PostgreSQL and distributed workers.
