# Legacy Alignment Run Boundary

Status:
- `CHARACTERIZED`
- `DEPRECATION_POLICY_ACCEPTED`
- `EXTERNAL_EXECUTION_DISABLED`
- `WORKER_EXTERNAL_EXECUTION_DISABLED`
- `EXISTING_EXTERNAL_JOBS_QUARANTINED`
- `FORMAL_REPLACEMENT_IMPLEMENTED`
- `FRONTEND_POST_CONSUMER_MIGRATED`
- `CONSUMER_AUDIT_COMPLETE`
- `EXTERNAL_CONSUMERS_UNKNOWN`
Tasks: 9C.4S through 9C.5L
Current release baseline: `8ba533ab43fc36e952268c5ea385397778b6fbd5`
Main conclusion: `DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`
Deprecation policy after Task 9C.4T:
`LEGACY_ALIGNMENT_RUN_DEPRECATION_V1`
External containment after Task 9C.4U:
`LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED`
Replacement contract after Task 9C.4V:
`FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`
Replacement contract conclusion:
`FORMAL_WORKFLOW_MODELS_REQUIRED_FIRST`
Replacement model status after Task 9C.4W:
`FORMAL_WORKFLOW_MODELS_ESTABLISHED`
Consumer audit result after Task 9C.5L:
`LEGACY_ALIGNMENT_CONSUMER_BOUNDARY_IDENTIFIED`

This document freezes the current behavior of `POST /api/alignment/run` and
records the Phase 1 containment boundary. Task 9C.4V defines the formal
replacement workflow contract in
`docs/formal_document_alignment_workflow_boundary.md` and
`docs/adr/ADR-formal-document-alignment-workflow.md`. Tasks through 9C.5K
implement and verify that replacement and migrate the production teacher POST
consumer. Task 9C.5L confirms that the legacy route is still not safe to remove
because legacy worker/tests/safety probes and unknown external consumers remain.

## Route Registration

| Concern | Current behavior |
|---|---|
| URL | `/api/alignment/run` |
| Method | `POST` |
| Flask endpoint | `run_alignment` |
| Registration | `@app.route("/api/alignment/run", methods=["POST"])` |
| File | `backend/app.py` |
| Handler lines | `11048` through `11232` |
| Handler size | 185 lines including decorator, 184 function lines |
| Duplicate rule | none |
| Route module | none |
| OpenAPI | listed in `docs/openapi.yaml` |
| Frontend | no production POST call; `GET /api/alignment/runs` historical list remains active |

The route remains an active compatibility surface, but it is no longer a
production frontend POST surface. It is not an alias for
`POST /api/alignment/verify` or the formal document workflow.

Task 9C.4U keeps the route in `backend/app.py`, keeps the URL/method/endpoint,
and adds a fail-closed provider classification gate before any legacy external
provider execution can start.

## HTTP Contract

| Concern | Current behavior |
|---|---|
| Authentication | required bearer token |
| Roles | `student`, `teacher`, `admin` |
| Reviewer role | rejected with `PERMISSION_DENIED` |
| Query | `sync=true`, `sync=1`, or `sync=yes` runs synchronous behavior |
| Body | `request.get_json() or {}` |
| Empty body | teacher/admin receive course-scope `PERMISSION_DENIED` before missing-term validation |
| Malformed JSON | Flask 400 before route handling |
| Non-object JSON | unhandled route exception, API 500 under non-propagating Flask config |
| Required runtime fields | `english_term` or `document_id`, after scope/course permission checks |
| Scope | `course` or `personal`, default `course` |
| Unknown fields | ignored except known `courseware_sentence`, `chapter`, `course_id`, `course_name`, `document_id`, `english_term`, `scope_type` |
| Success async status | 200 |
| Success sync direct status | 200 |
| Success sync document status | 200 |
| Success request_id | absent |
| Error request_id | absent for this legacy route |
| AuditRecord | none from the route |

Response envelopes differ by branch:

| Branch | Response shape |
|---|---|
| Async default | `api_success({"alignment_run_id", "job_id", "job_type", "job_status", "run", "job"}, "术语对齐任务已进入后台队列。")` |
| Sync document | raw `jsonify({"status": "success", "message": "文档术语对齐已完成。", "cards": [...]})` |
| Sync direct term | raw `jsonify({"status": "success", "message": "术语证据对齐已完成。", "alignment": ..., "card": ...})` |

## Frontend And OpenAPI

