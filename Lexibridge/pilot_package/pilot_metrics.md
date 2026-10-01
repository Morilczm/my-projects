# Pilot Metrics

## Usage Metrics

- `active_students`: unique students who log in or search during the pilot. Source: auth and usage records.
- `active_teachers`: teachers who upload, review, or resolve feedback. Source: job and QC logs.
- `documents_uploaded`: number of course and personal documents uploaded. Source: Document table.
- `jobs_completed`: completed background jobs. Source: BackgroundJob.
- `search_count`: terminology and knowledge search calls. Source: UsageRecord.
- `card_view_count`: card detail views if tracked. Source: usage or frontend event logs.
- `favorites_count`: favorites created. Source: favorite records.
- `mastered_count`: mastery marks. Source: learning records.
- `feedback_count`: submitted feedback. Source: PilotFeedback.
- `exports_count`: export actions. Source: UsageRecord.

## Quality Metrics

- `extraction_precision`: correct extracted professional terms divided by extracted terms.
- `extraction_recall`: expected gold terms found by extraction divided by gold terms.
- `english_evidence_accuracy`: correct English evidence divided by returned English evidence samples.
- `chinese_evidence_accuracy`: correct Chinese evidence divided by returned Chinese evidence samples.
- `evidence_accuracy`: both English and Chinese evidence correct divided by cases with returned evidence.
- `alignment_accuracy`: alignment status matches gold label.
- `false_positive_rate`: positive alignment when gold label is not positive.
- `auto_approval_error_rate`: auto-approved cards that should not be auto-approved divided by auto-approved cards.
- `no_evidence_forced_alignment_rate`: cases with missing evidence that still became positive alignment. Target: 0.
- `ocr_noise_term_rate`: OCR-noise terms divided by OCR-sourced term candidates.

## Teacher Metrics

- `qc_cards_reviewed`: cards reviewed by teachers.
- `average_qc_time_per_card`: total QC time divided by reviewed cards.
- `cards_approved`: approved cards.
- `cards_rejected`: rejected cards.
- `cards_marked_needs_more_evidence`: cards sent back for evidence.
- `feedback_resolved`: resolved feedback items.
- `teacher_satisfaction_score`: teacher survey score after pilot.

## Student Metrics

- `student_search_success_rate`: searches that lead to viewed relevant cards.
- `student_reported_usefulness`: student survey score.
- `student_trust_score`: student trust survey score.
- `student_feedback_rate`: feedback count divided by active students.
- `most_confusing_terms`: terms with repeated low trust or high feedback.
- `missing_terms_count`: missing-term feedback count.
