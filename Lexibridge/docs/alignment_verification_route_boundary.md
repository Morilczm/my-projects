# Alignment Verification Route Boundary

Task 9C.4D characterizes `POST /api/alignment/verify` without moving the route or changing production behavior.
Task 9C.4D.1 adds an application service boundary for the execution orchestration. Task 9C.4E moves the resulting thin HTTP adapter into `backend/routes/alignment_verification.py` while keeping the same URL, method, Flask endpoint, request/response contract, provider modes, state machine, usage behavior, attach gate, audit events, and transaction behavior.

## Route Contract

| Item | Current contract |
|---|---|
| URL | `POST /api/alignment/verify` |
| Flask endpoint | `verify_alignment_api` |
| Handler location | `backend/routes/alignment_verification.py` registered from `backend/app.py` |
| Handler size | 31-line nested HTTP adapter; original 9C.4D handler was 281 lines including decorator and blanks |
| Authentication | `require_current_user({"student", "teacher", "admin"})` |
| Request body parsing | `request.get_json(silent=True) or {}`; malformed JSON currently follows the empty-body validation path |
| Provider default | `mock-rule-v1` from `provider` or `provider_name` |
| Card lookup | Optional `card_uid`; when present, the execution service loads `ConceptAlignmentCard` and builds verification input from the card |
| Success status | `200` with success envelope and request ID |
| Validation/provider errors | `400` with `audit_error_code` |
| Missing card | `404` with `audit_error_code=concept_card_not_found` |
| Generic failure | `500` with `audit_error_code=alignment_verification_failed` |
| OpenAPI operation | `docs/openapi.yaml` defines `post /api/alignment/verify` with `200`, `400`, `403`, and `404` responses |

The response top-level data currently includes `run_uid`, provider metadata, parser/schema metadata, provider response status, verification status, confidence, recommendation, risk labels, cost/retry summaries, `can_auto_approve`, `is_production_result`, serialized `run`, and optional `card` / `attach_blocked_reason`.

## Direct Dependencies

The original Task 9C.4D route handler directly coordinated these dependencies. After Task 9C.4D.1 and 9C.4E, `backend/routes/alignment_verification.py` only builds the execution DTOs and calls `execute_alignment_verification(...)`; the execution service owns this dependency chain:

| Dependency | Use |
|---|---|
| `alignment_provider_service.get_alignment_provider` | Early provider existence validation |
| `concept_card_service.get_concept_card` | Optional card lookup |
| `alignment_verification_service.build_alignment_verification_input_from_card` | Card-to-verification input adapter |
| `alignment_verification_service.validate_alignment_verification_input` | Direct payload validation |
| `provider_governance_service.evaluate_provider_request` | Policy, role, course, usage, and cost gate |
| `provider_governance_service.provider_blocked_output` | Stable failed output for blocked provider requests |
| `alignment_verification_service.create_alignment_verification_run` | Failed policy-block run persistence |
| `alignment_verification_service.verify_alignment` | Provider execution wrapper and run persistence |
| `provider_governance_service.can_attach_verification_to_card` | Attach policy gate |
| `alignment_verification_service.apply_verification_result_to_card` | Optional card mutation |
| `alignment_verification_service.serialize_alignment_verification_run` | Response serialization |
| `record_alignment_verification_audit` | Verification audit events |
| `record_alignment_provider_usage` | Provider usage write and usage audit |

Direct model access from the route includes `ConceptAlignmentCard`, `AlignmentProviderPolicy`, `AlignmentProviderUsageRecord`, and `AlignmentVerificationRun`.

## Execution Chain

```text
HTTP request
-> route auth / request ID
-> request JSON parsing
-> initial alignment_verification_requested audit commit
-> provider existence check
-> provider_options normalization
-> card lookup or direct payload validation
-> provider governance gate
-> blocked branch:
   -> provider_blocked_output
   -> AlignmentVerificationRun failed run
   -> alignment_verification_blocked_by_policy audit
   -> ProviderUsageRecord + provider_usage_recorded audit
   -> commit
-> allowed branch:
   -> alignment_verification_service.verify_alignment
   -> provider implementation (mock/fake/replay/disabled external)
   -> AlignmentVerificationRun
   -> ProviderUsageRecord + provider_usage_recorded audit
   -> optional attach gate
   -> optional ConceptAlignmentCard update
   -> commit
-> completion audit
-> optional attached audit
-> success response
```

