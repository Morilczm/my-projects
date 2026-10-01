# Legacy Provider Healthcheck Boundary

Task: 9C.4L / 9C.4L.1 / 9C.4M / 9C.4N
Baseline commit for audit: `3f9b6dfb7a3631032ccff07330d801106117ffd4`
Status: `LIVE_PROBE_DISABLED`; `LOCAL_READINESS_SERVICE_ESTABLISHED`; `THIN_ROUTE_EXTRACTED`.

## HTTP Contract

- URL: `POST /api/admin/ai/healthcheck`
- Flask endpoint: `admin_ai_healthcheck`
- Handler location after 9C.4N: `backend/routes/legacy_provider_admin_healthcheck.py`
- Handler size after 9C.4N: 27 function body lines
- Authentication: required
- Allowed role: `admin`
- Rejected roles: unauthenticated 401, student 403, teacher 403
- Request body: optional JSON object
- Supported field: `live_probe`
- Unknown fields: ignored
- Empty JSON object: accepted
- Malformed JSON: Flask JSON parse error, HTTP 400
- Empty body without JSON content type: Flask unsupported media type, HTTP 415
- Success status: HTTP 200
- Success envelope: legacy `api_success`, top-level `status`, `message`, `data`
- Success `data`: `items`
- `request_id`: not returned by the current success response
- `live_probe=true`: accepted for compatibility; live provider transport probing is disabled and returns `LEGACY_LIVE_PROBE_DISABLED`
- AuditRecord: none
- OpenAPI: listed under `/api/admin/ai/healthcheck`
- Frontend: no direct `frontend/index.html` call found

## Handler Responsibilities

| Segment | Current owner | Reads DB | Writes DB | Network risk | Business rule |
|---|---|---:|---:|---:|---:|
| Authentication and role check | route module | token/user | token last-used flush | no | yes |
| Registry seed | `ensure_ai_registry_seed(...)` wrapper and seed service | provider/model/prompt | seed flush | no | yes |
| JSON parsing | route module | no | no | no | no |
| Enabled provider loop | route module | `AIProviderConfig` | health fields | no | yes |
| Local readiness decision | `services.legacy_provider_local_readiness.evaluate_legacy_provider_local_readiness(...)` | no | no | no | yes |
| Live transport probe | disabled at the legacy route boundary | no | health fields | no | yes |
| Commit | route module | no | provider health and possible seed rows | no | yes |
| Response mapping | route module | no | no | no | no |

The route module still owns transaction completion. The seed service and local readiness service do not commit or roll back.

## Route module

Task 9C.4N moves the thin HTTP adapter into `backend/routes/legacy_provider_admin_healthcheck.py`.

Register signature:

`register_legacy_provider_admin_healthcheck_routes(app, *, core, models, serializers, registry_seed_service, seed_models, provider_selection_factory, default_prompts, model_version_factory, local_readiness_service, credential_presence_resolver)`

The route module keeps the legacy endpoint name, admin-only permission, optional JSON parsing behavior, legacy `api_success` envelope without success `request_id`, and no-`AuditRecord` behavior. It does not import `backend.app`, provider adapter code, provider transport code, the old live healthcheck executor, credentials, or environment APIs.

Healthcheck-specific dependencies are passed explicitly. `RouteCoreDependencies` remains common route infrastructure only and does not include seed services, local readiness services, provider models, credential resolvers, adapter/transport dependencies, or healthcheck execution helpers.

## Local readiness service

Task 9C.4M adds `backend/services/legacy_provider_local_readiness.py`.

Public API:

- `LegacyProviderLocalReadinessRequest(live_probe_requested: bool)`
- `LegacyProviderLocalReadinessProvider(provider_name, provider_mode, model_name, enabled, credential_present, adapter_available, external_execution_enabled)`
- `LegacyProviderLocalReadinessResult(...)`
- `evaluate_legacy_provider_local_readiness(request, provider)`

The service is a pure local evaluator. It does not import Flask, `backend.app`, route modules, provider adapter code, provider transport code, or `os.environ`. It receives credential state only as `credential_present: bool`; it never receives API keys, bearer tokens, cookies, authorization headers, raw environment values, adapter clients, transport clients, or database sessions.

The result exposes only safe response fields and `health_updates={"health_status": ...}` for the route to apply to `AIProviderConfig`.

