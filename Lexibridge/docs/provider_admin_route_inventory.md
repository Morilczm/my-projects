# Provider/Admin Route Inventory

Task: 9C.4F
Baseline commit: `cb63cd657929e5c5f15efd6a9adc0e6384a08a86`
Branch: `audit/provider-admin-routes-9c4f`
Status: route inventory and characterization. Task 9C.4G has since extracted `GET /api/admin/alignment-runs`; Task 9C.4H has since added the dedicated legacy `/api/admin/ai/*` compatibility and healthcheck safety audit in `docs/legacy_provider_admin_surface.md`; Task 9C.4I has since extracted only the legacy observability GET views; Task 9C.4J has since moved the shared legacy provider registry seed implementation into `backend/services/legacy_provider_registry_seed.py` without changing route contracts; Task 9C.4K has since extracted only the seed-backed legacy configuration GET views; Task 9C.4N has since extracted the thin legacy healthcheck POST route; Task 9C.4O has since characterized prompt mutation and concluded `PROMPT_VERSIONING_OR_CONCURRENCY_POLICY_REQUIRED_FIRST`; Task 9C.4Q has since established `backend/services/legacy_provider_prompt_mutation.py`; Task 9C.4R has since moved the thin prompt mutation POST adapter into the shared configuration route module; Task 9C.4S has since characterized legacy `/api/alignment/run` and concluded `DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`; Task 9C.4T has since accepted `LEGACY_ALIGNMENT_RUN_DEPRECATION_V1`; Task 9C.5L confirms no production frontend legacy POST consumer remains while retaining the route for legacy worker/tests/safety probes and unknown external clients.

## Scope

This document inventories remaining provider/admin-adjacent routes after the 9C.4A through 9C.4E extractions:

- provider governance GET routes live in `backend/routes/provider_governance.py`;
- provider policy mutation lives in `backend/routes/provider_policy.py`;
- provider preflight POST lives in `backend/routes/provider_preflight.py`;
- `POST /api/alignment/verify` lives in `backend/routes/alignment_verification.py` and delegates execution to `backend/services/alignment_verification_execution.py`.

The remaining routes below still live in `backend/app.py`. Unknown route count after this scan: `0`.

## Remaining Route Inventory

