# ADR: Legacy Prompt Mutation Policy

Status: ACCEPTED_FOR_SMALL_PILOT

Date: 2026-07-17

Policy name: LEGACY_PROMPT_MUTABLE_REVISION_V1

Implementation status after Task 9C.4R: application service established in `backend/services/legacy_provider_prompt_mutation.py`; POST route adapter extracted into `backend/routes/legacy_provider_admin_configuration.py`.

## Context

`POST /api/admin/ai/prompts` is a legacy admin-only mutation endpoint. It shares the `/api/admin/ai/prompts` path and `admin_ai_prompts` Flask endpoint with the already extracted GET configuration view. Since Task 9C.4R, both GET and POST are handled by `backend/routes/legacy_provider_admin_configuration.py`; the POST adapter delegates to the prompt mutation application service.

Task 9C.4O characterized the current behavior:

- the mutation identifies a prompt by `prompt_key` plus `prompt_version`;
- a missing key/version creates a `PromptTemplate`;
- an existing key/version updates the existing row in place;
- the client supplies `prompt_version`;
- no immutable version history table exists;
- no database uniqueness constraint protects `prompt_key` plus `prompt_version`;
- no optimistic locking or `If-Match` behavior exists;
- active/default fields are direct row assignments, not globally managed operations;
- the callback commits directly and has no explicit rollback;
- OpenAPI marks `task_type` and `template_text` as required even though runtime only requires `prompt_key` and `prompt_version`.

Task 9C.4O.1 fixed provider-admin test state isolation before this policy was accepted, so the prompt mutation characterization can be run in different provider-admin test orders without sentinel state leaking between modules.

Task 9C.4Q implements this ADR in a prompt mutation application service. Task 9C.4R moves the thin POST adapter into the existing configuration route module. The service preserves the legacy mutable-revision policy, owns one commit plus explicit rollback, and returns a typed result. Neither task adds immutable history, uniqueness, locking, OpenAPI changes, or frontend changes.

## Decision

For the current local MVP and small controlled pilot, `POST /api/admin/ai/prompts` is formally treated as a legacy mutable revision upsert:

- Identity: `(prompt_key, prompt_version)`.
- Write behavior: upsert.
- Missing row: create one `PromptTemplate`.
- Existing row: update that row in place.
- Version policy: `LEGACY_MUTABLE_REVISION`; `prompt_version` is a client-provided opaque non-empty string, not semver, not server-generated, and not immutable.
- Repeated identical request: semantic success and no second row in normal single-writer execution.
- Repeated different request: overwrite the existing mutable revision.
- Concurrency policy: `SINGLE_WRITER_LAST_COMMIT_WINS`.
- Active/default scope: direct field assignment on the target row is preserved, but active/default exclusivity and workflow operations are out of scope.
- Validation baseline: `RUNTIME_CONTRACT_IS_COMPATIBILITY_SOURCE`.
- Transaction target for the next service: `APPLICATION_SERVICE_OWNS_TRANSACTION`.

This policy is a compatibility policy for a bounded local/small-pilot deployment. It is not a production versioning design.

## Current Compatibility Policy

### Identity

The compatibility identity is `(prompt_key, prompt_version)`.

`prompt_key` names the legacy prompt slot, such as `term_alignment`. `prompt_version` names the mutable revision label supplied by the client. Both values are stringified, stripped, and required by runtime. The comparison is case-sensitive because the database lookup uses the stored string values directly. Whitespace surrounding incoming values is not part of identity after runtime stripping. Missing values and empty strings fail runtime validation after stringification/stripping because they produce an empty value. JSON `null` is a legacy quirk: runtime stringifies it to `"None"` and accepts it. Service extraction must preserve that behavior unless a later versioned validation change is approved.

`provider`, `model`, `task_type`, `language`, `is_active`, and `is_default` are not part of the current identity.

### Version Semantics

The chosen version policy is `LEGACY_MUTABLE_REVISION`.

`prompt_version` is opaque. The server does not require semver, does not generate a replacement version, does not preserve previous content when the same key/version is updated, and does not promise historical lookup by older contents. Different `prompt_version` values for the same `prompt_key` can coexist as separate rows.

### Create, Update, And Upsert

When no row exists for `(prompt_key, prompt_version)`, the endpoint creates a new `PromptTemplate`.

