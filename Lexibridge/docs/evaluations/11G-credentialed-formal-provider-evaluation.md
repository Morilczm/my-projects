# Task 11G: Credentialed Formal Provider Evaluation

## Executive Conclusion

Technical status: `CREDENTIALED_FORMAL_PROVIDER_EVALUATION_BLOCKED`

Quality status: `BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED`

The current Codex process cannot read a real Provider credential. `DEEPSEEK_API_KEY_SET=false` and `OPENAI_API_KEY_SET=false`. No Provider preflight or formal 25-item run was attempted, and no Provider request was made.

## Provider Runtime

| Item | Result |
|---|---|
| Credential present | false |
| Provider ID | `deepseek-alignment-v1-disabled` |
| Model ID | `deepseek-chat` |
| Adapter path | `backend/services/alignment_providers.py:GuardedLLMAlignmentProvider` |
| Credential env | `DEEPSEEK_API_KEY` |
| supports_external_calls | true |
| Preflight | not run |
| Requests | 0 |
| Retries | 0 |
| Tokens | not reported |
| Latency | not measured |
| First blocker | `FORMAL_REAL_PROVIDER_EVAL_CREDENTIAL_MISSING` |

Static adapter review found that `deepseek-alignment-v1-disabled` is not merely a historical name in the current Formal provider layer. It is registered as an external provider ID, but `GuardedLLMAlignmentProvider` still selects `DisabledLLMTransport` for non-replay external execution. Because credentials were missing, runtime did not reach that later transport layer.

## Frozen Inputs

The 11E corpus and gold hashes were rechecked through the existing evaluation runner:

- Corpus SHA-256: `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- Gold SHA-256: `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`
- Concept count: 25
- Source count: 4 synthetic documents

No corpus, gold, threshold, prompt, retrieval, candidate, or production provider behavior was modified.

## Controlled Gate Result

The 11F evaluation gate was run with all non-secret requirements supplied:

- explicit evaluation gate enabled
- evaluation id matched
- runner id matched
- corpus hash matched
- gold hash matched
- isolated temporary database
- provider registered
- model matched allowlist
- request budget valid
- external provider flag supplied

The decision remained deny because the credential was absent:

`FORMAL_REAL_PROVIDER_EVAL_CREDENTIAL_MISSING`

## Retrieval-only Rerun

The 11E retrieval-only runner was rerun against a temporary SQLite database outside the repository.

- Provider requests: 0
- Status: `BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED`
- Sanitized JSON SHA-256: `7cc60747f43750ff43b5b60d478e645ee4cdb8219ee86118547eeece536b78bf`
- Review packet SHA-256: `e6f44709236bd7dec054d6f27f7bea444f670ba2a94c9be1bdcd304f4e9858df`
- JSON size: 143916 bytes
- Review packet size: 42700 bytes

## Quality Metrics

These are blocked retrieval-only proxy metrics, not real Provider semantic results.

| Metric | Result | Threshold | Pass |
|---|---:|---:|---|
| candidate_recall | 0.00 | 0.88 | no |
| chinese_term_top1_accuracy | 0.00 | 0.80 | no |
| chinese_term_top3_accuracy | 0.00 | 0.92 | no |
| english_hit_at_3 | 0.24 | 0.90 | no |
| chinese_hit_at_3 | 1.00 | 0.85 | yes |
| bilingual_evidence_completeness | 0.24 | 0.80 | no |
| term_pair_accuracy | 0.00 | 0.80 | no |
| unsupported_claim_rate | 1.00 | 0.10 max | no |
| critical_confusion_count | 0 | 0 | yes |
| source_reference_completeness | 1.00 | 1.00 | yes |
| chunk_reference_completeness | 1.00 | 1.00 | yes |
| approve_proxy_rate | 0.00 | 0.60 | no |
| edit_proxy_rate | 0.00 | informational | n/a |
| reject_proxy_rate | 1.00 | 0.15 max | no |

## Valid-evidence Subset

The retrieval-only rerun found 6/25 items with both EN and ZH evidence hit@3. Provider performance on this valid-evidence subset was not evaluated because credentials were absent.

## End-to-end Quality

All 25 concepts remained in the denominator. All 25 remained blocked at semantic evaluation. No item was removed or replaced with mock output.

Primary attribution count:

| Attribution | Count |
|---|---:|
| `PROVIDER_FAILURE` | 25 |

Secondary observations remain unchanged:

- English retrieval is weak on the synthetic corpus: `hit@3 = 0.24`.
- Chinese retrieval is strong: `hit@3 = 1.00`.
- Chinese candidate extraction over-extracts full definition fragments rather than exact accepted terms.

## Production Safety

The ordinary Formal Workflow still defaults to `mock-rule-v1`. Policy tests verified default deny, bad hash deny, non-temp database deny, unknown provider/model deny, budget deny, and mock regression. No browser, pytest, or dev check path made real Provider requests.

## Tests

| Command | Result |
|---|---|
| `backend/.venv-macos/bin/python -m pytest tests/test_formal_real_provider_evaluation_policy.py -q` | `12 passed` |
| `backend/.venv-macos/bin/python -m pytest tests/test_bilingual_knowledge_quality_metrics.py -q` | `6 passed` |
| related Provider/Formal/retrieval/11B/11D regression pytest command | `106 passed` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python -m pytest -q` | `1237 passed, 6 warnings` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python scripts/dev_check.py` | passed |
| `backend/.venv-macos/bin/python scripts/check_release_safety.py` | passed |

## Database Protection

- Accident database: `backend/lexibridge.db`
- Frozen SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- Final SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- Size: `1015808`
- mtime epoch: `1785496597`
- WAL/SHM: absent
- Evaluation database: temporary SQLite outside the repository
- Accident database used for evaluation: false

## Privacy and Network

- Provider requests: 0
- Synthetic egress: 0
- Private egress: 0
- Private PDF usage: 0
- External document API requests: 0
- Other external network: 0
- Model downloads: 0
- Secret exposure: 0

## Remaining Limitations

- No real Provider semantic quality was measured.
- The current process lacks Provider credentials.
- `deepseek-alignment-v1-disabled` may still require an evaluation-only executable transport after credentials are available.
- The corpus is synthetic.
- There is no real teacher blind review.
- Real course materials remain unvalidated.
- Production embedding/vector remains incomplete.
- Complex PDF and formula structure recognition remain out of scope.

## Final Decision

Technical status: `CREDENTIALED_FORMAL_PROVIDER_EVALUATION_BLOCKED`

Quality status: `BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED`
