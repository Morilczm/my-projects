# Route Extraction Checkpoint

Updated: 2026-07-15

This document records the real repository state at the Task 9C.3C checkpoint. It is a cumulative checkpoint for previously verified route extraction and pilot hardening work; it does not pretend that Tasks 9C.1, 9C.2, 9C.2.1, 9C.3A, and 9C.3B were committed independently.

## Git Baseline

- Pre-checkpoint commit: `09c49e2fae0a8cf4de8c1b22100d4d6d0d591bcc`
- Pre-checkpoint branch: `dev`
- Checkpoint commit: the commit containing this file; record the exact SHA with `git rev-parse HEAD` after committing. A commit cannot include its own SHA in tracked content without creating a self-reference.
- Checkpoint purpose: establish a reproducible route-refactor baseline before any provider governance route extraction.

## Working Tree Inventory

Task 9C.3C generated `/private/tmp/lexibridge-checkpoint-inventory.json` before committing.

- Pre-stage modified tracked files at task start: 7
- Pre-stage untracked candidate files at task start: 371
- Final staged files in checkpoint inventory: 380
- Total classified files: 380
- Unknown files: 0
- Files selected for staging: 380
- Categories:
  - configuration: 10
  - documentation: 121
  - source: 126
  - frontend_asset: 2
  - tests: 121

Ignored local runtime files were not selected for staging, including `.env`, `backend/lexibridge.db`, `__pycache__`, and `.pytest_cache`.

## Historical Release Artifact

The historical `lexibridge AI/` artifact is not part of current source. It was a historical release/backup copy and is not required to build, test, run, or verify the current project.

- Original artifact manifest: 31 files, 9,850,040 bytes.
- Remaining files available at recovery time: 13 files, 9,584,911 bytes.
- Missing files cannot be restored from the current environment.
- Remaining content has been preserved outside the Git repository at:
  `$HOME/Documents/LexiBridge-AI-Archives/route-refactor-pre-checkpoint-20260714-INCOMPLETE`
- Archive status: `INCOMPLETE_SOURCE_ARCHIVED_FOR_PRESERVATION_ONLY`.
- The archive, manifests, zip files, databases, temporary files, and release copies must not be committed.
- The durable archive gate accepts this incomplete historical archive because the current effective source tree has no dependency on it.

## Route Layer Snapshot

- `backend/app.py` line count: 16,475
- Direct `@app.route` handlers remaining in `backend/app.py`: 147
- Extracted route modules: 4
- Extracted routes: 15
- `RouteCoreDependencies` fields: 9
- Circular imports detected by tests: no
- Duplicate endpoints detected by tests: no

## Extracted Route Modules

| Module | Routes | Register function | Register parameter count | Domain model fields |
|---|---:|---|---:|---:|
| `backend/routes/teacher_learning_analytics.py` | 3 | `register_teacher_learning_analytics_routes(app, *, core, models)` | 3 | 6 |
| `backend/routes/student_concept_cards.py` | 5 | `register_student_concept_card_routes(app, *, core, models, student_visible_course_names, student_course_access_service, record_student_course_access_audit)` | 6 | 5 |
| `backend/routes/concept_card_review.py` | 4 | `register_concept_card_review_routes(app, *, core, models)` | 3 | 6 |
| `backend/routes/concept_card_feedback.py` | 3 | `register_concept_card_feedback_routes(app, *, core, models)` | 3 | 6 |

All four modules use explicit `app.add_url_rule` registration to preserve existing URL, method, endpoint, request/response, audit, permission, visibility, review-policy, triage, and export contracts. Blueprint migration and app factory work remain deferred.

## RouteCoreDependencies Boundary

`backend/routes/shared.py` contains the shared route foundation. `RouteCoreDependencies` currently carries:

- `db`
- `audit_record_model`
- `audit_record_service`
- `current_time_text`
- `require_current_user`
- `get_route_audit_context`
- `attach_request_id_to_response`
- `api_success_with_audit_context`
- `api_error_with_audit_context`

It must remain limited to cross-domain route infrastructure. It must not grow into a service locator, include Flask `app`, store request-specific mutable state, include all models, or include domain services such as provider governance, review policy, feedback, or student card services.

## Remaining Route Domains

`backend/app.py` still owns most initialization and legacy route groups. Current direct route handler groups include:

| Domain | Approx. direct handlers | Risk | Notes |
|---|---:|---|---|
| Auth | 7 | high | Session, password reset, current-user contracts. |
| Courses and membership | 3 | medium | Course membership and legacy course routes remain coupled to app globals. |
| Upload/documents | 4 | high | File handling, parse-quality gate, knowledge source creation, audit. |
| Knowledge governance | 20 | high | Source/chunk/version lifecycle and indexing/rebuild helpers. |
| Alignment/provider governance | 14 | high | Provider policy, preflight, attach gates, no-network boundary. |
| Student progress/course routes | 5 | medium | Student progress and membership administration routes remain in app.py. |
| Remaining Concept Card/admin/review-policy routes | 6 | high | Draft/admin status and policy management routes remain. |
| Evidence/retrieval/search | 2 | medium | Evidence retrieval and bilingual evidence routes remain. |
| Jobs/storage/health | 6 | medium | Operational routes and worker controls remain. |
| Legacy term/glossary/feedback/pilot | 22 | medium | Legacy compatibility surface remains. |
| Other admin/evaluation/retrieval routes | 56 | high | Mixed admin, retrieval experiment, cost, audit, and production readiness routes. |

## Coupling Assessment

- Initialization order remains coupled through `backend/app.py` model declarations, migration helpers, auth helpers, audit helpers, and route registration.
- Auth/RBAC helpers are still fragmented across app-level helpers and domain services.
- Audit helpers are shared but route-specific audit payload construction still lives near route modules or legacy handlers.
- App factory and Blueprint migration should remain deferred until more route slices have contract tests and clean worktree verification.

## Next Slice Recommendation

Provider governance and preflight routes are a reasonable next route-extraction slice only after this checkpoint is committed and reproduced from a clean worktree. That slice must preserve provider policy gates, disabled external provider behavior, no-network checks, AuditRecord behavior, and OpenAPI parity.

Do not begin provider governance extraction from an uncommitted or unreproducible working tree.

## Task 9C.4A Update

Task 9C.4A extracts only read-only provider governance and preflight GET routes into `backend/routes/provider_governance.py`. It does not extract provider policy mutation, preflight execution, alignment verification execution, replay behavior, provider usage recording, credential management, or transport code.

Migrated routes:

