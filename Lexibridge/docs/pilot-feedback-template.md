# Pilot Feedback Template

Use these forms during a small course pilot. The goal is to identify terminology coverage gaps, evidence quality issues, and workflow friction before expanding to real courses.

## Files

- `pilot_feedback/student_feedback_form.md`
- `pilot_feedback/teacher_feedback_form.md`
- `pilot_feedback/feedback_summary_template.md`

## Collection Method

1. Run `scripts/seed_demo_data.py`.
2. Run a supervised demo using the teacher and student scripts.
3. Ask students and teachers to complete the corresponding feedback form.
4. Summarize results with `feedback_summary_template.md`.
5. Convert repeated complaints into Quality Control or knowledge-source update tasks.

## Notes

- Do not treat demo metrics as production accuracy.
- Ask teachers specifically which Chinese evidence sources should be added.
- Ask students whether evidence-backed cards are more trustworthy than direct generic AI answers.