When a row exists for `(prompt_key, prompt_version)`, the endpoint updates that row in place. A repeated identical request remains a successful operation and should not create another row in normal single-writer execution. A repeated different request overwrites mutable fields such as `task_type`, `language`, `template_text`, `json_schema`, `is_active`, `is_default`, `notes`, and `updated_at` according to current runtime behavior.

The response does not distinguish created from updated. Both return the legacy success envelope and HTTP 200.

### Duplicate Rows

The current lookup uses the first row returned by `PromptTemplate.query.filter_by(prompt_key=..., prompt_version=...).first()`. The compatibility service must preserve that behavior if duplicate logical rows already exist. This is a compatibility risk, not a correctness guarantee.

Sequential repeated requests in one process should not create duplicate rows for the same key/version. True concurrent creation can still produce duplicate logical rows because there is no unique database constraint. Production hardening must add schema-backed uniqueness before claiming duplicate prevention.

### Concurrency

The current pilot policy is `SINGLE_WRITER_LAST_COMMIT_WINS`.

Admin-only access is an authorization gate, not a technical lock. The system assumes operational single-writer use for the prompt editor during the local/small pilot. If two writes target the same key/version, no conflict is detected and the last successful commit determines the final stored content. The endpoint does not provide ETag, `If-Match`, row version tokens, optimistic locking, conflict status, or lost-update prevention.

### Active And Default

The endpoint accepts `is_active` and `is_default` fields and assigns them directly on the target prompt row. It does not implement active/default workflow operations.

The following are out of scope for this endpoint policy:

- global one-active enforcement;
- global one-default enforcement;
- archive operations;
- activate/deactivate operations as separate commands;
- automatic deactivation of older versions;
- automatic unsetting of other defaults.

Future service extraction must preserve direct field assignment if supplied, but must not add active/default exclusivity or workflow behavior.

### Validation

Runtime contract is the compatibility source.

Runtime currently requires only:

- `prompt_key`;
- `prompt_version`.

`task_type`, `language`, `template_text`, `json_schema`, `is_active`, `is_default`, and `notes` follow current fallback/coercion behavior. Unknown fields are ignored. Non-object JSON currently reaches an error path captured by characterization tests; service extraction may safely map the same failure class without expanding accepted input.

OpenAPI currently marks `task_type` and `template_text` as required. That is documentation drift. Service extraction must not enforce the stricter OpenAPI fields, because that would break the legacy runtime contract. OpenAPI correction should be a separate narrow contract-alignment task.

### Template And Secret Boundary

Prompt template text is legitimate business data. It may contain natural-language instructions, placeholders, output-format instructions, or schema guidance. It must not be erased by broad keyword-based secret redaction.

Credential-like metadata is not prompt business data. Unknown fields such as API keys, bearer tokens, cookies, authorization headers, passwords, private keys, credential-bearing URLs, raw provider connection configuration, or environment values must not be persisted to `PromptTemplate`, returned in the API response, written to `AuditRecord`, or logged as request bodies.

The endpoint currently does not write a prompt mutation `AuditRecord`. Future service extraction must preserve no-AuditRecord behavior unless a later explicit audit task changes the contract.

## Rejected Alternatives

### Immutable Versions Now

Rejected for the current pilot. The database has no uniqueness constraint, no history table, no migration framework, and no conflict response contract. Treating same key/version updates as immutable conflicts would break current runtime behavior and existing characterization.

### Enforce OpenAPI Required Fields First

Rejected for this task. OpenAPI currently requires `task_type` and `template_text`, but runtime does not. Enforcing OpenAPI now would be a behavior change to the legacy endpoint. Runtime remains the compatibility baseline until a separate API contract alignment task is approved.

### Add Unique Constraints Or Optimistic Locking Now

Rejected for this task. The project still uses additive migration helpers rather than a formal migration framework. Unique constraints, immutable version history, row-version tokens, ETag/If-Match, and HTTP 409 semantics require a production hardening phase with migration and client compatibility planning.

### Move Active/Default Policy Into This Endpoint

Rejected for service extraction. The current endpoint only assigns target-row flags. It does not implement active/default uniqueness or workflow state transitions. Adding those semantics while extracting a service would mix compatibility preservation with product behavior design.