The production teacher document action now uses the formal workflow API and
does not call or fall back to `POST /api/alignment/run`. The old response
expectations below remain frozen for compatibility tests and possible external
clients:

- async queued responses contain `data.job_id`;
- non-queued success responses have `status=success`.

OpenAPI lists only a small request schema:

- `document_id`
- `english_term`
- `course_id`
- `scope_type`

Runtime also reads `course_name`, `courseware_sentence`, `chapter`, and the
`sync` query parameter. OpenAPI does not describe the three distinct response
shapes.

After Task 9C.4U, OpenAPI marks the route `deprecated: true` and documents
`LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED`. It still does not return HTTP
410 and does not claim that the replacement workflow exists.

### Frontend Migration Checklist

Current frontend dependency:

| Concern | Current dependency |
|---|---|
| File | `frontend/index.html` |
| Function | `loadAlignmentRuns()` for legacy history; formal start lives in `frontend/js/formal-workflow.js` |
| UI entry | Teacher/admin document row action button |
| Route | `GET /api/alignment/runs` only; no production legacy POST |
| Payload | none for the remaining GET list |
| Success follow-up | historical runs populate `state.cache.alignmentRuns` |
| Formal start | `POST /api/document-alignment-runs` with server-owned `source_uid` |
| Formal polling/items | formal run GET plus paginated formal items GET |
| Error display | formal API failure remains formal; there is no legacy fallback |
| Legacy list dependency | `/api/alignment/runs` remains loaded after run |
| Job dependency | `/api/jobs` displays `job.alignment_run_id` |

Completed cutover checklist:

1. replacement backend workflow and contract tests are implemented;
2. replacement E2E coverage is active;
3. the document action uses the replacement endpoint;
4. job/result polling uses formal Run and Item records rather than legacy
   `AlignmentRun`;
5. static checks prove production frontend legacy POST references are zero;
6. browser E2E proves requests to the legacy POST are zero;
7. disabling or returning 410 remains a separate task after external-consumer
   and queued-job policy approval.

Task 9C.4V defines the replacement frontend target as the formal API family:

- `POST /api/document-alignment-runs`
- `GET /api/document-alignment-runs/{run_uid}`
- `GET /api/document-alignment-runs/{run_uid}/items`

Those routes now exist with formal models, admission, processing, worker,
query, OpenAPI, frontend cutover, and browser verification. The detailed
remaining consumer inventory is in `docs/legacy_alignment_consumer_audit.md`.

## Formal Verification Comparison

| Concern | Legacy `/api/alignment/run` | Formal `/api/alignment/verify` |
|---|---|---|
| Route owner | `backend/app.py` | `backend/routes/alignment_verification.py` |
| Application service | none | `services/alignment_verification_execution.py` |
| Primary run model | `AlignmentRun` | `AlignmentVerificationRun` |
| Card model | `TerminologyCard` | `ConceptAlignmentCard` optional attach |
| Provider policy | not invoked | `evaluate_provider_request(...)` |
| Provider preflight | not invoked | separate readiness route and governance gate |
| Provider usage | no `AlignmentProviderUsageRecord` | one `AlignmentProviderUsageRecord` per verification result |
| Audit | no `AuditRecord` | request/completed/failed/policy/attach events |
| request_id | absent on success and errors | present through audit context |
| Parser | legacy `call_ai_task` JSON validation plus fallback | formal output parser/schema |
| Auto-approve gate | legacy `TerminologyCard` status machine can auto approve live evaluated models | formal provider result cannot auto approve |
| Attach gate | direct `TerminologyCard` create/update | explicit `attach_to_card` plus policy gate |
| Transaction | route/helper owned commits, no explicit route rollback | execution service owns commit/rollback |
| Credential access | legacy provider globals and `ai_selection_from_config` | governed provider registry |
| Network intent | possible for live default provider with API key | guarded by provider policy and disabled external providers |

The two routes are not compatible schemas and do not write the same tables.

## Handler Responsibility Split

| Section | Current location | Reads | Writes | Network risk | Future owner |
|---|---|---:|---:|---:|---|
| HTTP adapter | `run_alignment` | request, auth, course | none | no | route or compatibility adapter |
| Async queue setup | `run_alignment` | document/course/provider metadata | `AlignmentRun`, `BackgroundJob` | no direct network | replacement workflow or compatibility adapter |
| Sync document execution | `run_alignment` + `run_alignment_for_chunks` | `Document`, `DocumentChunk`, evidence | `AlignmentRun`, `TerminologyCard`, optional `UsageRecord` | possible through legacy AI task when provider is real | deprecated or split execution service |
| Sync direct execution | `run_alignment` + `generate_alignment_result` | evidence retrieval, provider metadata | `AlignmentRun`, `TerminologyCard`, `AICallLog`, optional `UsageRecord`, `SystemLog` | possible through live provider | deprecated or split execution service |
| Persistence | route and helpers | many legacy tables | commits in route/helper call chain | no separate safety gate | persistence plan only after deprecation policy |
| Compatibility | route response branches | frontend assumptions | none | no | compatibility policy |

