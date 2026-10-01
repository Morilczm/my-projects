# LexiBridge AI Evaluation Harness Specification

This document defines the Local MVP evaluation harness for terminology extraction, evidence retrieval, bilingual alignment, and auto-approval safety.

## Purpose

The evaluation harness answers:

- whether extracted terms are real academic terms;
- whether expected gold terms are missed;
- whether English and Chinese evidence support the expected term pair;
- whether `alignment_status` matches a manual gold label;
- whether the system forces alignment when evidence is missing;
- whether `auto_approved` is incorrectly assigned;
- whether OCR noise becomes terminology.

The harness is repeatable and stores every run as `EvaluationRun`.

## Data Model

### EvaluationSet

Fields:

- `id`
- `name`
- `course_id`
- `discipline`
- `description`
- `created_by`
- `created_at`
- `updated_at`
- `is_locked`

An evaluation set can be global or course-specific. Teachers can manage sets they created or sets bound to their courses. Admin can manage all sets.

### EvaluationItem

Fields:

- `id`
- `evaluation_set_id`
- `item_id`
- `split`
- `discipline`
- `course_id`
- `english_term`
- `expected_chinese_term`
- `english_context`
- `expected_english_evidence`
- `expected_chinese_evidence`
- `expected_alignment_status`
- `negative_english_evidence`
- `negative_chinese_evidence`
- `difficulty`
- `tags_json`
- `annotator`
- `reviewed_by`
- `disagreement_note`
- `version`
- `created_at`

`split` must be treated as `train`, `dev`, or `test`. Do not tune thresholds on `test` and then report that result as objective performance.

### EvaluationRun

Fields:

- `id`
- `evaluation_set_id`
- `model_version`
- `prompt_version`
- `retrieval_version`
- `alignment_version`
- `commit_hash`
- `split`
- `input_count`
- `skipped_count`
- `extraction_precision`
- `extraction_recall`
- `evidence_accuracy`
- `english_evidence_accuracy`
- `chinese_evidence_accuracy`
- `alignment_accuracy`
- `false_positive_rate`
- `auto_approval_error_rate`
- `ocr_noise_term_rate`
- `no_evidence_forced_alignment_rate`
- `created_by`
- `created_at`
- `finished_at`
- `status`
- `report_json`
- `report_markdown`
- `error_message`

## JSONL Format

`docs/evaluation_sample.jsonl` stores one JSON object per line:

```json
{
  "item_id": "SP-FT-001",
  "split": "test",
  "discipline": "signal_processing",
  "course_id": null,
  "english_term": "Fourier Transform",
  "expected_chinese_term": "傅里叶变换",
  "english_context": "Fourier Transform converts a time-domain signal into a frequency-domain representation.",
  "expected_english_evidence": "Fourier Transform represents a signal by frequency components.",
  "expected_chinese_evidence": "傅里叶变换用于将信号表示为频率分量。",
  "expected_alignment_status": "exact_match",
  "negative_english_evidence": "A hash table maps keys to buckets using a hash function.",
  "negative_chinese_evidence": "哈希表通过哈希函数将关键字映射到桶或存储位置。",
  "difficulty": "easy",
  "tags": ["core_term"],
  "annotator": "manual_seed",
  "reviewed_by": "manual_seed",
  "version": "v1"
}
```

## Evaluation Flow

For each `EvaluationItem`:

1. Run local term extraction on `english_context`.
2. Check whether the expected `english_term` was extracted.
3. Run evidence retrieval for English and Chinese evidence through the existing alignment workflow.
4. Run the existing alignment/card status logic.
5. Compare actual outputs with gold fields.
6. Record:
   - `expected_term_found`
   - `english_evidence_correct`
   - `chinese_evidence_correct`
   - `alignment_status_correct`
   - `wrongly_auto_approved`
   - `no_evidence_forced_alignment`
   - `ocr_noise_detected`
   - `failure_reason`

## Metrics

### extraction_precision

Correctly extracted expected terminology divided by all system-extracted candidate terms.

### extraction_recall

Gold terms found by the extractor divided by gold item count.

### english_evidence_accuracy

Correct English evidence divided by items where English evidence was returned.

### chinese_evidence_accuracy

Correct Chinese evidence divided by items where Chinese evidence was returned.

### evidence_accuracy

Items where both English and Chinese evidence are correct divided by items where any evidence was returned.

### alignment_accuracy

Items where actual `alignment_status` equals the expected gold status divided by total item count.

### false_positive_rate

Positive system alignment when the gold expected status is not positive, divided by total item count.

Positive system outputs are `exact_match`, `accepted_translation`, `auto_approved`, and `approved`.

### auto_approval_error_rate

`auto_approved` items whose gold status is not `exact_match` or `accepted_translation`, divided by total `auto_approved` count.

If there are no auto-approved items, the rate is 0.

### no_evidence_forced_alignment_rate

Items with missing English or Chinese evidence where the system still emits `exact_match`, `accepted_translation`, or `auto_approved`, divided by total item count.

This metric must stay 0.

### ocr_noise_term_rate

OCR noise terms divided by OCR-origin candidate terms. If the evaluation set has no OCR-origin terms, this value is `null` / not covered.

## Release Gate

Smoke set minimum:

- `extraction_precision >= 0.75`
- `extraction_recall >= 0.60`
- `evidence_accuracy >= 0.70`
- `alignment_accuracy >= 0.70`
- `false_positive_rate <= 0.10`
- `auto_approval_error_rate <= 0.05`
- `no_evidence_forced_alignment_rate == 0`

v1.0 target:

- `extraction_precision >= 0.80`
- `evidence_accuracy >= 0.75`
- `alignment_accuracy >= 0.75`
- `false_positive_rate <= 0.05`
- `ocr_noise_term_rate <= 0.10`
- `no_evidence_forced_alignment_rate == 0`

## API

- `POST /api/evaluation/sets`
- `GET /api/evaluation/sets`
- `POST /api/evaluation/items/import`
- `GET /api/evaluation/items`
- `GET /api/evaluation/sets/<id>/items`
- `POST /api/evaluation/run`
- `GET /api/evaluation/runs`
- `GET /api/evaluation/runs/<id>`

Students cannot access evaluation APIs. Teachers can manage their own evaluation sets or course-bound sets. Admin can manage all.

## Current Limitations

- The sample set has 60 smoke items, not enough for production accuracy claims.
- Current retrieval version is `local_lexical_v1`; no production reranker or vector database is used.
- Formula-related gold items can expose `formula_evidence_missing`, but real formula OCR quality is not evaluated unless a Formula OCR provider is configured.