## Consequences

The application service created in Task 9C.4Q is small and precise: it implements runtime-compatible validation, seed integration, key/version lookup, mutable revision upsert, one commit, explicit rollback, and a typed result.

The policy also keeps visible limitations:

- no immutable version history;
- no duplicate prevention under real concurrent creation;
- no lost-update protection;
- no active/default exclusivity;
- no prompt mutation audit event;
- OpenAPI currently documents stricter required fields than runtime.

Those limitations are acceptable only for local or small controlled pilot usage.

## Pilot Limitations

This policy assumes:

- SQLite remains the database;
- one administrator edits prompts operationally at a time;
- external LLM execution remains disabled by readiness conditions;
- prompt mutation is an admin-only compatibility endpoint;
- formal migrations and production monitoring are not yet enabled.

This policy must not be presented as production-grade version control.

## Future Production Migration

A production prompt mutation policy requires separate work:

- formal migration framework;
- `unique(prompt_key, prompt_version)` or a replacement identity table;
- immutable version rows or explicit revision records;
- a create-new-version operation;
- historical version query semantics;
- optimistic locking through a row version, `updated_at` token, or ETag/If-Match;
- HTTP 409 conflict response for stale writes or duplicate versions;
- one-active and one-default constraints if those concepts become product requirements;
- explicit prompt mutation audit events with safe summaries;
- multi-admin concurrency tests.

These changes must not be bundled into the compatibility service extraction.

## Service Extraction Requirements

The prompt mutation application service implements this flow:

1. seed registry defaults through the existing seed service;
2. validate runtime-compatible required fields;
3. look up by `(prompt_key, prompt_version)`;
4. create a row if missing;
5. update the first matching row in place if present;
6. flush as needed for serialization;
7. commit exactly once on success;
8. rollback explicitly on any failure;
9. return a typed result that lets the route preserve the legacy envelope and status.

The seed service must not commit or roll back. The route adapter does not own business commit/rollback after service extraction.

The service must not:

- introduce immutable version behavior;
- enforce OpenAPI-only required fields;
- add active/default exclusivity;
- create audit records;
- access provider credentials;
- call provider adapter or transport;
- touch `/api/alignment/run`.

## Route Extraction Requirements

The POST route remains in the shared configuration route registration until the thin adapter is extracted in a later task.

When the route is later moved:

- URL remains `/api/admin/ai/prompts`;
- method remains `POST`;
- endpoint remains `admin_ai_prompts`;
- the shared GET/POST rule shape must remain compatible;
- success remains the legacy envelope without `request_id`;
- admin-only permission remains;
- OpenAPI and frontend behavior remain unchanged unless a separate task changes them.

## OpenAPI Mismatch Decision

Decision: `RUNTIME_CONTRACT_IS_COMPATIBILITY_SOURCE`.

OpenAPI currently marks `task_type` and `template_text` as required. Runtime only requires `prompt_key` and `prompt_version`. The next service must preserve runtime behavior. A later OpenAPI correction may either relax the schema to match runtime or introduce a versioned API change, but that is outside this policy task.

## Security Boundary

The prompt template body is allowed business content. Redaction must not remove legitimate template instructions.

Credential-like unknown metadata is outside the prompt model and must remain ignored. The system must not persist or return API keys, bearer tokens, cookies, private keys, authorization headers, full environment values, provider transport credentials, full request bodies, or raw tracebacks through this endpoint.

The endpoint must remain no-network. It must not call provider adapter, provider transport, live probe, replay execution, usage writing, verification run creation, or card mutation logic.

## Testing Requirements

Characterization tests must continue to prove:

- GET/POST share `/api/admin/ai/prompts` and endpoint `admin_ai_prompts`;
- runtime requires `prompt_key` and `prompt_version`;
- missing key/version creates one row;
- existing key/version updates that row in place;
- same key/version does not create a second row in normal repeated execution;
- different content overwrites the mutable revision;
- `prompt_version` is client supplied and opaque;
- there is no immutable history generation;
- there is no optimistic lock, ETag, or conflict response;
- active/default exclusivity is not managed;
- no `AuditRecord` is written;
- success has no `request_id`;
- no network/provider transport is used;
- provider-admin state isolation prevents sentinel leakage across test order.
