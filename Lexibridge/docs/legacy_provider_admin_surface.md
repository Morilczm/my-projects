# Legacy Provider Admin Surface Audit

Task: 9C.4H
Baseline commit: `b9b5b0a53b5db6a89911bd659a9ec6c39b0c49dd`
Branch: `audit/legacy-provider-admin-9c4h`
Status: characterization and boundary audit. Task 9C.4I has since extracted only the legacy observability GET views: `/api/admin/ai/calls`, `/api/admin/ai/usage`, and `/api/admin/ai/health`. Task 9C.4K has since extracted the seed-backed legacy configuration GET views: `/api/admin/ai/providers`, `/api/admin/ai/models`, and `/api/admin/ai/prompts`. Task 9C.4N has since extracted the thin legacy healthcheck POST route while keeping live probe disabled. Task 9C.4O has since characterized prompt mutation and concluded `PROMPT_VERSIONING_OR_CONCURRENCY_POLICY_REQUIRED_FIRST`. Task 9C.4P accepts `LEGACY_PROMPT_MUTABLE_REVISION_V1` as the small-pilot compatibility policy for that mutation surface. Task 9C.4Q establishes the prompt mutation application service while leaving POST route extraction for a later task.

## Scope

This audit covers the legacy provider admin surface under `/api/admin/ai/*` and its overlap with the formal alignment-provider governance APIs. It does not cover or migrate `POST /api/alignment/run`; that route remains a separate legacy execution surface that needs its own service boundary.

Unknown legacy provider admin route count after scan: `0`.

## Route Inventory

