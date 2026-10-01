# Task 11F: Controlled Real Provider Formal Alignment

## Executive Conclusion

Task status: `CONTROLLED_REAL_PROVIDER_FORMAL_ALIGNMENT_BLOCKED`

11E quality rerun status: `BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED`

The controlled evaluation gate was added and verified in tests, but the current host has no `DEEPSEEK_API_KEY` or `OPENAI_API_KEY`. No real Provider preflight or 25-item run was executed. The frozen 11E retrieval-only pipeline was rerun against a temporary database and reproduced the same blocked quality result with Provider requests equal to 0.

## Original 11E Blocker

Formal Workflow previously resolved only the server-owned deterministic provider:

- provider: `mock-rule-v1`
- model: `mock-rule-v1:v1`
- real external calls: disabled

Two layers prevented real Provider execution:

1. `backend/services/formal_document_alignment_provider_selection.py` only accepted `mock-rule-v1`.
2. `backend/services/document_alignment_item_preparation.py` rejected providers with `supports_external_calls=True`.

## Controlled Evaluation Gate

The new policy is evaluation-only and is not wired into ordinary production defaults. It requires all of the following:

- `LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVAL_ENABLED=1`
- `LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVALUATION_ID=11E_BILINGUAL_QUALITY`
- runner id `11F_CONTROLLED_FORMAL_ALIGNMENT_RUNNER`
- corpus hash `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- gold hash `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`
- isolated SQLite database outside the repository
- registered external provider `deepseek-alignment-v1-disabled`
- allowlisted model `deepseek-chat`
- request budget in range 1 to 35
- configured credential via `DEEPSEEK_API_KEY`

Default Formal Workflow remains fail-closed on `mock-rule-v1`.

## Provider Run

No real Provider run was executed.

| Phase | Result |
|---|---|
| Default environment gate | `FORMAL_REAL_PROVIDER_EVAL_GATE_DISABLED` |
| All non-secret gates supplied | `FORMAL_REAL_PROVIDER_EVAL_CREDENTIAL_MISSING` |
| Preflight | not run |
| 25-item run | not run |
| Provider requests | 0 |
| Retries | 0 |
| Token usage | not reported |
| Synthetic data egress | 0 |

## 11E Retrieval-only Rerun

The frozen 11E runner was rerun to `/tmp` without Provider calls.

- JSON output SHA-256: `64e71009ac5e43143205ff1a3e15c78fa25312ead60cb09f51e7a7ed551e2f5d`
- Review packet SHA-256: `df31ef0a89779d95638bad1d141fceabdedeb8520839092974cad4dca4efd62e`
- Temporary DB: system temporary directory outside the repository

## Quality Metrics

These are blocked retrieval-only proxy metrics, not real Provider semantic quality.

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
| reject_proxy_rate | 1.00 | 0.15 max | no |

## Valid-evidence Subset

Six of 25 concepts had both English and Chinese retrieval hit@3 in the retrieval-only rerun. Provider quality on that subset was not evaluated because credentials were unavailable and no real Provider request was made.

## Failure Attribution

Primary attribution for all 25 frozen results remains `PROVIDER_FAILURE` because the real semantic evaluation could not execute.

Important secondary observations from retrieval-only diagnostics:

- English retrieval hit@3 was low at 0.24.
- Chinese retrieval hit@3 was 1.00.
- Chinese candidates often over-extracted definition fragments instead of exact accepted terms.

## Safety

- Accident database was not used.
- No external document parsing API was called.
- No private course data was used.
- No Provider credential was printed or persisted.
- No model download occurred.
- No real Provider request occurred.

## Tests

| Command | Result |
|---|---|
| `backend/.venv-macos/bin/python -m pytest tests/test_formal_real_provider_evaluation_policy.py -q` | `12 passed` |
| `backend/.venv-macos/bin/python -m pytest tests/test_bilingual_knowledge_quality_metrics.py -q` | `6 passed` |
| related Provider/Formal/retrieval/11B/11D regression pytest command | `106 passed` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python -m pytest -q` | `1237 passed, 6 warnings` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python scripts/dev_check.py` | passed |
| `backend/.venv-macos/bin/python scripts/check_release_safety.py` | passed |

Warnings were the existing SQLAlchemy `Query.get()` legacy warning and PyMuPDF/Swig deprecation warnings.

## Remaining Limitations

- No real Provider semantic quality was measured in this task.
- The corpus remains synthetic.
- There is no real teacher blind review.
- Real course materials remain unvalidated.
- Current results depend on future provider/model configuration.
- Production embedding/vector retrieval remains incomplete.
- Complex PDF and formula structure recognition are outside this task.

## Final Decision

Technical status: `CONTROLLED_REAL_PROVIDER_FORMAL_ALIGNMENT_BLOCKED`

Quality status: `BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED`

Next task should provide a real credentialed evaluation environment or explicitly decide that the existing Formal external provider adapter must be completed before semantic quality measurement can proceed.