- `GET /api/alignment/providers`
- `GET /api/alignment/providers/<provider_name>/policy`
- `GET /api/alignment/providers/<provider_name>/usage`
- `GET /api/alignment/providers/preflight/<preflight_uid>`
- `GET /api/alignment/providers/<provider_name>/preflight`

Provider routes still in `backend/app.py` after 9C.4A:

- `POST /api/alignment/providers/<provider_name>/policy`
- `POST /api/alignment/providers/<provider_name>/preflight`
- `POST /api/alignment/verify`
- `GET /api/admin/alignment-runs`
- `GET /api/admin/ai/providers`
- other legacy AI provider registry/health endpoints outside the alignment-provider governance group

Post-extraction route snapshot:

- `backend/app.py` line count: 16,385
- Direct `@app.route` handlers remaining in `backend/app.py`: 142
- Extracted route modules: 5
- Extracted routes: 20
- `RouteCoreDependencies` fields: 9
- `register_provider_governance_routes(app, *, core, models)` register parameter count: 3
- `ProviderGovernanceModels` fields: 3

The provider governance route module keeps provider services domain-specific and outside `RouteCoreDependencies`. Its GET handlers are local read paths: they query registry/policy/usage/preflight history and do not run transport, create verification runs, write provider usage, mutate policy, enable external providers, or call external networks.

Next provider slices should be decided from the remaining route list. Reasonable candidates are provider policy mutation or preflight execution, but real provider transport and external calls must remain disabled unless a later task explicitly changes that boundary with tests.

## Task 9C.4B Update

Task 9C.4B extracts only provider policy mutation into `backend/routes/provider_policy.py`. It does not extract provider preflight execution, alignment verification execution, replay behavior, provider usage recording, credential management, environment mutation, or transport code.

Migrated route:

- `POST /api/alignment/providers/<provider_name>/policy`

Provider routes still in `backend/app.py` after 9C.4B:

- `POST /api/alignment/providers/<provider_name>/preflight`
- `POST /api/alignment/verify`
- `GET /api/admin/alignment-runs`
- `GET /api/admin/ai/providers`
- other legacy AI provider registry/health endpoints outside the alignment-provider governance group

Post-extraction route snapshot:

- `backend/app.py` line count: 16,366
- Direct `@app.route` handlers remaining in `backend/app.py`: 141
- Extracted route modules: 6
- Extracted routes: 21
- `RouteCoreDependencies` fields: 9
- `register_provider_policy_routes(app, *, core, models, record_provider_governance_audit)` register parameter count: 4
- `ProviderPolicyModels` fields: 1

The provider policy route module keeps provider policy persistence in `services/provider_governance.py` and keeps the existing provider governance audit adapter explicit. Its POST handler writes only provider policy data and does not run transport, create verification runs, write provider usage, execute preflight, manage credentials, enable real external providers, or call external networks.

The next provider slice should be selected from the remaining route list. Provider preflight execution is the next reasonable candidate, but it should remain separate from alignment verification execution because those paths have different state and audit semantics.

## Task 9C.4C Update

Task 9C.4C extracts only provider preflight execution into `backend/routes/provider_preflight.py`. It does not extract alignment verification execution, provider usage writes, replay execution, credential management, environment mutation, or transport code.

Migrated route:

- `POST /api/alignment/providers/<provider_name>/preflight`

Provider routes still in `backend/app.py` after 9C.4C:

- `POST /api/alignment/verify`
- `GET /api/admin/alignment-runs`
- `GET /api/admin/ai/providers`
- other legacy AI provider registry/health endpoints outside the alignment-provider governance group

Post-extraction route snapshot:

- `backend/app.py` line count: 16,330
- Direct `@app.route` handlers remaining in `backend/app.py`: 140
- Extracted route modules: 7
- Extracted routes: 22
- `RouteCoreDependencies` fields: 9
- `register_provider_preflight_routes(app, *, core, models, record_provider_preflight_audit)` register parameter count: 4
- `ProviderPreflightModels` fields: 2

The provider preflight route module keeps preflight readiness logic in `services/provider_preflight.py` and keeps the existing provider preflight audit adapter explicit. Its POST handler creates only `AlignmentProviderPreflightRun` records and audit records, does not run transport, does not create alignment verification runs, does not write provider usage, does not mutate provider policy, does not manage credentials, and does not call external networks.

The next provider slice should not begin by moving `/api/alignment/verify`. First scan the verification route's state machine, provider usage writes, fake/replay provider behavior, result parsing, attach-to-card gate, audit semantics, and no-network/external-provider gates before deciding the next extraction boundary.

## Task 9C.4D Update

Task 9C.4D does not extract a route. It adds characterization coverage and documents the boundary of `POST /api/alignment/verify` in `docs/alignment_verification_route_boundary.md`.

Current verification route snapshot:

- Route: `POST /api/alignment/verify`
- Endpoint: `verify_alignment_api`
- Handler location: `backend/app.py:12059` through `backend/app.py:12339`
- Handler size: 281 lines including decorator and blanks
- Direct model dependencies: 4 (`ConceptAlignmentCard`, `AlignmentProviderPolicy`, `AlignmentProviderUsageRecord`, `AlignmentVerificationRun`)
- Main write tables: `alignment_verification_run`, `alignment_provider_usage_record`, optional `concept_alignment_card`, and `audit_record`
- Provider modes characterized: `mock-rule-v1`, `fake-llm-v1`, `external-llm-replay-v1`, `deepseek-alignment-v1-disabled`
- Verification route conclusion: `SERVICE_BOUNDARY_REQUIRED_FIRST`

The route handler still owns too much execution orchestration for direct movement into a route module. It sequences initial audit, provider existence checks, card-vs-payload input construction, provider governance, policy-block run creation, provider execution, provider usage recording, optional card attach, completion/failed audit, and rollback behavior. The next step should create or extend a domain service that owns this transaction and returns the existing response contract; only after that service boundary is frozen should route extraction proceed.

Post-9C.4D route snapshot remains:

- `backend/app.py` line count: 16,330
- Direct `@app.route` handlers remaining in `backend/app.py`: 140
- Extracted route modules: 7
- Extracted routes: 22
- `RouteCoreDependencies` fields: 9

Provider routes still in `backend/app.py` after 9C.4D:

- `POST /api/alignment/verify`
- `GET /api/admin/alignment-runs`
- `GET /api/admin/ai/providers`
- other legacy AI provider registry/health endpoints outside the alignment-provider governance group

## Task 9C.4D.1 Update