| Route | Method | Endpoint | Handler lines | Classification | Auth/roles | OpenAPI | Frontend | Seed helper | Writes | Network risk | Recommendation |
|---|---:|---|---:|---|---|---:|---:|---:|---|---|---|
| `/api/admin/ai/providers` | GET | `admin_ai_providers` | module | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` | admin only | yes | yes | yes | seed flush only; no commit | no | extracted in `backend/routes/legacy_provider_admin_configuration.py` |
| `/api/admin/ai/models` | GET | `admin_ai_models` | module | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` | admin only | yes | yes | yes | seed flush only; no commit | no | extracted in `backend/routes/legacy_provider_admin_configuration.py` |
| `/api/admin/ai/prompts` | GET | `admin_ai_prompts` | module | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW` | admin only | yes | yes | yes | seed flush only; no commit | no | extracted in `backend/routes/legacy_provider_admin_configuration.py`; POST still app-owned mutation callback |
| `/api/admin/ai/prompts` | POST | `admin_ai_prompts` | 12-line callback plus application service | `LEGACY_MUTATION_SERVICE_BACKED` | admin only | yes | no direct frontend call found | yes | service upserts `PromptTemplate`, owns seed + one commit + explicit rollback | no | route extraction next; policy remains `LEGACY_PROMPT_MUTABLE_REVISION_V1` |
| `/api/admin/ai/calls` | GET | `admin_ai_calls` | module | `EXTRACTED_LEGACY_OBSERVABILITY_VIEW` | admin only | yes | yes | no | none | no | extracted in `backend/routes/legacy_provider_admin_observability.py` |
| `/api/admin/ai/usage` | GET | `admin_ai_usage` | module | `EXTRACTED_LEGACY_OBSERVABILITY_VIEW` | admin only | yes | yes | no | none | no | extracted in `backend/routes/legacy_provider_admin_observability.py` |
| `/api/admin/ai/health` | GET | `admin_ai_health` | module | `EXTRACTED_LEGACY_OBSERVABILITY_VIEW` | admin only | yes | yes | yes | seed flush only; no commit | no | extracted as local health view, not live probe |
| `/api/admin/ai/healthcheck` | POST | `admin_ai_healthcheck` | module | `EXTRACTED_LEGACY_HEALTHCHECK_ROUTE` | admin only | yes | no direct frontend call found | yes | commits provider health and may persist env seed | no through legacy endpoint; live probe returns disabled result | extracted in `backend/routes/legacy_provider_admin_healthcheck.py` |

All routes keep the existing legacy response convention from `api_success`: top-level `status`, `message`, and `data`. None of these legacy admin AI routes returns `request_id` today.

## Formal API Overlap Matrix

| Legacy route | Formal route | Same source | Same fields | Same roles | Same side effects | Frontend replaceable |
|---|---|---:|---:|---:|---:|---:|
| `/api/admin/ai/providers` | `/api/alignment/providers` | partial | no | no; legacy is admin-only, formal allows teacher/admin | no; legacy can seed-flush registry rows | possible only with field mapping |
| `/api/admin/ai/models` | none | no | no | no | no | no direct formal replacement |
| `/api/admin/ai/prompts` GET | none | no | no | no | no | no direct formal replacement |
| `/api/admin/ai/calls` | none | no | no | no | no | no direct formal replacement |
| `/api/admin/ai/usage` | `/api/alignment/providers/<provider_name>/usage` | no; legacy uses `AICallLog`, formal uses alignment provider usage | no | no | no | no |
| `/api/admin/ai/health` | `/api/alignment/providers/<provider_name>/preflight` | no | no | no | no; health may seed-flush legacy registry | no |
| `/api/admin/ai/healthcheck` | `/api/alignment/providers/<provider_name>/preflight` POST | no | no | no | no; healthcheck mutates legacy provider health and can call transport | no |

The legacy surface is not a simple alias of the 9C.4A-9C.4C formal provider governance/preflight surface. It is an active UI contract over legacy provider registry, model registry, prompt templates, AI call logs, usage summaries, and provider health state.

## Registry Seed Side Effects

| Route | Calls `ensure_ai_registry_seed` | GET/POST | Persistent without explicit commit | What can be flushed | Characterized behavior |
|---|---:|---|---:|---|---|
| `/api/admin/ai/providers` | yes | GET | no | `AIProviderConfig`, `AIModelRegistry`, `PromptTemplate` | first request returns seeded rows but they are not persisted after the request without a later commit |
| `/api/admin/ai/models` | yes | GET | no | same | response may include flushed seed rows |
| `/api/admin/ai/prompts` | yes | GET | no | same | response may include flushed prompt defaults |
| `/api/admin/ai/prompts` | yes | POST | yes | same plus target `PromptTemplate` | mutation commits prompt changes and may also persist seed rows |
| `/api/admin/ai/calls` | no | GET | n/a | none | no registry seed |
| `/api/admin/ai/usage` | no | GET | n/a | none | no registry seed |
| `/api/admin/ai/health` | yes | GET | no | same | response may include flushed seed rows |
| `/api/admin/ai/healthcheck` | yes | POST | yes | same plus provider health fields | commits health fields and may persist env-selected seed rows |

This seed behavior is the main reason the legacy read-only views should be extracted separately from prompt mutation and healthcheck. A future cleanup can move seed initialization to startup, migration, or an explicit service, but 9C.4H does not change current behavior.

## Task 9C.4J Seed Service Boundary

Task 9C.4J moves the legacy provider registry seed implementation into `backend/services/legacy_provider_registry_seed.py`.

The new service owns only the legacy get-or-create and `flush` behavior for:

- `AIProviderConfig`
- `AIModelRegistry`
- `PromptTemplate`

It does not import Flask, `backend.app`, or route modules. It does not read credentials, create HTTP responses, call provider transport, execute health probes, write `AuditRecord`, or call `commit`/`rollback`. Existing callers still decide transaction outcome.

`backend/app.py` keeps a minimal compatibility wrapper named `ensure_ai_registry_seed(...)` so existing route and non-route callers keep their public call shape. The wrapper builds the environment provider selection and delegates to `ensure_legacy_provider_registry_seed(...)`.

### Seed Transaction Matrix

| Caller | Seed invoked | Flush | Caller commit | Caller rollback | Persistence after request |
|---|---:|---:|---:|---:|---:|
| `GET /api/admin/ai/providers` | yes | yes, for missing seed rows | no explicit commit | request teardown/session cleanup | seed rows are visible in the response transaction but are not persisted without a later commit |
| `GET /api/admin/ai/models` | yes | yes, for missing seed rows | no explicit commit | request teardown/session cleanup | same as providers GET |
| `GET /api/admin/ai/prompts` | yes | yes, for missing seed rows | no explicit commit | request teardown/session cleanup | same as providers GET |
| `GET /api/admin/ai/health` | yes, through `registry_seed_service` in the route module | yes, for missing seed rows | no explicit commit | request teardown/session cleanup | same as providers GET |
| `POST /api/admin/ai/prompts` | yes | yes, for missing seed rows | yes, through prompt mutation service | explicit service rollback on failure | prompt changes and any missing seed rows are persisted only on the service commit |
| `POST /api/admin/ai/healthcheck` | yes | yes, for missing seed rows | yes, after health fields are updated | caller/session rollback on failure | provider health changes and any missing seed rows are persisted only on the existing POST commit |
| `call_ai_task(...)` | yes | yes, for missing seed rows | owned by the caller path | owned by the caller path | unchanged from the historical helper |
| `ai_selection_from_config(...)` fallback | yes | yes, for missing seed rows | owned by the caller path | owned by the caller path | unchanged from the historical helper |

Characterization and service tests confirm:

- first service call creates and flushes missing provider/model/prompt rows;
- repeated calls in the same or later session do not create duplicate seed rows;
- caller rollback removes uncommitted seed rows;
- caller commit persists seed rows;
- partial seed state is completed without duplicating existing provider/model/prompt natural keys;
- service-level flush exceptions propagate to the caller and leave rollback ownership with the caller.

Current uniqueness is mostly enforced by lookup-before-create natural keys rather than formal unique constraints:

- provider: `provider_name`
- model: `provider_name` + `model_name`
- prompt: `prompt_key` + `prompt_version`

This preserves compatibility but remains vulnerable to concurrent duplicate creation if two sessions seed the same missing row at the same time. A later production hardening task should move stable defaults into migration/startup seed with explicit uniqueness or conflict handling.

## Healthcheck Execution Matrix

| Provider type | Credential present | `live_probe` | Transport called | Network risk | Result contract |
|---|---:|---:|---:|---:|---|
| `none` | no | false/true | no | no | unhealthy, local message |
| `mock` | n/a | false/true | no | no | healthy, development-only message |
| `local_heuristic` | n/a | false/true | no | no | healthy, development-only message |
| live provider, missing/placeholder credential | no | false/true | no | no | unhealthy, missing-key message |
| live provider, usable credential | yes | false | no | no | unknown, live probe skipped |
| live provider, usable credential | yes | true | no, disabled at legacy route boundary | no | unknown with `LEGACY_LIVE_PROBE_DISABLED` |

The 9C.4L.1 test suite verifies the route no longer passes `live_probe=True` through to healthcheck logic for an enabled live provider. It uses a spy and blocked socket/HTTP primitives to prove transport and adapter call counts stay at zero.

## Network And Secret Boundary

No-network coverage exists for:

- all legacy admin AI GET routes;
- unauthorized and role-denied paths;
- local healthcheck paths;
- `live_probe=false`;
- mock/local provider healthcheck;
- service-level live-probe transport intent via spy, without allowing a real connection.

Sentinel used by 9C.4H: `LEXIBRIDGE_SENTINEL_SECRET_9C4H`.

The current legacy serializers do not return API key fields. They do return non-secret operational fields such as `base_url`, token limits, cost estimates, health status, redacted prompt previews, and redacted response previews. A future healthcheck service boundary must keep transport exception text and live provider response summaries sanitized before returning them through `/api/admin/ai/healthcheck`.

## Write-set Matrix

| Route | Provider registry | Model registry | PromptTemplate | AICallLog | Usage | VerificationRun | ProviderPolicy | Preflight | AuditRecord |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| providers GET | possible flush, no commit | possible flush, no commit | possible flush, no commit | 0 | 0 | 0 | 0 | 0 | 0 |
| models GET | possible flush, no commit | possible flush, no commit | possible flush, no commit | 0 | 0 | 0 | 0 | 0 | 0 |
| prompts GET | possible flush, no commit | possible flush, no commit | possible flush, no commit | 0 | 0 | 0 | 0 | 0 | 0 |
| prompts POST | possible committed seed | possible committed seed | create/update commit | 0 | 0 | 0 | 0 | 0 | 0 |
| calls GET | 0 | 0 | 0 | read | 0 | 0 | 0 | 0 | 0 |
| usage GET | 0 | 0 | 0 | read | 0 | 0 | 0 | 0 | 0 |
| health GET | possible flush, no commit | possible flush, no commit | possible flush, no commit | 0 | 0 | 0 | 0 | 0 | 0 |
| healthcheck POST | committed seed possible; health fields commit | committed seed possible | committed seed possible | 0 | 0 | 0 | 0 | 0 | 0 |

No route in `/api/admin/ai/*` writes `AlignmentVerificationRun`, `AlignmentProviderUsageRecord`, `AlignmentProviderPolicy`, `AlignmentProviderPreflightRun`, or `AuditRecord` under current characterization.

## Permissions

All `/api/admin/ai/*` routes are admin-only.

- unauthenticated: 401;
- student: 403;
- teacher: 403;
- admin: allowed.

Course permissions are not consulted by this surface. Provider existence, credential state, and registry details are not exposed to non-admin roles through these routes.

## Frontend And OpenAPI Dependencies

`frontend/index.html` currently calls:

- `/api/admin/ai/providers`
- `/api/admin/ai/models`
- `/api/admin/ai/prompts`
- `/api/admin/ai/calls`
- `/api/admin/ai/usage`
- `/api/admin/ai/health`

No direct frontend call to `/api/admin/ai/healthcheck` was found. The healthcheck route is still listed in OpenAPI and tested, so it cannot be removed or renamed without a compatibility plan.

All `/api/admin/ai/*` routes are present in `docs/openapi.yaml`.

## Deprecation And Migration Suitability

| Route | Suitability |
|---|---|
| `/api/admin/ai/providers` GET | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW`; keep legacy shim/API contract |
| `/api/admin/ai/models` GET | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW`; keep legacy shim/API contract |
| `/api/admin/ai/prompts` GET | `EXTRACTED_SEED_BACKED_CONFIGURATION_VIEW`; shared endpoint preserved while POST mutation remains separate |
| `/api/admin/ai/prompts` POST | `LEGACY_PROMPT_MUTABLE_REVISION_V1`; application service established after 9C.4Q; route extraction still later |
| `/api/admin/ai/calls` GET | `KEEP_AND_EXTRACT` inside legacy read-only view group |
| `/api/admin/ai/usage` GET | `KEEP_AND_EXTRACT` inside legacy read-only view group |
| `/api/admin/ai/health` GET | `KEEP_AND_EXTRACT` as local health view only |
| `/api/admin/ai/healthcheck` POST | `EXTRACTED_LEGACY_HEALTHCHECK_ROUTE`; keep legacy live probe disabled and keep future live probing as a new explicit service |

## Complexity Snapshot

| Endpoint | Lines | Direct models | Helper/service calls | Returns | Writes | Network risk | Migration suitability |
|---|---:|---:|---:|---:|---:|---:|---|
| `admin_ai_providers` | module | 1 | seed service, metadata, serializer | 1 | seed flush only | no | extracted seed-backed configuration view |
| `admin_ai_models` | module | 1 | seed service, serializer | 1 | seed flush only | no | extracted seed-backed configuration view |
| `admin_ai_prompts` GET | module | 1 | seed service, serializer | 1 | seed flush only | no | extracted seed-backed configuration view; POST callback remains app-owned |
| `admin_ai_prompts` POST | 12 callback lines plus service | 1 | prompt mutation service, serializer | 1 | service commit + explicit rollback | no | route extraction next; no immutable versioning or active/default workflow |
| `admin_ai_calls` | 6 | 1 | serializer | 1 | 0 | no | read-only extraction candidate |
| `admin_ai_usage` | 6 | 1 | summary serializer | 1 | 0 | no | read-only extraction candidate |
| `admin_ai_health` | 7 | 1 | seed, serializer | 1 | seed flush only | no | read-only extraction candidate |
| `admin_ai_healthcheck` | module | 1 | seed, local readiness service | 1 | commit health/seed | no through legacy route | extracted thin route; future live probe must be a new service |

## Final Conclusion

Primary conclusion: `SPLIT_READONLY_AND_HEALTHCHECK_FIRST`.

Reasoning:

- The legacy admin AI GET views are active frontend/OpenAPI surface and are not drop-in aliases of formal provider governance APIs.
- Several GET views have a seed-flush side effect but do not commit by themselves.
- `POST /api/admin/ai/prompts` is a mutation sharing the same handler as prompt GET.
- `POST /api/admin/ai/healthcheck` commits provider health fields. After 9C.4M, local readiness and live-probe-disabled results are computed by `backend/services/legacy_provider_local_readiness.py`.
- There are no unknown `/api/admin/ai/*` routes after scan.

Next precise slice: audit `POST /api/admin/ai/prompts` mutation and its transaction boundary. Do not re-enable live transport probing without a new explicit live-probe service, and keep legacy `/api/alignment/run` separate.

## Task 9C.4I Update

Task 9C.4I implements the first half of the split by extracting only:

- `GET /api/admin/ai/calls`
- `GET /api/admin/ai/usage`
- `GET /api/admin/ai/health`

The new module preserves the legacy active API contract: admin-only access, endpoint names, `api_success` envelopes without `request_id`, id-desc limits, local health seed-flush behavior, no view `AuditRecord`, no provider transport, and no live probe. It does not migrate provider/model/prompt configuration views, `POST /api/admin/ai/prompts`, `POST /api/admin/ai/healthcheck`, `/api/alignment/run`, credential management, replay, or any provider execution path.

## Task 9C.4K Update

Task 9C.4K extracts only the seed-backed legacy configuration GET views into `backend/routes/legacy_provider_admin_configuration.py`:

- `GET /api/admin/ai/providers`
- `GET /api/admin/ai/models`
- `GET /api/admin/ai/prompts`

The module calls `ensure_legacy_provider_registry_seed(...)` directly as an explicit domain dependency and preserves the legacy compatibility contract: admin-only access, endpoint names, OpenAPI/frontend URLs, `api_success` envelopes without `request_id`, no view `AuditRecord`, provider/model/prompt ordering, and seed flush/no-explicit-commit behavior. Legitimate prompt metadata remains part of the prompt GET contract, while credential-like provider/model metadata remains excluded from responses.

`POST /api/admin/ai/prompts` now uses the same `backend/routes/legacy_provider_admin_configuration.py` route module as the GET prompt listing. Task 9C.4P defined the compatibility policy, Task 9C.4Q moved seed/upsert/commit/rollback into `backend/services/legacy_provider_prompt_mutation.py`, and Task 9C.4R removed the temporary app-owned callback while preserving the shared `admin_ai_prompts` endpoint. `/api/alignment/run` remains a separate future task, and legacy live transport probing is disabled.

## Task 9C.4L Healthcheck Boundary Audit

Task 9C.4L does not migrate `POST /api/admin/ai/healthcheck` and does not change production behavior. The detailed audit is in `docs/legacy_provider_healthcheck_boundary.md`.

Additional findings:

- The route remains admin-only, OpenAPI-listed, and not directly called by `frontend/index.html`.
- The handler still calls `ensure_ai_registry_seed(...)`, reads optional `live_probe`, loops over enabled `AIProviderConfig` rows, writes health fields, commits, and returns the legacy `api_success` envelope without `request_id`.
- Local readiness is separable from live probing: `none`, `mock`, `local_heuristic`, missing credential, and `live_probe=false` paths do not need provider transport.
- Before 9C.4L.1, live probe started for an enabled live provider with a usable credential and `live_probe=true`.
- The lower-level health helper still echoes adapter/provider error `message` if called directly. 9C.4L.1 blocks that helper path from the legacy route, so the active route no longer exposes raw adapter messages.

Primary conclusion after 9C.4L: `DISABLE_OR_DEPRECATE_LIVE_PROBE_FIRST`.

9C.4L.1 implements that safety step. `live_probe=true` now returns a safe disabled result, with `error_code=LEGACY_LIVE_PROBE_DISABLED`, and does not call provider adapter or transport. 9C.4M moves the local readiness decisions into `backend/services/legacy_provider_local_readiness.py`. 9C.4N moves the thin healthcheck adapter into `backend/routes/legacy_provider_admin_healthcheck.py` while preserving route-owned commit behavior.

## Task 9C.4O Prompt Mutation Boundary Audit

Task 9C.4O does not migrate `POST /api/admin/ai/prompts` and does not change production behavior. The detailed audit is in `docs/legacy_provider_prompt_mutation_boundary.md`.

Confirmed contract:

- GET and POST share the same Flask rule and endpoint: `/api/admin/ai/prompts`, `admin_ai_prompts`.
- GET and POST are implemented by `backend/routes/legacy_provider_admin_configuration.py`.
- After 9C.4R, the POST branch is a thin HTTP adapter that constructs `LegacyPromptMutationRequest`, calls the injected prompt mutation service, and maps the typed result to the existing legacy envelope.
- The implementation requires only `prompt_key` and `prompt_version`; OpenAPI currently also marks `task_type` and `template_text` as required.
- Success uses the legacy `api_success` envelope without `request_id`.
- No prompt mutation `AuditRecord` is written.
- The application service owns one commit and explicitly rolls back validation, seed, persistence, and commit failures.
- A successful mutation can persist missing registry seed rows that were flushed earlier by the shared route module.
- Legal prompt template content is stored as business data; unknown credential-like metadata is ignored and not persisted.
- Versioning, active/default exclusivity, uniqueness, optimistic locking, and conflict behavior are not fully defined.

Primary conclusion after 9C.4O: `PROMPT_VERSIONING_OR_CONCURRENCY_POLICY_REQUIRED_FIRST`.

Policy accepted after 9C.4P: `LEGACY_PROMPT_MUTABLE_REVISION_V1`, documented in `docs/adr/ADR-legacy-prompt-mutation-policy.md`.

Task 9C.4Q extracted that prompt mutation application service. Task 9C.4R extracted the thin POST route adapter while preserving the shared path/endpoint and removing the temporary configuration-module dependency on an app-owned callback.
