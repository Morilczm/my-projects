# Teacher Demo Script

## Goal

Demonstrate the official course knowledge-base workflow for `SP101 - Signal Processing Basics`.

For a real course pilot, use this demo script together with `pilot_package/teacher_manual.md`, `pilot_package/data_authorization_guide.md`, and `pilot_package/pre_pilot_checklist.md`. The demo files are synthetic and do not replace teacher authorization review for real course materials.

## Account

- Email: `teacher@lexibridge.local`
- Password: `Teacher1234`

## Steps

1. Log in as the teacher and open `Teacher Workspace`.
   Expected: the top status bar shows role `teacher`, AI/OCR provider status, and task count.

2. Select `SP101 - Signal Processing Basics`.
   Expected: the course panel shows document count, terminology count, review count, and evidence-missing count.

3. Open `Courseware Upload`.
   Expected: upload controls distinguish English course materials, Chinese reference materials, and supplementary KB materials.

4. Upload or confirm demo files:
   - `demo_data/signal_processing/english_course_notes.md`
   - `demo_data/signal_processing/chinese_reference.md`
   - `demo_data/signal_processing/mixed_pdf_sample.pdf`

   Expected: each upload creates or references a document and a background job.

5. Open `Documents & Jobs`.
   Expected: documents show parsing status, OCR status, formula OCR status, chunk count, formula block count, and linked job status.

6. Trigger or inspect an `AlignmentRun`.
   Expected: the run shows `term_count`, `card_created_count`, `auto_approved_count`, `qc_count`, `needs_evidence_count`, and `failed_count`.

7. Open `Quality Control`.
   Use filters:
   - `pending_quality_control`
   - `needs_more_evidence`
   - `formula_evidence_missing`
   - `no_zh_evidence`

8. Open the `Fourier Transform` card.
   Expected: the card shows English context, English evidence snapshot, Chinese evidence snapshot, score breakdown, quality flags, AI provider, retrieval version, and formula-risk note if applicable.

9. Approve one low-risk card after review.
   Expected: status changes to `approved`, with `approved_by` and `approved_at` recorded.

10. Reject one incorrect or intentionally incomplete card.
    Expected: status changes to `rejected`; it must not return to `auto_approved` automatically.

11. Open student feedback.
    Expected: the demo feedback created by `run_demo_flow.py` is visible and can be marked resolved.

## Talking Points

- Teachers do not review every card. They handle exceptions: weak evidence, missing evidence, domain mismatch, OCR risk, formula OCR missing, or student feedback.
- Local/mock AI output cannot auto-approve cards.
- Formula OCR is separated from ordinary OCR; without a formula provider, formula evidence is marked rather than fabricated.