Task 9C.4D.1 does not extract `POST /api/alignment/verify` into a route module. It creates an application-layer execution service boundary:

- Service module: `backend/services/alignment_verification_execution.py`
- Public entry point: `execute_alignment_verification(...)`
- Request DTO: `AlignmentVerificationExecutionRequest`
- Actor DTO: `AlignmentVerificationActor`
- Context DTO: `AlignmentVerificationExecutionContext`
- Dependency object: `AlignmentVerificationExecutionDependencies`
- Result DTO: `AlignmentVerificationExecutionResult`

The service owns provider existence checks, card-vs-payload input branching, provider governance, `AlignmentVerificationRun`, `AlignmentProviderUsageRecord`, mock/fake/replay/disabled provider dispatch, output parsing through existing services, optional card attach, audit sequencing, and business transaction commit/rollback. It does not import Flask, `backend.app`, route modules, credential resolvers, provider clients, or external transport.

`verify_alignment_api` remains registered in `backend/app.py` with the same URL, method, and endpoint name. It is now a thin HTTP adapter that handles auth, request parsing, request ID/audit context, DTO construction, service invocation, and response mapping.

Post-9C.4D.1 snapshot:

- `backend/app.py` line count: 16,133
- `verify_alignment_api` adapter size: 35 lines including decorator and blanks
- Direct `@app.route` handlers remaining in `backend/app.py`: 140
- Extracted route modules: 7
- Extracted routes: 22
- RouteCoreDependencies fields: 9
- Alignment verification execution service dataclasses: 5

The next safe slice is to move only the thin `/api/alignment/verify` route adapter into a route module. That task must not move or rewrite the execution state machine, usage semantics, attach gate, audit events, or transaction behavior.

## Task 9C.4E Update

Task 9C.4E extracts only the already-thin `POST /api/alignment/verify` HTTP adapter into `backend/routes/alignment_verification.py`.

- New route module: `backend/routes/alignment_verification.py`
- Route count: 1
- Registered route: `POST /api/alignment/verify`
- Flask endpoint: `verify_alignment_api`
- Register signature: `register_alignment_verification_routes(app, *, core, execution_dependencies, execute_fn=execute_alignment_verification)`
- Execution dependency boundary: `AlignmentVerificationExecutionDependencies` remains an explicit verification-domain dependency and is not added to `RouteCoreDependencies`.
- Execution service API: unchanged.
- Business owner: `backend/services/alignment_verification_execution.py`

The route module owns only auth, request parsing with the existing `silent=True` behavior, request ID/audit context, DTO construction, execution service invocation, and response mapping. It does not access `AlignmentVerificationRun`, `AlignmentProviderUsageRecord`, `AlignmentProviderPolicy`, provider transport, credentials, parser internals, card attach logic, or business commit/rollback.

Post-9C.4E snapshot:

- `backend/app.py` line count: 16,075
- Direct `@app.route` handlers remaining in `backend/app.py`: 139
- Extracted route modules: 8
- Extracted routes: 23
- RouteCoreDependencies fields: 9

Remaining provider/admin-adjacent route domains include admin alignment run listing, legacy AI provider/admin views, upload/knowledge/evidence routes, course and policy management routes, and other legacy app routes. The next provider-related slice should be selected from the remaining route inventory and must not re-open external provider execution unless a separate task explicitly hardens that path.

## Task 9C.4F Update

Task 9C.4F does not extract any route. It adds `docs/provider_admin_route_inventory.md` and characterization coverage for the remaining provider/admin-adjacent routes in `backend/app.py`.

Characterized remaining provider/admin routes:

- `GET /api/admin/alignment-runs`
- `GET /api/admin/ai/providers`
- `GET /api/admin/ai/models`
- `GET, POST /api/admin/ai/prompts`
- `GET /api/admin/ai/calls`
- `GET /api/admin/ai/usage`
- `GET /api/admin/ai/health`
- `POST /api/admin/ai/healthcheck`
- `POST /api/alignment/run`
- `GET /api/alignment/runs`
- `GET /api/alignment/runs/<int:run_id>`

Inventory result:

- Unknown provider/admin route count: 0
- `GET /api/admin/alignment-runs`: `READ_ONLY_ADMIN_LISTING`, direct extraction safe
- legacy `/api/admin/ai/*`: active frontend/OpenAPI surface, overlaps formal provider governance but is not an alias; requires deprecation/compatibility or service-boundary work before extraction
- `POST /api/admin/ai/healthcheck`: `HEALTH_EXTERNAL_RISK` at audit time because live provider mode plus `live_probe=true` could call provider transport before 9C.4L.1 disabled that route path
- `POST /api/alignment/run`: `SERVICE_BOUNDARY_REQUIRED` because it creates legacy `AlignmentRun`, background jobs/cards, usage, and commits
- legacy `/api/alignment/runs*`: active frontend/OpenAPI read paths tied to the older `AlignmentRun` surface

Post-9C.4F snapshot:

- `backend/app.py` line count: 16,075
- Direct `@app.route` handlers remaining in `backend/app.py`: 139
- Extracted route modules: 8
- Extracted routes: 23
- `RouteCoreDependencies` fields: 9

Primary next-slice conclusion: `GO_ADMIN_ALIGNMENT_RUNS_EXTRACTION`.

The next route extraction should be limited to `GET /api/admin/alignment-runs`. It must not include legacy `/api/admin/ai/*`, `/api/alignment/run`, `/api/alignment/runs`, provider healthcheck, prompt mutation, or external provider transport. Legacy provider admin routes need a separate compatibility/deprecation audit before they are moved.

## Task 9C.4G Update

Task 9C.4G extracts only the legacy admin alignment run listing into `backend/routes/admin_alignment_runs.py`.

- New route module: `backend/routes/admin_alignment_runs.py`
- Route count: 1
- Registered route: `GET /api/admin/alignment-runs`
- Flask endpoint: `admin_alignment_runs`
- Register signature: `register_admin_alignment_run_routes(app, *, core, models, serialize_alignment_run)`
- Domain model dependency: `AdminAlignmentRunModels(AlignmentRun)`
- Serializer dependency: existing `serialize_alignment_run` passed explicitly from `backend/app.py`
- RouteCoreDependencies fields: 9

The route module preserves the existing admin-only permission boundary, id-desc/limit-300 ordering, no-query-filter behavior, top-level `{"status", "runs"}` response shape, absence of `request_id`, and absence of view AuditRecord writes. It does not query or mutate `AlignmentVerificationRun`, `AlignmentProviderUsageRecord`, provider policy, provider preflight, Concept Cards, replay state, or provider transport.

