# Admin Demo Script

## Goal

Demonstrate operational visibility for users, courses, jobs, evaluation runs, logs, usage, and mock billing.

For a real course pilot, use this demo script together with `pilot_package/admin_manual.md`, `pilot_package/pilot_runbook.md`, and `pilot_package/post_pilot_report_template.md`. The admin should keep production-readiness blockers visible instead of presenting the local pilot as production-ready.

## Account

- Email: `admin@lexibridge.local`
- Password: `Admin1234`

## Steps

1. Log in as the admin and open `Admin Workspace`.
   Expected: user, course, job, evaluation, log, usage, and mock billing panels are visible.

2. Open User Management.
   Expected: demo users are visible:
   - `admin@lexibridge.local`
   - `teacher@lexibridge.local`
   - `student@lexibridge.local`
   - `student2@lexibridge.local`

3. Open Course Management.
   Expected: demo courses are visible:
   - `DS101 - Data Structures and Algorithms`
   - `SP101 - Signal Processing Basics`
   - `MATH101 - Engineering Mathematics`

4. Open Global Jobs.
   Expected: document ingestion, alignment, and evaluation demo jobs are visible with completed status.

5. Open Evaluation Runs.
   Expected: the latest run for `lexibridge_demo_gold_v1` is visible with metrics.

6. Open an EvaluationRun report.
   Expected: Markdown report includes metrics, release gate, failure cases, retrieval errors, alignment errors, and limitations.

7. Open System Logs.
   Expected: demo seed and demo flow entries are visible without secrets or tokens.

8. Open Usage / Mock Billing.
   Expected: Basic mock payment/subscription data exists for the demo student.

## Talking Points

- Admin visibility is operational and auditable.
- Demo data is self-authored and deterministic.
- The Local MVP still uses SQLite, mock email/payment, and optional local OCR/provider configuration.