Exception branches roll back the active transaction, then write a failure audit and return an error envelope. The route has controlled branches for concept-card lookup failure, unknown provider, provider-selection failure, verification validation failure, and generic failure.

## Provider Modes

| Provider | Provider type | Network | Policy behavior | Run status behavior | Usage behavior | Attach behavior |
|---|---|---:|---|---|---|---|
| `mock-rule-v1` | `mock` | No | Built-in local active policy permits student/teacher/admin | `mock_only` or `failed` | Writes usage for executed route requests | Built-in policy allows attach; draft card moves to `needs_review` |
| `fake-llm-v1` | `fake_llm` | No | Built-in local active policy permits student/teacher/admin | `needs_review` for valid fixture; `failed` for parser fixtures | Writes usage | Built-in policy allows attach; never approves |
| `external-llm-replay-v1` | `replay_llm` | No | Requires explicit policy | `needs_review` for valid replay; `failed` for replay/parser failures | Writes usage when route creates a run | Attach depends on `allow_attach_to_card` |
| `deepseek-alignment-v1-disabled` | `external_llm` | No under current gate | Missing or disabled policy blocks before transport in default local state | Failed policy-block run | Writes usage for policy-block run | No attach |

Real external provider execution remains disabled. Characterization tests patch socket connect for local modes and policy-block paths.

## Verification Run State Machine

The route and services currently use persisted `AlignmentVerificationRun.verification_status` values rather than a running job lifecycle.

| Current state | Event | Next state | Writes | Usage | Attach allowed |
|---|---|---|---|---|---|
| none | mock provider succeeds | `mock_only` | run, usage, audits | yes | yes if policy allows and card UID exists |
| none | fake provider valid fixture | `needs_review` | run, usage, audits | yes | yes if policy allows and card UID exists |
| none | replay valid fixture | `needs_review` | run, usage, audits | yes | yes if explicit policy allows |
| none | fake/replay parser failure | `failed` | run, usage, audits | yes | no meaningful attach |
| none | provider governance blocked | `failed` | run, usage, blocked audit, failed audit | yes | no |
| none | validation error before run | no run | requested audit, failed audit | no | no |
| none | unknown provider before run | no run | requested audit, failed audit | no | no |
| draft card | successful attach | card becomes `needs_review` | card risk labels, audits | already written | yes |
| non-draft card | successful attach | status unchanged | card risk labels, audits | already written | yes |

`can_auto_approve` is always forced false, provider output does not approve cards, and `ConceptAlignmentCard.confidence_score` is not written.

## Write-Set Matrix

| Path | VerificationRun | UsageRecord | Card/Draft | AuditRecord | Preflight | Other |
|---|---:|---:|---:|---:|---:|---:|
| Unauthorized | 0 | 0 | 0 | 0 | 0 | none |
| Malformed JSON / empty body | 0 | 0 | 0 | requested + failed | 0 | none |
| Card not found | 0 | 0 | 0 | requested + failed | 0 | none |
| Provider not found | 0 | 0 | 0 | requested + failed | 0 | none |
| Policy missing / disabled / blocked | 1 failed | 1 | 0 | requested + blocked + usage + failed | 0 | none |
| Mock success | 1 | 1 | 0 unless attach requested | requested + usage + completed | 0 | none |
| Fake valid | 1 | 1 | 0 unless attach requested | requested + usage + completed | 0 | none |
| Fake invalid output | 1 failed | 1 | 0 | requested + usage + failed | 0 | none |
| Replay success | 1 | 1 | 0 unless attach requested | requested + usage + completed | 0 | none |
| Replay fixture failure | 1 failed | 1 | 0 | requested + usage + failed | 0 | none |
| Attach blocked | 1 | 1 | 0 | requested + usage + blocked + completed | 0 | none |
| Attach success | 1 | 1 | 1 card update | requested + usage + completed + attached | 0 | none |
| Usage write exception | rollback removes flushed run and usage | 0 | 0 | requested + failed | 0 | none |

Preflight records are not written by `/api/alignment/verify`.

## Secret And Network Boundary

The input normalization path redacts sensitive keys such as `api_key`, `authorization`, `cookie`, `token`, `secret`, and `password`. The route audit adapter stores only bounded summaries: card UID, terms, course/chapter, provider, run metadata, provider response status, risk labels, and cost summary. It does not store full evidence, headers, credentials, or provider raw output.