## Provider Selection

Before Task 9C.4U, the legacy route used `current_provider_metadata()` and
`call_ai_task(...)`. Those paths use:

- `ensure_ai_registry_seed(...)`;
- `ai_selection_from_config(...)`;
- module-level provider globals such as `AI_PROVIDER`, `DEEPSEEK_API_KEY`,
  `OPENAI_API_KEY`, and base URLs;
- `provider_from_selection(...)`;
- `urllib.request.urlopen(...)` for OpenAI-compatible live providers.

The route does not accept a formal provider selection payload and does not call
the formal provider registry used by `/api/alignment/verify`.

Task 9C.4U adds `services/legacy_alignment_provider_classification.py`. The
classification helper is pure Python and does not import Flask, routes,
network clients, environment variables, credentials, or database state.

| Provider class | Transitional result |
|---|---|
| `none` / disabled | allowed deterministic local compatibility |
| `mock` | allowed deterministic compatibility |
| `local`, `heuristic`, `local_heuristic` | normalized to `local_heuristic` and allowed |
| `deepseek`, `openai`, `external`, `live`, `custom_openai_compatible` | blocked |
| unknown provider names | blocked |
| substring values such as `mock-deepseek` | blocked |
| custom endpoint/base URL in request metadata | blocked |

The gate uses an explicit allowlist. It does not treat substring matches as
safe and it has no environment, query, debug, or test flag that can re-enable
legacy external execution.

| Condition | Current result |
|---|---|
| No provider configured | local fallback after `AICallLog` error |
| Mock/local provider | local/mock result, requires QC |
| Live provider default with usable key before 9C.4U | live transport intent existed |
| Live provider default with usable key after 9C.4U | HTTP 422 `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` before credential/transport |
| Live transport exception after 9C.4U | no legacy transport is constructed |
| Provider disabled by formal policy | not checked |
| Preflight not ready | not checked |
| Credential missing | legacy provider error/fallback |

## Policy And Preflight

| Condition | Policy invoked | Preflight invoked | Execution attempted | Result |
|---|---:|---:|---:|---|
| Async default request | no | no | no immediate provider execution | queued `AlignmentRun` and `BackgroundJob` |
| Sync direct no provider | no | no | local deterministic metadata | fallback card/result |
| Sync document no provider | no | no | local term extraction plus deterministic alignment per term | cards/result |
| Live provider default after 9C.4U | no | no | none | 422 blocked response or worker terminal failure |
| Formal provider disabled | no | no | not evaluated as formal policy | legacy behavior |

The route bypasses the formal provider governance and preflight chain.

## Evidence And Prompt

Evidence sources:

- direct term path retrieves English and Chinese evidence via
  `retrieve_evidence_results(...)`;
- document path reads `DocumentChunk` rows and extracts terms locally;
- unknown request fields are ignored.

Prompt sources:

- prompt key is `term_alignment`;
- prompt version is `v1`;
- prompt template lookup happens inside legacy `call_ai_task(...)`;
- prompt text is not returned in API responses;
- `AICallLog` stores redacted prompt and response previews for provider calls.

Legal course/evidence text is business data and must not be keyword-redacted as
if it were a credential. Credential-like unknown request metadata is ignored by
the route and was characterized with `LEXIBRIDGE_SENTINEL_SECRET_9C4S`.

## Parser And Result Semantics

Legacy sync direct execution:

- calls `call_ai_task(task_type="term_alignment", ...)`;
- validates the provider result with `validate_ai_json(...)`;
- on any provider failure, catches the exception in `generate_alignment_result`
  and uses a local heuristic fallback;
- finalizes result through `finalize_alignment_result(...)`;
- writes `TerminologyCard` using `create_or_update_card_from_alignment(...)`.

This is not the formal output parser/schema chain. It can create or update
`TerminologyCard` and can auto approve only through the older
`can_use_model_for_auto_approval(...)` and status machine rules when a live,
evaluated model is configured. Formal verification never auto approves a card.

## Execution Matrix

