# LexiBridge AI Alignment State Machine Design

This document describes the Local MVP v0.8 terminology alignment state machine. The goal is to prevent AI output, mock fallback, weak evidence, OCR noise, or missing bilingual evidence from creating trusted terminology cards.

## Core Principle

LexiBridge AI does not treat translation as the final product. A `TerminologyCard` is only trusted when the English source context, English knowledge-base evidence, Chinese knowledge-base evidence, AI alignment output, and rule-based quality gates agree.

AI output is one input. It cannot directly decide the final card status.

## AlignmentRun

Every `/api/alignment/run` call and every upload-triggered alignment creates an `AlignmentRun`.

Tracked fields:

- `document_id`
- `course_id`
- `triggered_by`
- `ai_provider`
- `ai_model`
- `prompt_version`
- `retrieval_version`
- `term_count`
- `card_created_count`
- `auto_approved_count`
- `qc_count`
- `needs_evidence_count`
- `conflict_count`
- `failed_count`
- `status`
- `error_message`
- `started_at`
- `finished_at`

Status values:

- `queued`
- `running`
- `completed`
- `failed`
- `canceled`

The Local MVP runs alignments synchronously, so most runs move directly from `running` to `completed` or `failed`.

## alignment_status

The semantic alignment status describes the evidence relationship:

- `exact_match`: English and Chinese evidence point to the same concept.
- `accepted_translation`: Translation is acceptable, but evidence may be weaker or less course-specific.
- `partial_match`: Concepts overlap but are not fully equivalent.
- `broader_than_source`: Chinese concept is broader than the English source concept.
- `narrower_than_source`: Chinese concept is narrower than the English source concept.
- `ambiguous_candidate`: Candidate Chinese term is ambiguous.
- `multi_translation_conflict`: Multiple Chinese candidates conflict.
- `no_en_evidence`: English evidence is missing or below threshold.
- `no_zh_evidence`: Chinese evidence is missing or below threshold.
- `domain_mismatch`: Evidence is from the wrong course or discipline.
- `ocr_low_confidence`: Source OCR confidence is below threshold.
- `formula_evidence_missing`: Formula evidence is required but Formula OCR is unavailable or failed.
- `invalid_term_candidate`: Candidate is invalid, such as a full sentence, OCR noise, or formula fragment.
- `unverified_translation`: Only an unverified AI/local candidate exists.

Priority order is conservative. Missing evidence, domain mismatch, OCR/formula risk, and invalid candidates override optimistic AI output.

## TerminologyCard.status

Business status values:

- `draft`
- `needs_more_evidence`
- `pending_quality_control`
- `conflict_detected`
- `auto_approved`
- `approved`
- `rejected`
- `archived`

Allowed transitions:

- `draft -> needs_more_evidence`
- `draft -> pending_quality_control`
- `draft -> conflict_detected`
- `draft -> auto_approved`
- `needs_more_evidence -> pending_quality_control`
- `needs_more_evidence -> approved`
- `pending_quality_control -> approved`
- `pending_quality_control -> rejected`
- `pending_quality_control -> needs_more_evidence`
- `conflict_detected -> approved`
- `conflict_detected -> rejected`
- `auto_approved -> pending_quality_control`
- `approved -> pending_quality_control`
- `approved -> archived`
- `rejected -> archived`

Forbidden transitions:

- `rejected -> auto_approved`
- `needs_more_evidence -> auto_approved`
- `pending_quality_control -> auto_approved by system`
- mock/local AI output -> `auto_approved`
- no English evidence -> `auto_approved`
- no Chinese evidence -> `auto_approved`
- domain mismatch -> `auto_approved`
- OCR low confidence -> `auto_approved`
- formula evidence missing -> `auto_approved`
- invalid term candidate -> `auto_approved`

The helper `validate_card_status_transition(old_status, new_status, actor_role, system_action=False)` enforces this transition table.

## Confidence Score

Final card confidence is calculated by `calculate_confidence_score(...)`:

```text
confidence_score =
0.25 * term_quality_score
+ 0.25 * english_evidence_score
+ 0.25 * chinese_evidence_score
+ 0.15 * ai_alignment_score
+ 0.05 * course_scope_score
+ 0.05 * source_quality_score
- risk_penalty
```

The first six inputs are 0-1 values and are multiplied to a 0-100 score. Risk penalties are direct point deductions.

Risk penalties:

| Risk flag | Penalty |
| --- | ---: |
| `no_zh_evidence` | 40 |
| `no_en_evidence` | 40 |
| `domain_mismatch` | 50 |
| `ocr_low_confidence` | 25 |
| `formula_evidence_missing` | 25 |
| `mock_or_local_ai` | 30 |
| `ambiguous_candidate` | 20 |
| `multi_translation_conflict` | 30 |
| `invalid_term_candidate` | 60 |
| `weak_evidence` | 15 |
| `unverified_translation` | 35 |

Scores are clamped to 0-100. If English or Chinese evidence is missing, final confidence is capped at 45.

## Auto Approval Gate

`auto_approved` is only allowed when all conditions are true:

- `confidence_score >= 85`
- `term_quality_score >= 0.80`
- `english_evidence_score >= 0.80`
- `chinese_evidence_score >= 0.80`
- `alignment_status in ["exact_match", "accepted_translation"]`
- AI provider is live, not `mock`, `none`, or `local_heuristic`
- OCR confidence is at least 60 or OCR was not required
- no `formula_evidence_missing`
- no `no_en_evidence`
- no `no_zh_evidence`
- no `domain_mismatch`
- no `ocr_low_confidence`
- no `invalid_term_candidate`
- no `multi_translation_conflict`

If the gate fails, the card stores the gate rejection reasons in `score_breakdown_json.auto_approval_gate.reasons` and routes to `needs_more_evidence`, `pending_quality_control`, or `conflict_detected`.

## Evidence Snapshot Strategy

`TerminologyCard` stores:

- `english_evidence_snapshot`
- `chinese_evidence_snapshot`
- `english_evidence_score`
- `chinese_evidence_score`
- `score_breakdown_json`
- `quality_flags_json`
- `retrieval_version`
- `source_alignment_run_id`

The snapshots preserve the evidence text, source title, citation, page number, knowledge-base type, evidence score, strength, score breakdown, and risk flags. This makes cards traceable even if the original `KnowledgeChunk` later changes.

## Mock And Local AI Boundary

When no live DeepSeek provider is configured, the backend may still produce a local demo candidate so the workflow remains demonstrable. Those cards are flagged with `mock_or_local_ai`, receive a confidence penalty, and cannot auto-approve.

Provider failures are logged in `SystemLog`. Cards generated after provider failure include a risk note and enter Quality Control or `needs_more_evidence`.

## Current Test Result

The PR-3 alignment test suite was run with:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_alignment_status.py tests/test_card_generation.py tests/test_confidence_scoring.py
```

Result:

```text
13 passed
```

Full regression:

```bash
backend/.venv-macos/bin/python -m pytest
```

Result:

```text
28 passed
```
