# Task 11I: Formal DeepSeek Transport

## Executive Conclusion

Task status: `FORMAL_DEEPSEEK_TRANSPORT_CLOSED`

The Formal alignment transport layer now has an evaluation-ready DeepSeek HTTP transport path with fake-executor offline coverage. The implementation adds a distinct `deepseek-alignment-v1` provider configuration, keeps `deepseek-alignment-v1-disabled` permanently fail-closed, and preserves the ordinary Formal Workflow default of `mock-rule-v1`.

The task was initially marked partial because the Codex sandbox could not bind `127.0.0.1`. The same commit was then verified from the macOS host terminal, where loopback binding, full pytest, `dev_check.py`, backend smoke, and release safety all passed. The sandbox loopback failure was environmental, not a project code defect.

No real DeepSeek request was made.

## Host Verification Closure

This section records host-executed verification. These commands were run by the user in a normal macOS Terminal, not inside the Codex sandbox.

| Check | Host result |
|---|---|
| Loopback bind | `LOOPBACK_BIND_OK`, Python bound `127.0.0.1:58357` |
| Tesseract | host-local Tesseract executable verified, exact path omitted, version `5.5.3` |
| 11I targeted tests | `47 passed in 3.63s` |
| Full pytest | `1254 passed, 6 warnings in 207.15s` |
| `dev_check.py` internal pytest | `1254 passed, 6 warnings in 210.34s` |
| `dev_check.py` migration | `scripts/migrate_db.py --apply`, temporary database, database migrated |
| `dev_check.py` backend smoke | `Backend smoke check passed: /api/test returned success.` |
| `dev_check.py` final | `All local pre-release checks passed.` |
| Release safety | `Release safety check passed.` |
| Worktree after host verification | clean |
| Real DeepSeek requests | `0` |

Before host verification, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, and `LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVAL_ENABLED` were unset. No Task 11J command, credentialed Provider evaluation runner, or real DeepSeek command was executed.

This closes 11I because the only previous blocker was sandbox-local loopback denial. In the host environment, the same implementation passed targeted tests, the complete suite, `dev_check.py`, backend smoke, and release safety while keeping real Provider requests at 0.

## Initial Gap

Before 11I, Formal alignment could not make a real DeepSeek request because:

- `deepseek-alignment-v1-disabled` was the only Formal DeepSeek-style provider and remained disabled.
- `HTTPTransport` in `backend/services/llm_transport.py` was a placeholder returning `provider_disabled`.
- `GuardedLLMAlignmentProvider` selected only injected, replay, or disabled transports.
- Ordinary Formal provider selection continued to allow only `mock-rule-v1`.

The legacy DeepSeek code in `backend/services/ai_provider.py`, `backend/services/ai_providers.py`, and `backend/app.py` does not implement `BaseLLMTransport.generate()` and is not used as the Formal alignment transport.

## Existing Transport Architecture

`BaseLLMTransport.generate(prompt, config, request_options=None)` returns `LLMTransportResult`.

Current local transports:

- `DisabledLLMTransport`: returns `status=error`, `error_code=provider_disabled`, `request_count=0`.
- `FakeLLMTransport`: returns fixture raw output for parser tests.
- `ReplayLLMTransport`: returns replay fixture raw output for controlled tests.
- `DeepSeekHTTPTransport`: new in 11I; parses the provider HTTP envelope and returns raw model content for the existing alignment output parser.

The transport layer does not parse LexiBridge alignment-domain JSON. That parsing remains in `backend/services/alignment_providers.py` through the existing alignment output parser path.

## Provider Configuration

| Provider | Model | Configured | Feature-enabled | Credential | Executable | Default |
|---|---|---:|---:|---:|---:|---:|
| `mock-rule-v1` | `mock-rule-v1` | yes | n/a | n/a | yes | yes |
| `deepseek-alignment-v1-disabled` | `deepseek-chat` | yes | ignored | ignored | no | no |
| `deepseek-alignment-v1` | `deepseek-chat` | yes | requires `LEXIBRIDGE_EXTERNAL_LLM_ENABLED` | requires `DEEPSEEK_API_KEY` | only when all gates pass | no |
| `external-llm-replay-v1` | `alignment-replay-fixture` | yes | n/a | n/a | replay-only | no |

`configured`, `feature_enabled`, `credential_present`, and `executable` are tracked as separate states. A provider is executable only when it is configured, not permanently disabled, externally feature-enabled, credential-present, and not replay mode.

## Default Closed Policy

Default Formal Workflow remains `mock-rule-v1`.

Ordinary Formal selection still rejects external providers. The item preparation boundary still rejects providers with `supports_external_calls=True`. Ordinary `/api/alignment/verify` requests using `deepseek-alignment-v1` are blocked by provider governance unless an explicit policy is created; no such production policy is added in this task.

## Request Envelope

`DeepSeekHTTPTransport` constructs an OpenAI-compatible chat-completions request:

- method: `POST`
- URL: configured DeepSeek base URL plus `/chat/completions`
- headers: `Content-Type: application/json`, `Accept: application/json`, and bearer authorization
- body: stable JSON with `model`, `messages`, and `stream=false`
- timeout: normalized provider timeout, reused for connect/read fields in the injectable request object
- retry count: `0`

