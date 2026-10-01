# Controlled Real-Provider Evaluation Contract

Task: 10B

Conclusion target: `CONTROLLED_REAL_PROVIDER_EVALUATION_CONTRACT_ESTABLISHED`

This contract establishes an evaluation-only path for Chinese terminology
candidate proposals. It does not enable a real Provider in the Formal Workflow,
does not call an external Provider in Task 10B, and does not convert Provider
output into document evidence, approved terminology, or student-facing learning
assets.

## Purpose

The controlled path exists so a future Task 10C can evaluate a small set of
safe English Formal Items against one real Provider under explicit privacy,
credential, budget, request, parser, and artifact boundaries.

The implemented chain is:

```text
ControlledProviderEvaluationInput
-> privacy eligibility
-> provider/model allowlist
-> credential availability check
-> cost/request preflight
-> bounded prompt construction
-> evaluation-only HTTP transport
-> strict JSON parser
-> provider_generated_proposal
-> sanitized evaluation artifact
```

## Input Contract

`ControlledProviderEvaluationInput` is a frozen evaluation DTO. It includes:

- `evaluation_item_uid`
- `course_or_domain`
- `english_term`
- `normalized_english_term`
- `bounded_context`
- `context_source_type`
- `privacy_classification`
- `input_fingerprint`

The input fingerprint is a deterministic SHA-256 digest over the minimal safe
input fields. The bounded context has a fixed length limit and must not contain
local file paths, credential-shaped headers, HTML/script content, full PDFs,
full pages, or private course material.

## Privacy Classification

Only these classifications are recognized:

- `PUBLIC`
- `SYNTHETIC`
- `AUTHORIZED_EXTERNAL`
- `LOCAL_ONLY_PRIVATE`

Only `PUBLIC`, `SYNTHETIC`, and `AUTHORIZED_EXTERNAL` may pass toward the
transport. `LOCAL_ONLY_PRIVATE`, missing classifications, and invalid
classifications fail closed before credential or transport access.

The existing second-course private corpus remains `LOCAL_ONLY_PRIVATE` and is
not eligible for external Provider evaluation in this contract.

## Proposal Versus Evidence

Provider output is always `provider_generated_proposal`.

It is not:

- document evidence
- verified translation
- approved terminology
- canonical term
- student-ready card

Task 10B writes no Formal Workflow rows, no `DocumentAlignmentWorkflowItem`
rows, no Chinese candidate rows, and no `ConceptAlignmentCard` rows.

## Provider Proposal Schema

`ProviderGeneratedChineseCandidateProposal` is a strict DTO with:

- `chinese_term`
- `chinese_explanation`
- `alignment_rationale`
- `alternative_candidates`
- `risk_labels`
- `abstain`
- `abstain_reason`
- `provider_name`
- `model_name`
- `prompt_version`
- `output_schema_version`

`abstain=true` allows an empty `chinese_term` and requires an abstain reason.
`abstain=false` requires a non-empty Chinese term. Risk labels are allowlisted
and all string/list fields have fixed limits.

## Provider And Model Allowlist

The evaluation path does not accept arbitrary Provider URLs, model names,
headers, prompts, timeouts, or retry settings from item data. The current
allowlist includes the loopback fake-provider target used by tests. Live
execution without a configured safe target fails closed with
`REAL_PROVIDER_TARGET_NOT_CONFIGURED`.

## Credential Guard

Credential loading is limited to approved resolver objects such as an
environment-variable resolver. The resolver reports availability without
logging or storing the credential value. Credential values are kept in process
memory only and redacted from DTO reprs, safe errors, artifacts, logs, and test
outputs.

Task 10B does not configure or read a real Provider credential.

## HTTP Transport

`SafeEvaluationHTTPTransport` is evaluation-only. It enforces:

- POST-only JSON requests
- HTTPS-only external endpoints
- loopback only in explicit test mode
- host allowlist
- redirect rejection
- proxy environment ignored
- TLS verification for HTTPS
- fixed timeout
- response-size limit
- request-body size limit
- one bounded retry for 429 and selected 5xx/transient failures
- no retry for business 4xx, malformed JSON, schema invalid output, redirects,
  invalid content type, or oversized response

The transport is not wired into the Formal Workflow.

## Prompt

The evaluation prompt version is:

`provider-chinese-candidate-evaluation-v1`

It is separate from the Formal Workflow prompt `alignment-v1`. The prompt
requires JSON-only output, bounded-context use, abstention when uncertain, no
evidence fabrication, no learning-material generation, no approval, and
prompt-injection resistance.

## Output Parser

The parser rejects:

- non-JSON output
- arrays or scalar JSON
- unknown top-level fields
- missing required fields
- duplicate keys
- Markdown code fences
- trailing prose
- invalid enum/list/string shapes
- oversized strings
- HTML/script content
- credential-shaped headers
- local paths
- claims that Provider output is evidence

Parser failure yields `OUTPUT_INVALID`.

## Budget And Request Caps

The evaluation budget DTO includes:

- max items per batch
- max requests per item
- max total requests
- max input tokens
- max output tokens
- max estimated cost per item
- max estimated cost per batch
- max concurrency
- safety reserve ratio

Worst-case cost is calculated before any HTTP call using conservative token
estimates, output token cap, retry reserve, versioned pricing config, and the
safety reserve ratio. If the budget cannot be proven safe, the request is
blocked before transport.

## Artifact

The artifact writer stores only sanitized evaluation summaries:

- evaluation id
- git commit
- provider/model safe ids
- prompt/schema/pricing versions
- counts
- token totals
- estimated cost
- latency summary
- per-item safe result summaries

It does not store credentials, full prompts, full bounded context, raw Provider
responses, raw headers, private course content, local paths, stack traces, or
document evidence.

## CLI

`scripts/run_controlled_provider_evaluation.py` supports:

- `--manifest`
- `--json-output`
- `--dry-run`
- `--max-items`
- `--provider`
- `--model`
- `--execute-live`

The default path is dry-run. Task 10B only runs dry-run. Live execution requires
`--execute-live` plus all safety gates, and still fails closed if the real
Provider target is not configured.

## Formal Workflow Isolation

The Formal Workflow remains unchanged:

- default provider: `mock-rule-v1`
- model identity: `mock-rule-v1:v1`
- prompt version: `alignment-v1`
- public Formal API unchanged
- no Provider evaluation auto-creates WorkflowRuns or WorkflowItems
- no Provider proposal is written as Chinese evidence
- no Provider proposal creates or approves ConceptAlignmentCards

## Limitations

Task 10B does not prove real Provider quality, latency, cost, rate-limit
behavior, expert terminology correctness, teacher acceptance, or student
learning value. Task 10C is the next task and should run a 20-50 item controlled
real Provider evaluation only with safe data and legal credentials.