Post-9C.4G snapshot:

- `backend/app.py` line count: 16,074
- Direct `@app.route` handlers remaining in `backend/app.py`: 138
- Extracted route modules: 9
- Extracted routes: 24

Remaining provider/admin-adjacent route domains:

- active legacy `/api/admin/ai/*` provider admin views and prompt mutation;
- `POST /api/admin/ai/healthcheck`, which has a live-probe transport risk;
- legacy `/api/alignment/run`, which still owns execution/background-job/card/usage orchestration;
- legacy `/api/alignment/runs` and `/api/alignment/runs/<int:run_id>` read paths.

Do not migrate `/api/admin/ai/*` as the next step without a separate compatibility/deprecation audit. Healthcheck and `/api/alignment/run` require explicit service/security boundaries before route extraction.

## Task 9C.4H Update

Task 9C.4H does not extract any route. It adds `docs/legacy_provider_admin_surface.md` and characterization coverage for the active legacy `/api/admin/ai/*` provider admin surface.

Characterized legacy provider admin routes:

- `GET /api/admin/ai/providers`
- `GET /api/admin/ai/models`
- `GET /api/admin/ai/prompts`
- `POST /api/admin/ai/prompts`
- `GET /api/admin/ai/calls`
- `GET /api/admin/ai/usage`
- `GET /api/admin/ai/health`
- `POST /api/admin/ai/healthcheck`

Inventory result:

- Unknown legacy provider admin route count: 0
- All `/api/admin/ai/*` routes are admin-only and present in OpenAPI.
- The frontend uses the six legacy GET views: providers, models, prompts, calls, usage, and health.
- `GET /api/admin/ai/providers`, `/models`, `/prompts`, and `/health` call the legacy registry seed path; after 9C.4J the implementation lives in `backend/services/legacy_provider_registry_seed.py` behind the `ensure_ai_registry_seed(...)` compatibility wrapper. Characterization shows the GET seed path flushes default registry/model/prompt rows for the response but does not persist them without a later commit.
- `POST /api/admin/ai/prompts` is a mutation and commits `PromptTemplate` changes.
- `POST /api/admin/ai/healthcheck` commits provider health fields and may also persist env-selected seed rows.
- Before 9C.4L.1, `POST /api/admin/ai/healthcheck` passed `live_probe=True` into provider health logic for an enabled live provider; `services.ai_health.healthcheck_provider(...)` called the provider adapter only in live mode with non-placeholder credential and `live_probe=true`.

Primary conclusion: `SPLIT_READONLY_AND_HEALTHCHECK_FIRST`.

Next safe slice: extract only the safe legacy read-only admin provider views after splitting them away from prompt mutation and healthcheck transport risk. Do not migrate `/api/admin/ai/healthcheck` until a service boundary separates local health summary from live transport probing. Do not migrate `POST /api/alignment/run` as part of this provider admin slice.

## Task 9C.4I Update

Task 9C.4I extracts only legacy provider admin observability GET views into `backend/routes/legacy_provider_admin_observability.py`.

Migrated routes:

- `GET /api/admin/ai/calls`
- `GET /api/admin/ai/usage`
- `GET /api/admin/ai/health`

Routes intentionally left in `backend/app.py`:

- `GET /api/admin/ai/providers`
- `GET /api/admin/ai/models`
- `GET /api/admin/ai/prompts`
- `POST /api/admin/ai/prompts`
- `POST /api/admin/ai/healthcheck`
- legacy `/api/alignment/run`
- legacy `/api/alignment/runs`
- legacy `/api/alignment/runs/<int:run_id>`

Post-9C.4I snapshot:

- `backend/app.py` line count: 16,068
- Direct `@app.route` handlers remaining in `backend/app.py`: 135
- Extracted route modules: 10
- Extracted routes: 27
- `RouteCoreDependencies` fields: 9
- `register_legacy_provider_admin_observability_routes(app, *, core, models, serializers, registry_seed_service)` register parameter count: 5
- `LegacyProviderAdminObservabilityModels` fields: 2
- `LegacyProviderAdminObservabilitySerializers` fields: 4

The route module keeps the legacy endpoint names, admin-only permission, OpenAPI/frontend URLs, legacy `api_success` envelopes without `request_id`, id-desc limits, local health seed-flush behavior, and no view `AuditRecord`. It does not commit or roll back, does not execute live health probes, does not call provider transport, does not create verification runs, does not write provider usage, and does not mutate provider policy, provider preflight, prompts, cards, or credentials.

Next recommended slice: audit and isolate seed-backed provider/model/prompt configuration GET behavior before extraction, or establish a dedicated healthcheck service boundary that separates local health summary from live transport probing. Do not move `POST /api/admin/ai/healthcheck` or `POST /api/alignment/run` as part of an observability route slice.

## Task 9C.4J Seed Service Boundary

Task 9C.4J does not extract any route. It moves the legacy provider registry seed implementation into `backend/services/legacy_provider_registry_seed.py` and keeps `backend/app.py::ensure_ai_registry_seed(...)` as a compatibility wrapper for existing app-local routes, non-route callers, and the extracted local health view dependency.

The new service API is:

- `LegacyProviderRegistrySeedModels(AIProviderConfig, AIModelRegistry, PromptTemplate)`
- `LegacyProviderRegistrySeedResult(provider_config, model, prompts, created_provider, created_model, created_prompt_count, updated_provider)`
- `ensure_legacy_provider_registry_seed(db, models, selection, default_prompts, current_time_text, model_version, owner_user_id)`

The service owns only lookup/create/update-default and `flush` behavior. It does not import Flask, `backend.app`, or route modules; it does not read credentials, call provider transport, execute health probes, write `AuditRecord`, or call `commit`/`rollback`. Callers still own transaction outcome and response contracts.

Seed transaction semantics remain unchanged:

- `GET /api/admin/ai/providers`, `/models`, `/prompts`, and `/health` can flush missing provider/model/prompt rows for the response but do not explicitly commit.
- `POST /api/admin/ai/prompts` keeps its existing prompt mutation commit ownership and can persist missing seed rows only through that existing commit.
- `POST /api/admin/ai/healthcheck` keeps its existing provider health commit ownership and can persist missing seed rows only through that existing commit.
- `call_ai_task(...)` and `ai_selection_from_config(...)` fallback keep their historical caller-owned transaction behavior.

Natural-key idempotency remains lookup-before-create based on `provider_name`, `provider_name + model_name`, and `prompt_key + prompt_version`; there are still no new schema constraints. Concurrent duplicate creation remains a documented production-hardening risk.