## Local readiness

Local readiness is the part that can be computed without provider transport:

- `live_probe=true` returns `LEGACY_LIVE_PROBE_DISABLED` for every provider class;
- provider mode `none` with `live_probe` omitted/false returns unhealthy;
- provider mode `mock` with `live_probe` omitted/false returns healthy;
- provider mode `local_heuristic` with `live_probe` omitted/false returns healthy;
- live provider without a usable credential, with `live_probe` omitted/false, returns unhealthy;
- live provider with a usable credential and `live_probe=false` returns unknown with "live probe skipped";
- `live_probe` omitted behaves like false.

This logic has no network dependency and can be isolated from route HTTP parsing.

## Live transport probe

Before 9C.4L.1, live transport probe could start when all of the following were true:

- the route is called by an admin;
- an enabled provider config is selected;
- the selected provider mode is `live`;
- the selected provider has a non-placeholder credential from the environment/global provider selection;
- request JSON has `live_probe=true`.

The service then called `provider_from_selection(selection).call(...)` with a `term_alignment` health payload. Characterization used a spy and blocked socket/HTTP primitives; no test performed a real external request.

9C.4L.1 disables that legacy route path. 9C.4M moves the disabled/local decision into the local readiness service. `live_probe=true` still returns HTTP 200 with the legacy envelope, but providers now receive a safe local result:

- `health_status=unknown`
- `error_code=LEGACY_LIVE_PROBE_DISABLED`
- a stable message stating provider transport was not attempted

The lower-level helper still needs a redaction boundary before any future live-probe service can be enabled, because adapter/provider error `message` can contain sensitive text.

## Execution Matrix

| Provider class | Provider status | Credential | `live_probe` | Transport intent | DB writes | HTTP/result |
|---|---|---:|---:|---:|---:|---|
| any provider | enabled | any | true | no, disabled by service | health fields and possible seed commit | 200, `LEGACY_LIVE_PROBE_DISABLED` |
| none | enabled | no | omitted/false | no | health fields and possible seed commit | 200, unhealthy |
| mock | enabled | n/a | omitted/false | no | health fields | 200, healthy |
| local_heuristic | enabled | n/a | omitted/false | no | health fields | 200, healthy |
| live external | enabled | missing/placeholder | false | no | health fields | 200, unhealthy missing-key message |
| live external | enabled | usable | false | no | health fields | 200, unknown skipped-live-probe message |
| any | disabled | any | any | no for that provider | none for disabled provider | omitted from `items` |
| unauthenticated | n/a | n/a | any | no | none | 401 |
| non-admin | n/a | n/a | any | no | none for provider health | 403 |
| malformed JSON | after admin auth and seed call | n/a | n/a | no | seed may be flushed but not committed by this path | 400 |
| empty non-JSON body | after admin auth and seed call | n/a | n/a | no | seed may be flushed but not committed by this path | 415 |

## Seed and transaction matrix

| Path | Seed flush | Health write | Call write | Usage write | Audit | Commit | Rollback |
|---|---:|---:|---:|---:|---:|---:|---:|
| unauthorized | no | no | no | no | no | no | no route rollback |
| role denied | no | no | no | no | no | no | no route rollback |
| malformed JSON | yes, after admin auth | no | no | no | no | no | caller/session cleanup required |
| empty non-JSON body | yes, after admin auth | no | no | no | no | no | caller/session cleanup required |
| local-only success | yes | yes | no | no | no | yes | no |
| credential missing | yes | yes | no | no | no | yes | no |
| live probe skipped | yes | yes | no | no | no | yes | no |
| live probe requested | yes | disabled result health fields | no | no | no | yes if commit succeeds | no |
| live probe adapter exception | n/a after 9C.4L.1 | n/a | n/a | n/a | n/a | n/a | n/a |
| database commit exception | yes | partial in session | no | no | no | no | no explicit route rollback |
| AuditRecord exception | n/a | n/a | n/a | n/a | n/a | n/a | n/a, route writes no AuditRecord |

## Write-set

The success path can persist:

- `AIProviderConfig` seed rows;
- `AIModelRegistry` seed rows;
- `PromptTemplate` seed rows;
- `AIProviderConfig.health_status`;
- `AIProviderConfig.last_healthcheck_at`;
- `AIProviderConfig.updated_at`.

