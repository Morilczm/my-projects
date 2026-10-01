# Task 11J-R5 Credentialed DeepSeek Synthetic Quality Evaluation

## Status

- Technical: `CREDENTIALED_DEEPSEEK_SYNTHETIC_EVALUATION_COMPLETED`
- Quality: `BILINGUAL_KNOWLEDGE_QUALITY_INSUFFICIENT`
- Credential present: `true`
- Provider/model: `deepseek-alignment-v1` / `deepseek-chat`
- Transport: `DeepSeekHTTPTransport`

All 25 frozen benchmark rows received a terminal evaluation status. All three
system-derived provider-ready items reached the real Formal Provider path.
Quality is insufficient, but the evaluation contract is complete.

## Attempt history

1. Credential missing; requests `0`.
2. Formal provider admission blocked; requests `0`.
3. Fixed momentum preflight blocked by English evidence; requests `0`.
4. Explanation persistence verification blocked; requests `1`.
5. Production candidate output incorrectly controlled benchmark enumeration;
   requests `0`.
6. Unified 25-row enumeration completed. Three matched items were executed.

Attempt 6 used `4` requests and `1` runner retry. The first physics-23 response
was successfully persisted as `needs_review`, but an outdated runner outcome
label misclassified it. The allowed preflight retry produced the frozen result,
which was reused in the batch. Physics-24 succeeded. Physics-25 returned
`provider_non_json_output`; the safe failed verification was persisted and the
systemic protocol failure was recorded. No mock/replay substitution occurred.

## Benchmark coverage and readiness

| Measure | Result |
| --- | ---: |
| Benchmark rows | 25/25 |
| Production candidate matched | 3 |
| Missing | 22 |
| Ambiguous | 0 |
| Provider ready | 3 |
| Provider called | 3 |
| Upstream not ready | 22 |

The deterministic preflight selector chose `physics-23`, the first
`provider_ready=true` row in frozen order. Benchmark English terms were used
only for exact binding verification and scoring; Provider inputs came from
production candidate objects and production retrieval.

## Provider execution and persistence

- Requests/retries: `4/1`
- Provider successes/failures: `2/1`
- Provider token usage: not returned
- Persisted latency: not returned
- Preflight new-session reload: passed
- Preflight reused in batch: yes

Persistence completeness across three Provider-called concepts:

| Field | Complete |
| --- | ---: |
| Term pair | 3/3 |
| Explanation | 3/3 |
| Confidence | 2/3 |
| Evidence refs | 3/3 |
| Provenance | 3/3 |
| Fully successful verification | 2/2 |

The failed physics-25 row contains the bounded parser-failure explanation and
evidence provenance, but no confidence.

## Quality metrics

Fresh upstream reproduction:

| Metric | Result |
| --- | ---: |
| Candidate recall | 0.0000 |
| Chinese top-1 | 0.0000 |
| Chinese top-3 | 0.0000 |
| English hit@3 | 0.2400 |
| Chinese hit@3 | 1.0000 |
| Bilingual evidence completeness | 0.2400 |
| Gold-valid evidence subset | 6/25 |

Valid-evidence subset:

| Metric | Result |
| --- | ---: |
| Provider called | 3/6 |
| Term-pair accuracy | 0.0000 |
| Explanation support | 0.3333 |
| Unsupported claim rate | 0.0000 |
| Critical confusion count | 0 |
| Confidence present | 0.3333 |

All 25:

| Metric | Result |
| --- | ---: |
| Term-pair accuracy | 0.0000 |
| Unsupported claim rate | 0.0000 |
| Critical confusion count | 0 |
| Source reference completeness | 0.1200 |
| Chunk reference completeness | 0.1200 |
| Approve proxy | 0.0000 |
| Edit proxy | 0.0000 |
| Reject proxy | 1.0000 |

Primary attribution:

- `CANDIDATE_EXTRACTION_DEFECT`: 22
- `CHINESE_CANDIDATE_DEFECT`: 2
- `PROVIDER_FAILURE`: 1

The two successful Provider outputs received definition-like Chinese candidates
before transport rather than accepted top-level terms, so their earliest cause
is Chinese candidate quality rather than term alignment.

## Frozen artifacts and safety

- Sanitized raw output SHA-256:
  `41352ec911781e5d577a3f1755e976425294345dc989946f290999183272a527`
- Raw requests, raw responses, headers, credentials, and full source text were
  not stored.
- Temporary SQLite database was outside the repository.
- Accident database was not queried, migrated, or copied.
- Private data egress: `0`
- Secret exposure: `0`
- External document API requests: `0`

## Verification

- Targeted evaluation/Formal regression: `101 passed`.
- Full pytest: `1245 passed, 20 failed, 12 errors, 6 warnings`.
- `dev_check`: failed because its pytest phase produced the same result.
- Every failure/error was the established Codex sandbox loopback limitation:
  `PermissionError: [Errno 1] Operation not permitted` while binding
  `127.0.0.1`. Host verification remains pending; no production workaround was
  introduced.
- Release safety: passed.
- Real DeepSeek requests during ordinary tests and `dev_check`: `0`.
- Accident database final SHA-256, size, and mtime matched the baseline; WAL and
  SHM remained absent.