Post-9C.4J status:

- No new route module.
- No additional extracted route.
- `backend/app.py` line count: 16,005.
- Direct `@app.route` handlers remaining in `backend/app.py`: 135.
- Extracted route modules: 10.
- Extracted routes: 27.
- `RouteCoreDependencies` fields: 9.
- Provider/model/prompt configuration GET routes still remain in `backend/app.py`.
- `POST /api/admin/ai/healthcheck`, `POST /api/admin/ai/prompts`, and legacy `/api/alignment/run` remain separate future tasks.

Next recommended slice: if 9C.4J gates pass, migrate only the seed-backed provider/model/prompt GET views in a narrow task. Keep prompt mutation, healthcheck live transport, and legacy alignment execution out of that slice.

## Task 9C.4K Legacy Provider Configuration Routes

Task 9C.4K extracts only the seed-backed legacy provider admin configuration GET views into `backend/routes/legacy_provider_admin_configuration.py`:

- `GET /api/admin/ai/providers`
- `GET /api/admin/ai/models`
- `GET /api/admin/ai/prompts`

At the time of 9C.4K, the module registered the shared `/api/admin/ai/prompts` endpoint with `GET` and `POST` to preserve the Flask endpoint name `admin_ai_prompts`, while POST mutation logic remained app-owned through an explicit callback. Task 9C.4R later removed that callback and moved the thin POST adapter into the same route module.

Register signature:

9C.4K register signature at extraction time used an app-owned POST mutation callback parameter. That transitional dependency is historical only; Task 9C.4R removed it and replaced it with explicit prompt mutation service dependencies in the same route module.

Current post-9C.4R register signature shape:

`register_legacy_provider_admin_configuration_routes(app, *, core, models, serializers, registry_seed_service, seed_models, provider_selection_factory, default_prompts, model_version_factory, prompt_mutation_service, prompt_mutation_dependencies)`

The extracted GET views call `ensure_legacy_provider_registry_seed(...)` directly as an explicit domain dependency. They preserve admin-only access, OpenAPI/frontend URLs, legacy `api_success` envelopes without `request_id`, no view `AuditRecord`, provider/model/prompt ordering, seed flush/no-explicit-commit behavior, and no transport/live-probe behavior.

Post-9C.4K status:

- New route module: `backend/routes/legacy_provider_admin_configuration.py`.
- Migrated GET routes in this slice: 3.
- `backend/app.py` line count: 16,007.
- Direct `@app.route` handlers remaining in `backend/app.py`: 132.
- Extracted route modules: 11.
- Extracted routes: 30.
- `RouteCoreDependencies` fields: 9.
- `POST /api/admin/ai/prompts`, `POST /api/admin/ai/healthcheck`, and legacy `/api/alignment/run` remain separate future tasks.

Historical next slice after 9C.4K: audit the healthcheck boundary before any `POST /api/admin/ai/healthcheck` route extraction; prompt mutation and legacy `/api/alignment/run` remain separate tasks.

## Task 9C.4L Legacy Provider Healthcheck Boundary Audit

Task 9C.4L does not extract a route and does not modify production behavior. It adds `tests/test_legacy_provider_healthcheck_characterization.py` and `docs/legacy_provider_healthcheck_boundary.md`.

Findings:

- `POST /api/admin/ai/healthcheck` remains in `backend/app.py`.
- Endpoint remains `admin_ai_healthcheck`.
- The handler is 16 function body lines, 17 lines including the decorator.
- It calls `ensure_ai_registry_seed(...)`, reads optional `live_probe`, checks all enabled `AIProviderConfig` rows, writes provider health fields, commits, and returns the legacy `api_success` envelope without `request_id`.
- Local readiness paths do not call transport.
- Before 9C.4L.1, live probe transport intent existed for enabled live providers with usable credential and `live_probe=true`.
- The lower-level live probe helper still echoes adapter error `message` if called directly, so any future live-probe service needs an explicit redaction boundary before being enabled.
- No route module was added.
- `backend/app.py` line count remains 16,007.
- Direct `@app.route` handlers remaining in `backend/app.py`: 132.
- Extracted route modules: 11.
- Extracted routes: 30.
- `RouteCoreDependencies` fields: 9.

Task 9C.4L conclusion: `DISABLE_OR_DEPRECATE_LIVE_PROBE_FIRST`.

Next recommended slice: before extracting `POST /api/admin/ai/healthcheck`, disable/deprecate live probe behavior or create a dedicated live-probe service with explicit redaction, timeout/error mapping, and transport spy tests. Then split local readiness into its own service and only afterwards move the thin route adapter. Keep `POST /api/admin/ai/prompts` and legacy `/api/alignment/run` separate.

## Task 9C.4L.1 Legacy Live Probe Disable

Task 9C.4L.1 keeps `POST /api/admin/ai/healthcheck` in `backend/app.py` and does not introduce a route module.

Security behavior change:

- URL/method/endpoint remain `POST /api/admin/ai/healthcheck` and `admin_ai_healthcheck`.
- Admin-only permission and the legacy `api_success` envelope remain unchanged.
- `live_probe` omitted and `live_probe=false` keep the local readiness path.
- `live_probe=true` for enabled live providers returns `health_status=unknown` and `error_code=LEGACY_LIVE_PROBE_DISABLED`.
- The disabled result uses a stable safe message and does not include raw adapter exceptions or credentials.
- Provider adapter, provider transport, socket, requests, httpx, and urllib call counts remain zero through the legacy route.
- Seed flush and route-owned commit behavior are preserved.
- Write-set remains limited to local healthcheck seed/health fields; no provider usage, verification run, preflight run, provider call, card, or AuditRecord is created.
- Readiness now includes a provider network-disabled smoke check that calls the legacy healthcheck with `live_probe=true` against an enabled live provider and asserts `LEGACY_LIVE_PROBE_DISABLED` without network.

Post-9C.4L.1 status:

- No new route module.
- No additional extracted route.
- `backend/app.py` direct route count remains 132.
- Extracted route modules remain 11.
- Extracted routes remain 30.
- `RouteCoreDependencies` remains 9 fields.

Post-9C.4L.1 next slice was Task 9C.4M, which established the local readiness service while preserving the disabled live-probe response. After 9C.4M, the next safe slice is moving the thin healthcheck HTTP adapter to a route module. Keep prompt mutation and legacy `/api/alignment/run` separate.

## Task 9C.4M Legacy Provider Local Readiness Service