| Route | Method | Endpoint | Lines | Classification | Read only | Auth/roles | OpenAPI | Frontend/scripts | Database writes | Network risk | Secret risk | Recommendation |
|---|---:|---|---:|---|---:|---|---:|---|---|---|---|---|
| `/api/admin/alignment-runs` | GET | `admin_alignment_runs` | module | `EXTRACTED_READ_ONLY_ADMIN_LISTING` | yes | admin only | no | README only | none | none | serialized run summaries only | extracted in `backend/routes/admin_alignment_runs.py` |
| `/api/admin/ai/providers` | GET | `admin_ai_providers` | module | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` | mostly | admin only | yes | frontend active | may flush registry seed if missing; no explicit commit | none in GET | provider config fields; no API keys returned | extracted in `backend/routes/legacy_provider_admin_configuration.py` |
| `/api/admin/ai/models` | GET | `admin_ai_models` | module | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` | mostly | admin only | yes | frontend active | may flush registry seed if missing; no explicit commit | none | model registry fields; no credentials | extracted in `backend/routes/legacy_provider_admin_configuration.py` |
| `/api/admin/ai/prompts` | GET | `admin_ai_prompts` | module | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` | mostly | admin only | yes | frontend active | may flush registry seed if missing; no explicit commit | none | prompt metadata by current serializer | extracted in `backend/routes/legacy_provider_admin_configuration.py`; shares endpoint with extracted POST adapter |
| `/api/admin/ai/prompts` | POST | `admin_ai_prompts` | module + service | `EXTRACTED_SERVICE_BACKED_LEGACY_MUTATION` | no | admin only | yes | OpenAPI active; no direct frontend POST found | service upserts `PromptTemplate`, commits once, rolls back failures, can persist seed rows | none | accepts template/schema text; unknown credential-like metadata ignored | extracted thin adapter in `backend/routes/legacy_provider_admin_configuration.py` |
| `/api/admin/ai/calls` | GET | `admin_ai_calls` | module | `EXTRACTED_LEGACY_OBSERVABILITY_VIEW` | yes | admin only | yes | frontend active | none | none | serialized call logs; characterization verifies no sentinel secret | extracted in `backend/routes/legacy_provider_admin_observability.py` |
| `/api/admin/ai/usage` | GET | `admin_ai_usage` | module | `EXTRACTED_LEGACY_OBSERVABILITY_VIEW` | yes | admin only | yes | frontend active | none | none | usage summaries; characterization verifies no sentinel secret | extracted in `backend/routes/legacy_provider_admin_observability.py` |
| `/api/admin/ai/health` | GET | `admin_ai_health` | module | `EXTRACTED_LEGACY_OBSERVABILITY_VIEW` | mostly | admin only | yes | frontend active | seed flush only; no explicit commit | none | health/config summary only | extracted as local health view, not live probe |
| `/api/admin/ai/healthcheck` | POST | `admin_ai_healthcheck` | module | `EXTRACTED_LEGACY_HEALTHCHECK_ROUTE` | no | admin only | yes | tested | updates provider health fields, commits | no through legacy endpoint; live mode returns disabled result from service | lower-level helper still needs redaction before future live probe | extracted in `backend/routes/legacy_provider_admin_healthcheck.py` |
| `/api/alignment/run` | POST | `run_alignment` | 184 | `ACTIVE_COMPATIBILITY_SURFACE` | no | student, teacher, admin | yes | no production frontend POST; scripts/tests active | creates `AlignmentRun`, background job or cards, records personal usage, commits | external/live execution is fail-closed | alignment/card payloads | keep until deprecation window, external consumers, and queued jobs are resolved |
| `/api/alignment/runs` | GET | `alignment_runs` | 29 | `LEGACY_ACTIVE` | yes | student, teacher, admin | yes | frontend active | none | none | serialized legacy `AlignmentRun` summaries | extract only after legacy alignment-run boundary decision |
| `/api/alignment/runs/<int:run_id>` | GET | `alignment_run_detail` | 16 | `LEGACY_ACTIVE` | yes | student, teacher, admin with owner/course/admin checks | yes | README/docs/tests | none | none | serialized legacy run detail | extract only after legacy alignment-run boundary decision |

## Already Extracted Provider Routes

| Route | Module | Relationship |
|---|---|---|
| `GET /api/alignment/providers` | `backend/routes/provider_governance.py` | Formal provider registry/governance listing. Overlaps with but does not match `/api/admin/ai/providers`. |
| `GET /api/alignment/providers/<provider_name>/policy` | `backend/routes/provider_governance.py` | Formal policy read path. |
| `POST /api/alignment/providers/<provider_name>/policy` | `backend/routes/provider_policy.py` | Formal policy mutation. |
| `GET /api/alignment/providers/<provider_name>/usage` | `backend/routes/provider_governance.py` | Formal alignment-provider usage listing. Different model from legacy `AICallLog` usage. |
| `GET /api/alignment/providers/<provider_name>/preflight` | `backend/routes/provider_governance.py` | Formal preflight history. |
| `POST /api/alignment/providers/<provider_name>/preflight` | `backend/routes/provider_preflight.py` | Formal local preflight execution. |
| `POST /api/alignment/verify` | `backend/routes/alignment_verification.py` | Formal alignment verification execution HTTP adapter. |

## Admin Alignment Runs Contract

- URL/method: `GET /api/admin/alignment-runs`
- Endpoint: `admin_alignment_runs`
- Authentication: required.
- Allowed roles: `admin` only.
- Query parameters: none.
- Request body: none.
- Success status: HTTP 200.
- Error statuses: unauthenticated 401; non-admin roles 403.
- Response top-level fields: `status`, `runs`.
- `request_id`: not returned by the current implementation.
- AuditRecord event: none observed.
- Data source: `AlignmentRun.query.order_by(AlignmentRun.id.desc()).limit(300)`.
- Writes: none.
- Commit/rollback: none.
- Network: none.
- OpenAPI: not currently listed.
- Frontend: no active frontend call found.
- Existing tests before this task: no dedicated contract test found.
- Status: `EXTRACTED_READ_ONLY_ADMIN_LISTING` in `backend/routes/admin_alignment_runs.py`.
- Suitability: extracted as a low-risk, narrow route module. It remains low product value because it is not in OpenAPI/frontend.

## Admin AI Providers Contract

- URL/method: `GET /api/admin/ai/providers`
- Endpoint: `admin_ai_providers`
- Authentication: required.
- Allowed roles: `admin` only.
- Success status: HTTP 200.
- Error statuses: unauthenticated 401; non-admin roles 403.
- Response envelope: `status`, `message`, `data`.
- Response `data`: `items` and `current`.
- `request_id`: not returned by the current implementation.
- AuditRecord event: none observed.
- Data source: `AIProviderConfig` plus `current_provider_metadata()`.
- Writes: calls the legacy registry seed service directly from `backend/routes/legacy_provider_admin_configuration.py`, which can add/flush `AIProviderConfig`, `AIModelRegistry`, and `PromptTemplate` rows when the seed is missing. The GET handler does not explicitly commit.
- Network: none for this GET route.
- Secret redaction: characterization injects sentinel API key values and verifies they do not appear in the response.
- Relationship to formal API: overlaps with `GET /api/alignment/providers`, but schema, role set, storage model, and frontend use differ.
- Status: `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` in `backend/routes/legacy_provider_admin_configuration.py`. It remains a legacy active view, not a formal provider governance API alias.

## Legacy Provider Routes

The `/api/admin/ai/*` group is active in `frontend/index.html` and OpenAPI. It is not the same surface as the 9C.4A formal provider governance API.

- `/api/admin/ai/providers`, `/models`, `/prompts`, and `/health` all call the shared legacy registry seed service. The extracted provider/model/prompt configuration route module calls `ensure_legacy_provider_registry_seed(...)` directly as an explicit domain dependency for GET views; `backend/app.py` keeps `ensure_ai_registry_seed(...)` as a compatibility wrapper for app-local non-route helper paths.
- `/api/admin/ai/prompts` still preserves the shared Flask endpoint `admin_ai_prompts`; GET and POST are both handled by the configuration route module. After 9C.4Q, `backend/services/legacy_provider_prompt_mutation.py` owns the `PromptTemplate` upsert, seed integration, one commit, and explicit rollback under `LEGACY_PROMPT_MUTABLE_REVISION_V1`; after 9C.4R, the app-owned prompt mutation callback has been removed.
- `/api/admin/ai/healthcheck` mutates provider health fields. After 9C.4M, local readiness and `LEGACY_LIVE_PROBE_DISABLED` are computed by `services/legacy_provider_local_readiness.py`; after 9C.4N, the thin route adapter lives in `backend/routes/legacy_provider_admin_healthcheck.py` and still owns seed, query, health-field writes, and commit.
- `/api/admin/ai/calls` and `/usage` are read-only over `AICallLog`, a legacy AI usage/cost surface distinct from `AlignmentProviderUsageRecord`.

The remaining legacy provider admin write/high-risk routes should not be extracted as one group until their service boundaries are explicit.

## Legacy Alignment Run Routes

`/api/alignment/run` and `/api/alignment/runs*` are legacy alignment run APIs.
The POST remains in OpenAPI and compatibility tooling but is no longer called
by the production frontend. The GET list remains active in the frontend.

- `POST /api/alignment/run` is an execution route. It can create an `AlignmentRun`, create background jobs, run synchronous document/term alignment, create or update terminology cards, record personal AI usage, and commit.
- `GET /api/alignment/runs` is a role-filtered listing for student/teacher/admin.
- `GET /api/alignment/runs/<int:run_id>` is a role-filtered detail route.

Task 9C.4S concluded `DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`. Task 9C.4T accepts `LEGACY_ALIGNMENT_RUN_DEPRECATION_V1`, and Task 9C.4U contains legacy external/live execution at the POST route, worker, retry, queued-job, and direct-helper boundaries without extracting the route. Tasks 9C.5H and 9C.5K migrate and verify the formal production frontend path. Task 9C.5L identifies the remaining compatibility boundary in `docs/legacy_alignment_consumer_audit.md`; the route remains active until unknown external consumers and legacy queued-job handling have an approved policy. The two GET routes should be handled separately as a compatibility read model.

## Duplicate And Alias Matrix

| Route A | Route B | Same data | Same schema | Same roles | Same service | Alias candidate |
|---|---|---:|---:|---:|---:|---:|
| `/api/admin/ai/providers` | `/api/alignment/providers` | partial | no | no | no | no |
| `/api/admin/ai/usage` | `/api/alignment/providers/<provider_name>/usage` | no | no | no | no | no |
| `/api/admin/ai/health` | `/api/alignment/providers/<provider_name>/preflight` | no | no | no | no | no |
| `/api/admin/alignment-runs` | `/api/alignment/runs` | partial | no | no | yes, legacy `AlignmentRun` | no |
| `/api/alignment/run` | `/api/alignment/verify` | no | no | no | no | no |

There are overlapping concepts, but no safe drop-in alias was found.

## Write-set Matrix

| Path | VerificationRun | ProviderUsage | ProviderPolicy | Preflight | AlignmentRun | AI registry | Prompt | AICallLog | AuditRecord |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `/api/admin/alignment-runs` GET | 0 | 0 | 0 | 0 | read | 0 | 0 | 0 | 0 |
| `/api/admin/ai/providers` GET | 0 | 0 | 0 | 0 | 0 | possible seed flush | possible seed flush | 0 | 0 |
| `/api/admin/ai/models` GET | 0 | 0 | 0 | 0 | 0 | possible seed flush | possible seed flush | 0 | 0 |
| `/api/admin/ai/prompts` GET | 0 | 0 | 0 | 0 | 0 | possible seed flush | possible seed flush | 0 | 0 |
| `/api/admin/ai/prompts` POST | 0 | 0 | 0 | 0 | 0 | possible committed seed | prompt upsert commit | 0 | 0 |
| `/api/admin/ai/calls` GET | 0 | 0 | 0 | 0 | 0 | 0 | 0 | read | 0 |
| `/api/admin/ai/usage` GET | 0 | 0 | 0 | 0 | 0 | 0 | 0 | read | 0 |
| `/api/admin/ai/health` GET | 0 | 0 | 0 | 0 | 0 | possible seed flush | possible seed flush | 0 | 0 |
| `/api/admin/ai/healthcheck` POST | 0 | 0 | 0 | 0 | 0 | health write/commit | 0 | 0 | 0 |
| `/api/alignment/run` POST | 0 | 0 | 0 | 0 | write/commit | possible registry seed through legacy AI helper | prompt lookup through legacy AI helper | possible legacy usage/AICallLog side effect | 0 |
| `/api/alignment/runs` GET | 0 | 0 | 0 | 0 | read | 0 | 0 | 0 | 0 |
| `/api/alignment/runs/<id>` GET | 0 | 0 | 0 | 0 | read | 0 | 0 | 0 | 0 |

## Network And Secret Boundary

Characterization tests enforce no-network behavior for the read/list routes and for `admin_ai_healthcheck` with `live_probe=false` and `live_probe=true`.

Network risk is now blocked at the legacy route boundary. `services/ai_health.py` still contains provider transport logic for future use, but `POST /api/admin/ai/healthcheck` no longer calls it for `live_probe=true`.

Sentinel secret: `LEXIBRIDGE_SENTINEL_SECRET_9C4F`

The characterization suite verifies the sentinel does not appear in provider/admin responses covered by the tests. The legacy provider serializers still include legitimate fields such as token limits and token cost field names; those are not credentials.

## Frontend And Script Dependencies

Active frontend dependencies:

- `frontend/index.html` calls `/api/alignment/runs`.
- No production frontend code calls `POST /api/alignment/run`.
- `frontend/js/formal-workflow.js` calls only the formal document-alignment API family.
- `frontend/index.html` calls `/api/admin/ai/providers`, `/models`, `/prompts`, `/calls`, `/usage`, and `/health`.

OpenAPI dependencies:

- `/api/alignment/run`, `/api/alignment/runs`, and `/api/alignment/runs/{run_id}` are listed. Task 9C.4S found the `/api/alignment/run` OpenAPI schema omits the `sync` query parameter and does not describe all three response shapes.
- `/api/admin/ai/providers`, `/models`, `/prompts`, `/calls`, `/usage`, `/health`, and `/healthcheck` are listed.
- `/api/admin/alignment-runs` is not listed.

`/api/admin/alignment-runs` appears in README/admin route documentation but no active frontend call was found.

## Complexity Snapshot

| Endpoint | Lines | Direct models | Service/helper calls | Returns | Writes | Network risk | Extraction suitability |
|---|---:|---:|---:|---:|---:|---:|---|
| `admin_alignment_runs` | module | 1 | serializer | 1 | 0 | no | `EXTRACTED_READ_ONLY_ADMIN_LISTING` |
| `admin_ai_providers` | module | 1 | seed service, metadata, serializer | 1 | possible seed flush | no | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` |
| `admin_ai_models` | module | 1 | seed service, serializer | 1 | possible seed flush | no | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` |
| `admin_ai_prompts` | module + service | 1 | prompt mutation service, seed service, serializer | 2 | yes on POST through service | no | GET and POST extracted in shared configuration route module |
| `admin_ai_calls` | 6 | 1 | serializer | 1 | 0 | no | `DIRECT_EXTRACTION_SAFE` inside legacy group |
| `admin_ai_usage` | 6 | 1 | summary serializer | 1 | 0 | no | `DIRECT_EXTRACTION_SAFE` inside legacy group |
| `admin_ai_health` | 7 | 1 | seed, serializer | 1 | possible seed flush | no | `DEPRECATION_AUDIT_REQUIRED` |
| `admin_ai_healthcheck` | module | 1 | seed, local readiness service | 1 | yes | disabled in legacy live-probe mode | `EXTRACTED_LEGACY_HEALTHCHECK_ROUTE` |
| `run_alignment` | 159 | many | course/auth/job/alignment/card/usage helpers | 14 | yes | provider-dependent | `SERVICE_BOUNDARY_REQUIRED` |
| `alignment_runs` | 29 | 2 | course permission, serializer | 1 | 0 | no | `EXTRACTION_AFTER_LEGACY_BOUNDARY` |
| `alignment_run_detail` | 16 | 2 | course permission, serializer | 4 | 0 | no | `EXTRACTION_AFTER_LEGACY_BOUNDARY` |

## Task 9C.4H Legacy Provider Admin Audit

Task 9C.4H keeps all production routes in place and adds a dedicated audit for `/api/admin/ai/*`.

Additional findings:

- Unknown `/api/admin/ai/*` route count remains `0`.
- `/api/admin/ai/providers`, `/models`, `/prompts` GET, and `/health` call the shared legacy registry seed service; GET paths flush seed rows for the response but do not persist them without a later commit.
- `/api/admin/ai/prompts` POST is a prompt mutation route and must not be migrated with read-only views.
- `/api/admin/ai/healthcheck` commits provider health state and may persist env-selected seed rows.
- `/api/admin/ai/healthcheck` had a live transport risk before 9C.4L.1. It now returns `LEGACY_LIVE_PROBE_DISABLED` for live providers when `live_probe=true`.
- `services.ai_health.healthcheck_provider(...)` still contains a live adapter path if called directly, so future live probing must be implemented as a separate explicit service with redaction.

Task 9C.4H conclusion: `SPLIT_READONLY_AND_HEALTHCHECK_FIRST`.

Task 9C.4M has extracted local healthcheck readiness into a service while preserving disabled live probe behavior. Task 9C.4N moves the thin healthcheck HTTP adapter to `backend/routes/legacy_provider_admin_healthcheck.py` while preserving caller-owned transaction behavior. Do not re-enable live transport probing without an explicit service boundary.

## Task 9C.4I Legacy Observability Extraction

Task 9C.4I extracts only the safe legacy observability GET views into `backend/routes/legacy_provider_admin_observability.py`:

- `GET /api/admin/ai/calls`
- `GET /api/admin/ai/usage`
- `GET /api/admin/ai/health`

The extracted routes keep the legacy endpoint names, admin-only permission, OpenAPI/frontend URLs, `api_success` response envelope without `request_id`, no view `AuditRecord`, and existing id-desc limits. `/api/admin/ai/health` still calls the existing seed helper for local registry defaults but does not add commit/rollback, live probe, provider transport, provider usage writes, policy/preflight writes, verification runs, or card writes.

Still in `backend/app.py`:

- prompt mutation: `POST /api/admin/ai/prompts`;
- live-probe risk route: `POST /api/admin/ai/healthcheck`;
- legacy alignment execution routes: `/api/alignment/run` and `/api/alignment/runs*`.

## Task 9C.4K Legacy Configuration Extraction

Task 9C.4K extracts only the seed-backed legacy configuration GET views into `backend/routes/legacy_provider_admin_configuration.py`:

- `GET /api/admin/ai/providers`
- `GET /api/admin/ai/models`
- `GET /api/admin/ai/prompts`

The extracted routes keep the legacy endpoint names, admin-only permission, OpenAPI/frontend URLs, `api_success` response envelope without `request_id`, no view `AuditRecord`, existing ordering, and seed flush/no-explicit-commit behavior. The route module calls `ensure_legacy_provider_registry_seed(...)` directly and does not import `backend.app` or the compatibility wrapper.

Still in `backend/app.py` after 9C.4K:

- prompt mutation logic for `POST /api/admin/ai/prompts`, passed to the route module as an explicit callback to preserve the shared `admin_ai_prompts` endpoint;
- legacy healthcheck route until 9C.4N; after 9C.4N it lives in `backend/routes/legacy_provider_admin_healthcheck.py`;
- legacy alignment execution routes: `/api/alignment/run` and `/api/alignment/runs*`.

## Task 9C.4L Legacy Healthcheck Boundary Audit

Task 9C.4L keeps `POST /api/admin/ai/healthcheck` in `backend/app.py` and adds dedicated characterization in `tests/test_legacy_provider_healthcheck_characterization.py` plus `docs/legacy_provider_healthcheck_boundary.md`.

Confirmed contract:

- URL/method/endpoint remain `POST /api/admin/ai/healthcheck` and `admin_ai_healthcheck`.
- The route is admin-only and uses the legacy `api_success` envelope without `request_id`.
- The route calls the shared seed wrapper, writes `AIProviderConfig` health fields, and commits.
- The route does not write `AICallLog`, alignment provider usage, verification runs, preflight runs, cards, or `AuditRecord`.
- Local readiness paths do not call transport.
- Before 9C.4L.1, live probe transport intent existed only for enabled live providers with usable credential and `live_probe=true`.
- Current lower-level live probe helper can echo adapter/provider error `message` if called directly, but 9C.4L.1 blocks that path from the legacy route.

Task 9C.4L conclusion: `DISABLE_OR_DEPRECATE_LIVE_PROBE_FIRST`.

Task 9C.4M establishes the local readiness service. Task 9C.4N extracts the thin healthcheck route adapter while preserving caller-owned transaction behavior. Task 9C.4O characterizes prompt mutation and records `PROMPT_VERSIONING_OR_CONCURRENCY_POLICY_REQUIRED_FIRST`; Task 9C.4P defines `LEGACY_PROMPT_MUTABLE_REVISION_V1`; Task 9C.4Q extracts the prompt mutation application service so seed/upsert/commit/rollback are no longer implemented directly in the HTTP adapter; Task 9C.4R moves that adapter into the shared configuration route module. Task 9C.4S characterizes legacy `/api/alignment/run` and records `DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`; Task 9C.4T defines `LEGACY_ALIGNMENT_RUN_DEPRECATION_V1`; Task 9C.4U blocks legacy alignment external/live execution at route, worker, retry, queued-job, and direct-helper boundaries without moving the route. The next alignment task is the formal document alignment workflow contract, not legacy route extraction.

Task 9C.4V defines that formal replacement contract as
`FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`. The target API family is
`POST /api/document-alignment-runs`,
`GET /api/document-alignment-runs/{run_uid}`, and
`GET /api/document-alignment-runs/{run_uid}/items`. Tasks 9C.4W through 9C.5F
establish the formal models, admission, worker, processing, query services,
HTTP adapters, and OpenAPI contract. The legacy `/api/alignment/run` route
remains temporary frontend compatibility until formal API E2E and frontend
cutover are complete; it must not be extracted as a normal service/route.

## Final Decision

Primary conclusion after Task 9C.4G: `ADMIN_ALIGNMENT_RUNS_EXTRACTED`

Reasoning:

- `GET /api/admin/alignment-runs` is a small admin-only read path.
- It does not write `AlignmentRun`, provider usage, provider policy, preflight, or audit rows.
- It does not call provider transport or access the network.
- It does not return credentials or raw provider secrets.
- It is independent from the active frontend provider admin views.
- Extracting it should not freeze the legacy `/api/admin/ai/*` design.

Task 9C.4G extracted only `GET /api/admin/alignment-runs` into `backend/routes/admin_alignment_runs.py`. It did not include `/api/admin/ai/*`, `/api/alignment/run`, `/api/alignment/runs`, healthcheck, prompt mutation, or any provider transport path.

Secondary follow-up:

- Run a separate legacy provider admin compatibility/deprecation audit before migrating `/api/admin/ai/*`.
- Disable legacy `/api/alignment/run` external/live execution before touching its route or service boundary.
