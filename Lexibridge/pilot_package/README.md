# LexiBridge AI Pilot Package

This package helps a pilot owner run a small course trial of LexiBridge AI. It is intended for local pilot validation, classroom demonstration, course reporting, and structured feedback collection.

## What This Package Is For

- Plan a small trial with 1-3 courses.
- Guide teachers through upload, alignment, quality control, feedback, and export.
- Guide students through terminology search, evidence reading, favorites, mastery marks, personal uploads, and feedback.
- Help administrators monitor jobs, logs, evaluation, AI provider state, knowledge base versions, retrieval diagnostics, and pilot reports.
- Prepare material for final presentation, report, poster, and trial review.

## What This Package Is Not For

- It is not a production deployment guide.
- It is not legal approval for copyrighted materials.
- It is not a guarantee that every terminology card is correct.
- It is not a replacement for teacher judgment.

## Required Reading

- `pilot_runbook.md`: pilot owner.
- `teacher_manual.md`: teachers and teaching assistants.
- `student_manual.md`: students.
- `admin_manual.md`: local project administrator.
- `data_authorization_guide.md`: course material use boundary.
- `privacy_and_risk_notice.md`: privacy, AI, OCR, and alignment risks.
- `pilot_metrics.md`: success indicators and data sources.
- `post_pilot_report_template.md`: after-trial review.

## Demo Data vs Real Course Data

Demo data is self-authored and controlled. It is useful for stable demonstrations and regression tests. Real course data comes from teachers and students, can contain ambiguity, OCR noise, missing Chinese references, and authorization constraints. A successful demo does not prove full real-course readiness.

## Local Pilot Boundary

The current system is local pilot-ready. It is not production-ready. SQLite, local uploads, mock payment, mock email, local worker, local lexical/vector demo retrieval, and optional local heuristic AI are not production services.

## Pilot Report And Feedback Loop

After a trial:

1. Export or review student and teacher feedback.
2. Convert important feedback into EvaluationItem or IterationBacklogItem.
3. Run evaluation and retrieval regression.
4. Generate a redacted pilot report.
5. Decide the next iteration based on evidence, not impressions.

Useful commands:

```bash
python scripts/check_pilot_package.py
python scripts/generate_pilot_package_summary.py --output docs/generated/pilot_package_summary.md
python scripts/export_final_project_snapshot.py --output docs/generated/final_project_snapshot.json
python scripts/generate_pilot_report.py --course-id 1 --output docs/generated/pilot_report_course_1.md
```