Task 9C.4M keeps `POST /api/admin/ai/healthcheck` in `backend/app.py` and adds `backend/services/legacy_provider_local_readiness.py`.

Service API:

- `LegacyProviderLocalReadinessRequest(live_probe_requested)`
- `LegacyProviderLocalReadinessProvider(provider_name, provider_mode, model_name, enabled, credential_present, adapter_available, external_execution_enabled)`
- `LegacyProviderLocalReadinessResult(...)`
- `evaluate_legacy_provider_local_readiness(request, provider)`

Boundary:

- The service has no Flask, `backend.app`, route, provider adapter, provider transport, environment, credential, commit, rollback, AuditRecord, usage, verification, preflight, card, or network dependency.
- The healthcheck route now passes only `credential_present: bool`; it does not pass API keys or raw environment values to the service.
- `live_probe=true` keeps returning `LEGACY_LIVE_PROBE_DISABLED`.
- `live_probe` omitted and `live_probe=false` keep local readiness behavior.
- Seed remains owned by `backend/services/legacy_provider_registry_seed.py`.
- The route still owns provider query, health-field writes, `last_healthcheck_at`, `updated_at`, commit, and the legacy `api_success` envelope without `request_id`.

Post-9C.4M status:

- No new route module.
- No additional extracted route.
- `backend/app.py` direct route count remains 132.
- Extracted route modules remain 11.
- Extracted routes remain 30.
- `RouteCoreDependencies` remains 9 fields.

Next recommended slice after 9C.4M was moving the now-thin `POST /api/admin/ai/healthcheck` HTTP adapter into a route module. Keep `POST /api/admin/ai/prompts` and legacy `/api/alignment/run` separate.

## Task 9C.4N Legacy Provider Healthcheck Route

Task 9C.4N extracts only the thin legacy provider admin healthcheck HTTP adapter into `backend/routes/legacy_provider_admin_healthcheck.py`.

Register signature:

`register_legacy_provider_admin_healthcheck_routes(app, *, core, models, serializers, registry_seed_service, seed_models, provider_selection_factory, default_prompts, model_version_factory, local_readiness_service, credential_presence_resolver)`

The module preserves:

- URL/method/endpoint: `POST /api/admin/ai/healthcheck`, `admin_ai_healthcheck`;
- admin-only permission;
- optional JSON body behavior, including malformed/empty body behavior;
- legacy `api_success` response envelope without success `request_id`;
- no `AuditRecord` behavior;
- seed service integration and flush semantics;
- route-owned health-field writes and single commit;
- `LEGACY_LIVE_PROBE_DISABLED` for `live_probe=true`;
- credential boundary as `credential_presence_resolver(config) -> bool`;
- no adapter, transport, provider call, usage, verification run, preflight run, card, or external network behavior.

Post-9C.4N status:

- New route module: `backend/routes/legacy_provider_admin_healthcheck.py`.
- Migrated route in this slice: 1.
- `backend/app.py` line count: 16,036.
- Direct `@app.route` handlers remaining in `backend/app.py`: 131.
- Extracted route modules: 12.
- Extracted routes: 31.
- `RouteCoreDependencies` fields: 9.

Next recommended slice: audit `POST /api/admin/ai/prompts` mutation, including its seed, validation, serializer, commit/rollback, OpenAPI/frontend, and shared `admin_ai_prompts` endpoint compatibility. Keep legacy `/api/alignment/run` as a separate execution-boundary audit, and do not re-enable legacy live probing without a new explicit service.

## Task 9C.4O Legacy Provider Prompt Mutation Audit

Task 9C.4O does not extract a route and does not change production behavior. It adds characterization for `POST /api/admin/ai/prompts` and records the detailed boundary in `docs/legacy_provider_prompt_mutation_boundary.md`.

Confirmed registration:

- `GET /api/admin/ai/prompts` and `POST /api/admin/ai/prompts` share one Flask rule.
- The endpoint remains `admin_ai_prompts`.
- GET is handled by `backend/routes/legacy_provider_admin_configuration.py`.
- At audit time, POST delegated through an app-owned callback. Task 9C.4R later removed this callback.

Prompt mutation snapshot at the time of the 9C.4O audit:

- The callback is 22 lines.
- It performs one upsert operation on `PromptTemplate`.
- The target key is `prompt_key` + `prompt_version`.
- The implementation requires only `prompt_key` and `prompt_version`, while OpenAPI also marks `task_type` and `template_text` required.
- It commits directly and has no explicit rollback.
- It writes no `AuditRecord`.
- It performs no network, provider adapter, provider transport, usage, verification run, preflight, or card writes.

Post-9C.4O status:

- No new route module.
- No additional extracted route.
- `backend/app.py` line count remains 16,036.
- Direct `@app.route` handlers remaining in `backend/app.py`: 131.
- Extracted route modules remain 12.
- Extracted routes remain 31.
- `RouteCoreDependencies` remains 9 fields.

Primary conclusion: `PROMPT_VERSIONING_OR_CONCURRENCY_POLICY_REQUIRED_FIRST`.

Next recommended slice: define prompt mutation policy before service extraction. The policy must cover validation, legal prompt template handling, version creation versus in-place update, active/default exclusivity, duplicate key/version handling, optimistic locking or accepted last-write-wins behavior, and explicit transaction rollback semantics. Only after that should a prompt mutation application service and route extraction be attempted. Keep legacy `/api/alignment/run` separate.

## Task 9C.4P Legacy Prompt Mutation Policy

Task 9C.4P does not extract a route and does not change production behavior. It adds `docs/adr/ADR-legacy-prompt-mutation-policy.md` and accepts `LEGACY_PROMPT_MUTABLE_REVISION_V1` for the current small pilot.

Policy summary:

- Identity remains `(prompt_key, prompt_version)`.
- Missing key/version creates one `PromptTemplate`.
- Existing key/version updates the first matching row in place.
- `prompt_version` is client-provided and opaque.
- No immutable history, uniqueness guarantee, optimistic locking, conflict status, or active/default exclusivity is provided.
- Runtime contract remains the compatibility source; OpenAPI still overstates required fields.
- The next service must own one commit and explicit rollback.

Post-9C.4P status:

- No new route module.
- No additional extracted route.
- `backend/app.py` direct route count remains 131.
- Extracted route modules remain 12.
- Extracted routes remain 31.
- `RouteCoreDependencies` remains 9 fields.

## Task 9C.4Q Legacy Prompt Mutation Service

Task 9C.4Q adds `backend/services/legacy_provider_prompt_mutation.py` and keeps `POST /api/admin/ai/prompts` in the existing shared route/callback registration.