The fake executor tests inspect method, URL, headers, timeout, body, model, message order, and absence of API key in the body.

## Response Parsing

The transport accepts the provider HTTP envelope and extracts:

- `choices[0].message.content`
- response model when present
- usage when present
- finish reason when present
- HTTP status
- latency
- request count
- retry count

Missing usage is allowed and returned as an empty usage dictionary.

## Error Classification

| Scenario | Error code |
|---|---|
| Provider disabled, feature disabled, replay misuse | `provider_disabled` |
| Credential missing | `credential_missing` |
| HTTP 400 or other 4xx except auth/rate | `invalid_request` |
| HTTP 401/403 | `authentication_failed` |
| HTTP 429 | `rate_limited` |
| HTTP 500/502/503 | `provider_server_error` |
| Connection timeout | `connection_timeout` |
| Read timeout | `read_timeout` |
| DNS/connection failure | `network_error` |
| Invalid JSON | `invalid_json` |
| Missing/invalid choices or message | `malformed_provider_response` |
| Missing, empty, or non-string content | `missing_response_content` |

Failures do not fall back to mock.

## Secret Safety

Credentials are resolved only at `generate()` time through a credential resolver shared with the configured environment variable name. The factory checks credential presence without reading or logging the value.

Tests use an obvious fake credential string only. The request object's `repr()` redacts authorization, error messages do not include credentials, and artifacts do not include authorization headers or secret values.

## Fake Executor Boundary

Transport tests use an injected fake executor. An autouse test guard replaces `urllib.request.urlopen` with a failure if code bypasses the fake executor. Importing the module and constructing `DeepSeekHTTPTransport` do not execute HTTP.

Real DeepSeek requests: `0`.

## Tests

| Command | Result |
|---|---|
| `backend/.venv-macos/bin/python -m pytest tests/test_formal_deepseek_provider_config.py tests/test_formal_deepseek_transport.py tests/test_formal_external_provider_selection.py tests/test_formal_real_provider_evaluation_policy.py tests/test_alignment_external_provider_guard.py -q` | `39 passed` |
| `backend/.venv-macos/bin/python -m pytest tests/test_alignment_verify_route_characterization.py::test_alignment_verify_provider_modes_and_write_set tests/test_formal_external_provider_selection.py tests/test_formal_deepseek_provider_config.py -q` | `11 passed` |
| `backend/.venv-macos/bin/python -m pytest tests/test_formal_document_alignment_provider_selection.py tests/test_document_alignment_production_contract_convergence.py tests/test_document_alignment_item_verification_security.py tests/test_alignment_verification_execution_service.py tests/test_alignment_verify_route_characterization.py tests/test_bilingual_knowledge_quality_metrics.py tests/test_bilingual_evidence_workflow.py tests/test_chinese_term_candidates.py -q` | `54 passed` |
| host-executed 11I targeted tests | `47 passed in 3.63s` |
| host-executed full pytest | `1254 passed, 6 warnings in 207.15s` |
| host-executed `dev_check.py` | passed; internal pytest `1254 passed, 6 warnings in 210.34s`; temporary DB migrated; backend smoke passed |
| `backend/.venv-macos/bin/python scripts/check_release_safety.py` | passed |

Warnings were the existing SQLAlchemy `Query.get()` legacy warning and PyMuPDF/Swig deprecation warnings.

## Environment Findings

Loopback is unavailable in the Codex sandbox execution environment. Minimal socket bind to `127.0.0.1:0` failed there with `PermissionError: [Errno 1] Operation not permitted`. The failing sandbox full-pytest files all depended on local HTTP server binding.

The macOS host terminal successfully bound `127.0.0.1:58357`, so the prior Codex sandbox loopback failure is attributed to the sandbox environment rather than project code.

Tesseract is not available on the Codex default `PATH`, but the host verification used a host-local Tesseract executable, exact path omitted, version 5.5.3. The executable path is intentionally omitted from this report and is not recorded in production code or configuration.

## Database Protection

Accident database: `backend/lexibridge.db`

| Check | Value |
|---|---|
| Frozen SHA-256 | `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa` |
| Before SHA-256 | `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa` |
| Final SHA-256 | `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa` |
| Size | `1015808` bytes |
| mtime epoch | `1785496597` |
| WAL | absent |
| SHM | absent |

All tests that initialized app state used temporary test databases. The accident database was not migrated, copied, or used.

## Privacy and Network

- Real DeepSeek requests: `0`
- External network requests: `0` for new 11I transport tests
- External document API requests: `0`
- Private data usage: `0`
- Private PDF usage: `0`
- Model downloads: `0`
- Secret exposure: `0`

## Remaining Limitations

- 11I did not perform any real Provider request.
- The 25-item credentialed semantic quality rerun has not been executed.
- Existing English retrieval weakness and Chinese candidate quality issues are not fixed in this task.
- Real course material and teacher blind review remain unvalidated.
- Production Provider execution remains default-closed.
- Codex sandbox loopback remains unavailable, but host verification closed the 11I regression gate.

## Final Decision

`FORMAL_DEEPSEEK_TRANSPORT_CLOSED`

The implementation is verified on the host and remains default-closed. The next task, after this is accepted, should be `Task 11J: Credentialed DeepSeek Synthetic Quality Evaluation`.