Characterization confirms it does not create or modify:

- `AICallLog`;
- `AlignmentProviderUsageRecord`;
- `AlignmentVerificationRun`;
- `AlignmentProviderPreflightRun`;
- `AuditRecord`;
- `ConceptAlignmentCard`.

## Credential flow

Credential source is not `AIProviderConfig`; that model has no API-key column. After 9C.4M, the legacy endpoint no longer constructs a `ProviderSelection` for healthcheck local readiness. After 9C.4N, the route module receives a `credential_presence_resolver(config) -> bool` callback from `backend/app.py` and passes only a boolean snapshot field to the local readiness service.

For `live_probe=true`, the service returns the disabled result before any adapter or transport code can be involved. The lower-level live health helper can still reflect adapter messages if called directly, so any future live-probe service must add a redaction boundary before being enabled.

## Timeout and error mapping

| Condition | Current mapping |
|---|---|
| no provider configured | result item `health_status=unhealthy` |
| mock/local provider | result item `health_status=healthy` |
| missing live credential | result item `health_status=unhealthy` |
| live credential but probe skipped | result item `health_status=unknown` |
| `live_probe=true` for any provider class | result item `health_status=unknown`, `error_code=LEGACY_LIVE_PROBE_DISABLED` |
| provider adapter returns success | no longer reachable through this legacy endpoint |
| provider adapter returns error | no longer reachable through this legacy endpoint |
| provider adapter returns error message with sensitive text | no longer reachable through this legacy endpoint |
| malformed JSON | HTTP 400 before route response mapping |
| empty non-JSON body | HTTP 415 before route response mapping |

9C.4L.1 intentionally adds the stable compatibility reason code `LEGACY_LIVE_PROBE_DISABLED`; 9C.4M keeps that code in the local readiness service.

## Permissions

The route is admin-only. Student and teacher tokens receive 403. Unauthenticated calls receive 401. Provider existence, credential presence, adapter class, base URL, and transport exceptions are not disclosed to unauthenticated or non-admin callers.

## AuditRecord

The current handler does not create `AuditRecord` rows on success or failure. 9C.4L.1 keeps that behavior.

## No-network and transport spy

Tests block `socket`, `urllib`, `requests`, and `httpx` on service and route paths. Service tests statically verify there is no Flask, route, adapter, transport, credential, commit, or rollback dependency. Route tests verify the route calls `evaluate_legacy_provider_local_readiness(...)` with a provider snapshot whose credential state is boolean.

## Complexity metrics

| Metric | Value |
|---|---:|
| Handler lines including decorator | n/a, registered with `app.add_url_rule` |
| Function body lines | 27 |
| Direct route model count | 1 |
| Direct service/helper calls | 4: auth, seed, credential-present adapter, local readiness |
| Return paths | 2 |
| Explicit commit points | 1 |
| Explicit rollback points | 0 |
| Provider transport call sites in route | 0 |
| Provider transport call sites in health service | 1, no longer reachable from legacy healthcheck live probe |
| Credential value copy points in healthcheck route | 0; only boolean credential presence is passed |
| Audit events | 0 |
| Tables possibly written by success path | 3 seed tables plus `AIProviderConfig` health fields |

## Final conclusion

Primary conclusion after 9C.4N: `THIN_ROUTE_EXTRACTED`.

Reasoning:

- Local readiness and live transport probe are logically separable.
- The route is admin-only and no frontend call was found, but OpenAPI still exposes it.
- The route module commits provider health fields and possible seed rows.
- The legacy route now delegates local readiness calculation to a pure service and blocks live provider transport when `live_probe=true`.
- Current lower-level health helper still echoes adapter error `message`; a sentinel in that helper result appears if it is called directly. That remains a future live-probe service risk, not a route-level active path.

Next service plan:

1. Keep the legacy `LEGACY_LIVE_PROBE_DISABLED` response in place.
2. Keep caller-owned transaction behavior in the extracted route module.
3. Create a separate future live-probe service only if real external probing becomes a requirement, with explicit timeout, redaction, transport spy tests, and no raw adapter message passthrough.
4. Audit `POST /api/admin/ai/prompts` before any prompt mutation extraction, and keep legacy `/api/alignment/run` as a later execution-boundary task.