Service API:

- `LEGACY_PROMPT_MUTATION_POLICY`
- `LegacyPromptMutationRequest`
- `LegacyPromptMutationDependencies`
- `LegacyPromptMutationResult`
- `execute_legacy_prompt_mutation(request=..., dependencies=...)`

Boundary:

- The service implements `LEGACY_PROMPT_MUTABLE_REVISION_V1`.
- It owns runtime-compatible validation, seed integration, `(prompt_key, prompt_version)` lookup, mutable revision create/update, one commit, and explicit rollback.
- It does not import Flask, `backend.app`, route modules, provider adapter/transport, environment, credentials, or AuditRecord.
- The app callback no longer directly queries, creates, updates, commits, or rolls back `PromptTemplate`.
- GET `/api/admin/ai/prompts` remains handled by `backend/routes/legacy_provider_admin_configuration.py`.
- At the end of 9C.4Q, POST `/api/admin/ai/prompts` still used the shared `admin_ai_prompts` rule and app-owned callback; route extraction was still pending.

Post-9C.4Q status:

- No new route module.
- No additional extracted route.
- `backend/app.py` line count: 16,057.
- Direct `@app.route` handlers remaining in `backend/app.py`: 131.
- Extracted route modules remain 12.
- Extracted routes remain 31.
- `RouteCoreDependencies` remains 9 fields.

## Task 9C.4R Legacy Prompt Mutation POST Route

Task 9C.4R moves the now-thin `POST /api/admin/ai/prompts` HTTP adapter into `backend/routes/legacy_provider_admin_configuration.py` and removes the temporary app-owned `admin_ai_prompts_post_handler` callback.

Current registration:

`register_legacy_provider_admin_configuration_routes(app, *, core, models, serializers, registry_seed_service, seed_models, provider_selection_factory, default_prompts, model_version_factory, prompt_mutation_service, prompt_mutation_dependencies)`

Boundary:

- GET and POST still share one Flask rule and endpoint: `/api/admin/ai/prompts`, `admin_ai_prompts`.
- The POST branch constructs `LegacyPromptMutationRequest`, calls the injected prompt mutation service, and maps the typed result to the existing legacy response envelope.
- The route module does not query or mutate `PromptTemplate` directly and does not commit or roll back.
- `backend/services/legacy_provider_prompt_mutation.py` continues to own seed integration, key/version lookup, mutable revision upsert, one commit, and explicit rollback.
- No schema, frontend, OpenAPI, policy, or service API change is included.

Post-9C.4R status:

- No new route module; the existing configuration route module now fully owns the shared prompt GET/POST HTTP adapter.
- Newly fully extracted route in this slice: 1 (`POST /api/admin/ai/prompts`).
- `backend/app.py` line count: 16,044.
- Direct `@app.route` handlers remaining in `backend/app.py`: 131.
- Direct route count did not change because the POST method was already registered by the configuration route module as part of the shared GET/POST rule; this task removed the app-owned callback, not an `@app.route` decorator.
- Extracted route modules remain 12.
- Extracted routes: 32.
- `RouteCoreDependencies` remains 9 fields.

Next recommended slice: Task 9C.4S audits legacy `/api/alignment/run` as a separate execution-boundary task.

## Task 9C.4S Legacy Alignment Run Boundary Audit

Task 9C.4S does not extract a route and does not modify production behavior. It
adds `tests/test_legacy_alignment_run_characterization.py` and
`docs/legacy_alignment_run_boundary.md`.

Findings:

- `POST /api/alignment/run` remains in `backend/app.py`.
- Route: `/api/alignment/run`
- Method: `POST`
- Endpoint: `run_alignment`
- Handler location: `backend/app.py:10125` through `backend/app.py:10284`
- Handler size: 160 lines including decorator, 159 function lines.
- Active frontend caller: `frontend/index.html::runAlignmentForDocument`.
- OpenAPI path exists, but does not describe the `sync` query parameter or all
  three response shapes.
- The legacy route writes `AlignmentRun`, `BackgroundJob`, `TerminologyCard`,
  legacy `UsageRecord`, and `AICallLog` paths, not `AlignmentVerificationRun`.
- The legacy route bypasses formal provider policy, provider preflight,
  provider usage, request-id, audit, formal parser, and attach gates.
- Async default requests queue an `AlignmentRun` and `BackgroundJob` without
  immediate provider execution.
- Sync direct/document requests use legacy evidence, prompt, card, and provider
  helper paths.
- A live default provider with a usable key can reach legacy `urllib` transport
  intent before local fallback, so no real network is allowed in tests.
- Repeated async requests are not idempotent and create distinct
  `AlignmentRun`/`BackgroundJob` rows.
- The handler contains commit points but no explicit rollback.

Main conclusion:

`DEPRECATE_LEGACY_ALIGNMENT_RUN_FIRST`

Post-9C.4S status:

- No new route module.
- No additional extracted route.
- `backend/app.py` direct route count remains 131.
- Extracted route modules remain 12.
- Extracted routes remain 32.
- `RouteCoreDependencies` remains 9 fields.

Next recommended slice: define a legacy `/api/alignment/run`
deprecation/compatibility policy. Do not extract the current handler as an
application service unchanged, and do not delete the endpoint before replacing
or disabling the active frontend document-alignment flow.

## Task 9C.4T Legacy Alignment Run Deprecation Policy

Task 9C.4T does not modify production code, does not move the route, and does
not change OpenAPI or frontend behavior. It accepts
`LEGACY_ALIGNMENT_RUN_DEPRECATION_V1` in
`docs/adr/ADR-legacy-alignment-run-deprecation.md`.

Policy summary:

- current role: `TEMPORARY_FRONTEND_COMPATIBILITY_ONLY`;
- legacy external execution: `PROHIBITED`;
- safe transition: `LOCAL_OR_DETERMINISTIC_ONLY`;
- replacement: `FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`;
- direct alias to `/api/alignment/verify`: `PROHIBITED`;
- dual write: `PROHIBITED`;
- post-cutover legacy data: retain read-only;
- disable response after zero callers: HTTP 410 with
  `LEGACY_ALIGNMENT_RUN_DEPRECATED`.

Post-9C.4T status:

- No new route module.
- No additional extracted route.
- `POST /api/alignment/run` remains in `backend/app.py`.
- `backend/app.py` direct route count remains 131.
- Extracted route modules remain 12.
- Extracted routes remain 32.
- `RouteCoreDependencies` remains 9 fields.