| Path | Provider/policy/preflight | Execution | HTTP/result |
|---|---|---|---|
| Unauthenticated | none | none | 401 `AUTH_REQUIRED` |
| Reviewer | none | none | 403 `PERMISSION_DENIED` |
| Student course request | none | none | 403 `PERMISSION_DENIED` |
| Teacher empty body | none | none | 403 before missing-term validation |
| Invalid scope | none | none | 400 `VALIDATION_ERROR` |
| Malformed JSON | none | none | Flask 400 |
| Non-object JSON | none | none | API 500 when exceptions do not propagate |
| Async direct term | no formal gates | no immediate provider execution | queued `AlignmentRun` and `BackgroundJob` |
| Sync direct term | no formal gates | legacy evidence + deterministic provider metadata | raw success with `alignment` and `card` |
| Sync document | no formal gates | legacy term extraction + card generation | raw success with `cards` |
| Live/default external provider | no formal gates | no execution after 9C.4U | `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` |
| Repeated async request | none | no idempotency | new `AlignmentRun` and new `BackgroundJob` |

## Transport Intent

Characterization blocks `socket.socket`, `urllib.request.Request`, and
`urllib.request.urlopen`.

Findings:

- async local/deterministic request has zero socket/urlopen calls;
- sync direct request with default none/local provider has zero socket/urlopen
  calls and no legacy provider adapter initialization;
- sync document request under default none/local provider has zero socket/urlopen
  calls;
- when a live provider is made the default and an API key is present, the route
  returns `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` before `urllib.Request`,
  `urlopen`, socket, provider selection, adapter construction, or credential
  metadata access.

This containment is intentionally not a service extraction. The legacy route
still bypasses formal policy/preflight/parser/audit and remains a temporary
frontend compatibility surface.

## Route, Worker, And Queued Job Containment

Task 9C.4U closes all currently reachable legacy execution entries:

| Entry | Gate | External/live result | Writes on blocked path |
|---|---|---|---|
| HTTP `POST /api/alignment/run` | request classification before run/job/card creation | HTTP 422 `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` | none |
| `process_alignment_job(...)` | job/run/input classification before marking run running | terminal failed job with `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` | only job failure bookkeeping |
| `/api/jobs/<id>/retry` for quarantined external job | retry guard on failed job error code | HTTP 422, job remains failed | none |
| direct `generate_alignment_result(...)` helper | default provider classification before evidence/provider execution | raises `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` | none |
| direct `run_alignment_for_chunks(...)` helper | default provider classification before `AlignmentRun` creation | raises `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED` | none |

Historical queued/running/retrying jobs with external/live intent are
quarantined by the worker gate when a worker attempts to process them. The
readiness gate counts remaining runnable external legacy jobs and requires
`legacy_external_runnable_jobs_count == 0`.

Blocked route paths do not create `AlignmentRun`, `BackgroundJob`,
`TerminologyCard`, legacy `UsageRecord`, `AICallLog`, formal verification
records, preflight records, concept cards, or audit records. Blocked worker
paths do not create cards, usage, AI call logs, verification runs, concept
cards, or audit records.

The blocked response is not `LEGACY_ALIGNMENT_RUN_DEPRECATED`; the endpoint is
not HTTP 410 while the frontend still calls it.

## Credential Flow

| Source | Current behavior |
|---|---|
| Request body credential-like unknown fields | ignored |
| Module globals on blocked external path | not read for route/worker/direct helper classification |
| Environment on blocked external path | not read by `legacy_alignment_provider_classification` |
| Provider adapter on blocked external path | not initialized |
| Transport on blocked external path | not constructed |
| API response | sentinel not returned in characterization or 9C.4U security tests |
| AuditRecord | no legacy route audit |
| AICallLog | not written on blocked external route/worker paths |
| AlignmentRun/TerminologyCard | sentinel not persisted in characterized fields |

## Write-set Matrix

| Path | AlignmentRun | BackgroundJob | TerminologyCard | AICallLog | UsageRecord | VerificationRun | ProviderUsage | Preflight | Audit | Commit | Rollback |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Unauthorized | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Validation/permission failure | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Blocked external/live HTTP request after 9C.4U | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Blocked external/live worker job after 9C.4U | existing only | existing only terminal failure | 0 | 0 | 0 | 0 | 0 | 0 | 0 | worker commit | worker failure path |
| Async direct term | +1 queued | +1 queued | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| Sync direct term course deterministic | +1 completed | 0 | +1/update | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| Sync direct term personal deterministic | +1 completed | 0 | +1/update | 0 | +1 | 0 | 0 | 0 | 0 | 1 | 0 |
| Sync document deterministic | +1 completed | 0 | +N/update | 0 | optional personal usage | 0 | 0 | 0 | possible parse-risk audit only | 1 | helper exceptions only |
| Repeated async request | +1 each request | +1 each request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 each | 0 |
| Commit failure | unhandled 500 | maybe pending before rollback | pending before rollback | pending before rollback | pending before rollback | 0 | 0 | 0 | 0 | commit raises | no explicit handler rollback |