No current local provider mode should call external network. Replay mode uses local replay transport. The disabled external provider remains disabled by governance/configuration in the local pilot baseline.

## Complexity Metrics

| Metric | Count |
|---|---:|
| Handler lines | 281 |
| Direct route model classes | 4 |
| Direct domain service modules/helpers | 8+ |
| Database tables written on success-like paths | 3 or 4 with attach |
| Explicit `db.session.commit()` calls in handler body | 2 mutually exclusive main commits |
| Route helper audit commits outside main transaction | requested, completion, optional attached/failure |
| Rollback branches | 5 |
| Return paths | 7 |
| Provider modes | 4 |
| Verification audit event types | 5 |
| Provider usage audit event types | 1 |
| Attach branches | 3: no attach, blocked attach, successful attach |

## Extraction Conclusion

`SERVICE_BOUNDARY_REQUIRED_FIRST`

The route is not just thin HTTP glue. It still owns significant orchestration:

- initial audit before validation;
- provider existence check;
- card versus payload input branch;
- policy-block run creation;
- provider execution branch;
- provider usage write;
- attach policy branch and card mutation;
- multi-step audit sequencing;
- transaction commit/rollback behavior.

Before moving this route into a route module, create or extend a domain service that owns the verification execution transaction. The route should eventually pass actor context, request payload, and request ID into that service, then translate a service result into the existing response envelope. The service contract must preserve the state machine, write-set matrix, usage behavior, audit events, no-network gate, secret redaction, and attach behavior documented here.

## Task 9C.4D.1 Service Boundary

Task 9C.4D.1 introduces `backend/services/alignment_verification_execution.py` as the application-layer execution boundary. The public entry point is:

```text
execute_alignment_verification(
    request: AlignmentVerificationExecutionRequest,
    actor: AlignmentVerificationActor,
    context: AlignmentVerificationExecutionContext,
    dependencies: AlignmentVerificationExecutionDependencies,
) -> AlignmentVerificationExecutionResult
```

The DTOs are frozen dataclasses. The service accepts normalized request fields, safe actor metadata, safe audit context, and explicit verification-domain dependencies. It does not import Flask, `backend.app`, route modules, `RouteCoreDependencies`, credential resolvers, provider clients, or external transport.

The service now owns the application orchestration that was previously in `verify_alignment_api`:

- provider existence validation;
- card-vs-direct-payload input branch;
- provider governance gate;
- policy-block run creation;
- mock/fake/replay/disabled provider execution dispatch through existing services;
- provider usage write;
- optional attach gate and card update;
- verification audit sequencing;
- business transaction commit/rollback;
- safe response data construction.

`verify_alignment_api` now lives in `backend/routes/alignment_verification.py` and remains the Flask endpoint. Its remaining responsibilities are HTTP-only: authentication, request JSON parsing with the existing `silent=True` behavior, provider/card/attach field normalization, DTO construction, service invocation, and mapping `AlignmentVerificationExecutionResult` back to the existing API envelope.

Task 9C.4E status:

`SERVICE_BOUNDARY_ESTABLISHED`

`THIN_ROUTE_EXTRACTED`

Current adapter snapshot:

- Original Task 9C.4D handler: about 281 lines in `backend/app.py`.
- Task 9C.4D.1 thin adapter: about 35 lines in `backend/app.py`.
- Task 9C.4E route module: `backend/routes/alignment_verification.py`, 139 lines total.
- Nested `verify_alignment_api` adapter body: 31 lines.
- Register signature: `register_alignment_verification_routes(app, *, core, execution_dependencies, execute_fn=execute_alignment_verification)`.
- Execution service public API unchanged: `execute_alignment_verification(...)`, `AlignmentVerificationExecutionRequest`, `AlignmentVerificationActor`, `AlignmentVerificationExecutionContext`, `AlignmentVerificationExecutionDependencies`, and `AlignmentVerificationExecutionResult`.

This changes the extraction conclusion to:

`THIN_ROUTE_EXTRACTION_COMPLETE`

Future tasks must not move or rewrite the verification state machine, provider execution behavior, usage write semantics, attach gate, audit events, or transaction behavior as part of route cleanup.