Next recommended slice after 9C.4T: disable legacy alignment external/live
execution and credential flow while keeping the current frontend compatibility
contract. Do not build the replacement document-alignment workflow in the same
task.

## Task 9C.4U Legacy Alignment External Execution Containment

Task 9C.4U keeps `POST /api/alignment/run` in `backend/app.py`; it is not a
route extraction. It adds a pure provider classification boundary and blocks
legacy external/live execution before route writes, worker execution, retry, or
direct helper transport intent.

Post-9C.4U status:

- `POST /api/alignment/run` URL/method/endpoint remain unchanged.
- The frontend document-alignment compatibility flow remains active.
- External/live intent returns or records `LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED`.
- Safe transitional providers are explicit allowlist values only:
  `none`, `mock`, and `local_heuristic` aliases.
- Unknown/custom provider names and custom endpoint/base URL metadata fail
  closed.
- `urllib.Request`, `urlopen`, socket, adapter construction, and credential
  metadata are not reached on blocked route/worker/helper paths.
- Historical queued/running/retrying external legacy jobs are quarantined by
  the worker gate and cannot be retried into execution.
- OpenAPI marks `/api/alignment/run` as deprecated but does not declare HTTP
  410 or a replacement endpoint.
- Direct `@app.route` count remains unchanged because the route was not moved.

Next recommended slice: define the formal document alignment workflow contract
and boundary. Do not extract the legacy route as a service and do not cut over
the frontend until the replacement workflow exists.

## Task 9C.4V Formal Document Alignment Workflow Contract

Task 9C.4V does not modify production code, does not add a route, does not add
models, and does not modify frontend or OpenAPI. It defines the replacement
contract for legacy document alignment in
`docs/adr/ADR-formal-document-alignment-workflow.md` and
`docs/formal_document_alignment_workflow_boundary.md`.

Contract summary:

- workflow: `FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION`;
- status: `PROPOSED_FOR_SMALL_PILOT`;
- canonical input: `GOVERNED_KNOWLEDGE_SOURCE`;
- execution model: `ASYNC_JOB_ORCHESTRATION`;
- start endpoint target: `POST /api/document-alignment-runs`;
- status endpoint target: `GET /api/document-alignment-runs/{run_uid}`;
- item endpoint target: `GET /api/document-alignment-runs/{run_uid}/items`;
- idempotency: `Idempotency-Key`, not request ID;
- root model required: `DocumentAlignmentWorkflowRun`;
- item model required: `DocumentAlignmentWorkflowItem`;
- data policy: `NO_LEGACY_AND_FORMAL_DUAL_WRITE`;
- provider path: formal governance, policy, preflight, verification, parser,
  usage, and audit only.

Post-9C.4V status:

- `POST /api/alignment/run` remains in `backend/app.py`.
- Legacy external/live execution remains disabled by 9C.4U.
- Frontend still calls the legacy route.
- No new route module.
- No additional extracted route.
- Direct `@app.route` count remains unchanged.
- Extracted route modules remain 12.
- Extracted routes remain 32.
- `RouteCoreDependencies` remains 9 fields.

Main conclusion:

`FORMAL_WORKFLOW_MODELS_REQUIRED_FIRST`

## Task 9C.4W Formal Document Alignment Workflow Models

Task 9C.4W adds only the formal data model layer required by the 9C.4V
contract. It does not add the replacement application service, API route,
worker orchestration, frontend cutover, OpenAPI contract, HTTP 410 disabled
response, or legacy dead-path removal.

Added model layer:

- `DocumentAlignmentWorkflowRun`;
- `DocumentAlignmentWorkflowItem`;
- `backend/services/document_alignment_workflow_contract.py` constants;
- root/item status and stage validation;
- idempotency scope unique constraint;
- per-run item key unique constraint;
- source/parse references;
- draft card and verification run UID references;
- safe error fields;
- `BACKGROUND_JOB_AS_TRANSPORT_ONLY` remains unchanged.

Post-9C.4W status:

- `POST /api/alignment/run` remains in `backend/app.py`.
- Legacy external/live execution remains disabled by 9C.4U.
- Frontend still calls the legacy route.
- No replacement route is registered.
- No workflow worker is registered.
- No application service is implemented.
- Direct `@app.route` count remains 131.
- Extracted route modules remain 12.
- Extracted routes remain 32.
- `RouteCoreDependencies` remains 9 fields.
- Migration remains `PILOT_CREATE_ALL_ONLY`; production still requires
  `FORMAL_MIGRATION_REQUIRED_BEFORE_PRODUCTION`.

Next recommended slice: freeze and implement the formal document alignment
application service. That task must explicitly define service DTOs, transaction
ownership, item-key generation, idempotency enforcement, and worker handoff
from the model fields before any route or frontend cutover.

## Task 9C.5K Formal Workflow Frontend Cutover Verification

Task 9C.5K verifies the Task 9C.5H frontend cutover from the trusted formal
backend baseline. It does not extract another route and does not change the
formal API, OpenAPI, workflow version, job type, idempotency scope, or
`RouteCoreDependencies`.

Verified teacher flow:

- upload and governed-source refresh provide the server-owned `source_uid`;
- `POST /api/document-alignment-runs` uses a browser-crypto idempotency key and
  sends only `source_uid`;
- polling uses `GET /api/document-alignment-runs/{run_uid}` and stops at a
  terminal business status;
- items use `GET /api/document-alignment-runs/{run_uid}/items` with server-side
  `page` and `page_size` parameters;
- reload restores the same Run from a strict `sessionStorage` allowlist without
  persisting tokens, credentials, evidence bodies, or model output;
- double-clicking creates one formal POST, and formal failure does not fall
  back to `POST /api/alignment/run`.

Legacy consumer status:

- the teacher start, polling, item-loading, and recovery flow makes zero
  requests to `POST /api/alignment/run`;
- the legacy backend POST remains registered and is not deleted in this task;
- `GET /api/alignment/runs` remains an active historical compatibility list and
  requires a separate remaining-consumer/deprecation decision.

The browser verification runner uses the server-authoritative
`DocumentAlignmentWorkflowRun.total_items` for item rendering and pagination
assertions. This preserves item-bootstrap semantics for multi-word candidates
and for early blocked runs instead of assuming one item per fixture phrase.

Pilot status remains `READY_WITH_CONDITIONS`: the verified local path is a
Pilot Release Candidate, not a production deployment. PostgreSQL migrations,
object storage, a supervised production queue/worker runtime, distributed
lease proof, live-provider governance, monitoring, HTTPS, backup/restore, and
formal privacy operations remain outside the current baseline.