## Transaction

The route owns direct `db.session.commit()` calls in each branch. It does not
contain an explicit rollback. Helper functions can raise after mutating the
session. Commit failure currently maps to an API 500 only when Flask error
handling is allowed to catch the exception; tests must manually roll back the
session afterward.

The formal verification service differs: it owns explicit rollback in known
failure paths and records typed audit outcomes.

## Usage And Audit

| Concern | Legacy `/api/alignment/run` |
|---|---|
| `AlignmentProviderUsageRecord` | never written by characterized paths |
| Legacy `UsageRecord` | written for personal sync alignment/card paths |
| `AuditRecord` | not written by normal async/direct sync paths |
| Provider usage audit | not written |
| Request audit | not written |
| Card attach audit | not written |
| `request_id` | not attached |

Parse-quality risk propagation inside `create_or_update_card_from_alignment`
can write parse-risk audit records for specific document input risks, but the
route does not create alignment-run audit events.

## Repeated Requests

The route has no idempotency key. Repeating the same async direct-term request
creates another `AlignmentRun` and another `BackgroundJob`. Sync direct requests
can update the same `TerminologyCard` through the legacy normalized term lookup.

## Complexity Metrics

| Metric | Value |
|---|---:|
| Handler lines including decorator | 160 |
| Direct legacy model classes in handler | 5 (`AlignmentRun`, `BackgroundJob` via helper, `Document`, `DocumentChunk`, `Course`) |
| Direct helper/service calls | 12+ |
| Return shapes | 3 success shapes plus multiple error shapes |
| Commit points in handler | 3 |
| Explicit rollback points in handler | 0 |
| Provider execution points | indirect through `generate_alignment_result` and `run_alignment_for_chunks` |
| Credential read points | indirect through provider selection globals/env |
| Formal policy points | 0 |
| Formal preflight points | 0 |
| Formal parser points | 0 |
| `AlignmentVerificationRun` writes | 0 |
| Legacy card mutation points | sync direct and sync document |

## Main Conclusion

`DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`

Rationale:

- the frontend still calls the route, so immediate deletion would break the UI;
- the route writes a legacy data model and has three response shapes;
- it bypasses formal provider policy, provider usage, audit, request-id, parser,
  and attach gates;
- it can reach live provider transport intent if legacy provider configuration
  is made live;
- directly extracting it as a service would preserve a weaker duplicate
  execution path beside the formal verification API.

## Next Step

Task 9C.4T accepts `LEGACY_ALIGNMENT_RUN_DEPRECATION_V1` for the small pilot.
The route is now formally classified as
`TEMPORARY_FRONTEND_COMPATIBILITY_ONLY`.

Lifecycle:

1. `PHASE_0_CURRENT_AUDITED_STATE`: this document and the route remain the
   baseline; new callers are not allowed.
2. `PHASE_1_EXTERNAL_EXECUTION_CONTAINMENT`: keep the endpoint and frontend
   contract, but block legacy live/external execution and credential flow.
3. `PHASE_2_REPLACEMENT_WORKFLOW`: build
   `FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`; do not alias directly to
   `/api/alignment/verify`.
4. `PHASE_3_FRONTEND_CUTOVER`: move UI/E2E/scripts to the replacement and prove
   zero legacy calls.
5. `PHASE_4_DISABLE_LEGACY_ENDPOINT`: return HTTP 410 with
   `LEGACY_ALIGNMENT_RUN_DEPRECATED` only after caller count is zero.
6. `PHASE_5_REMOVE_DEAD_PATH`: remove the dead handler/helpers and archive or
   document legacy records separately.

Task 9C.4U completes `PHASE_1_EXTERNAL_EXECUTION_CONTAINMENT`: external/live
legacy execution is blocked at the HTTP route, worker, queued-job retry, and
direct helper boundaries. The next implementation slice is the replacement
workflow contract, not route extraction.

Do not move the current handler into a service unchanged.
