# LexiBridge AI Final Delivery

This directory is the final course handoff package for LexiBridge AI. It organizes the runnable local demo, final acceptance evidence, course report material, presentation material, poster copy, and release-package checks in one place.

Current version boundary: LexiBridge AI is local pilot-ready and course demonstration-ready. It is not production-ready.

## File Purposes

- `final_delivery_checklist.md`: final checkbox list for code, features, docs, and safety boundary.
- `final_acceptance_report.md`: acceptance report covering backend, frontend, workflows, evaluation, security, demo, and pilot package.
- `final_test_report.md`: final executed-command test report.
- `final_demo_script.md`: final teacher, student, admin, and learning-outcome demo script.
- `final_screenshot_checklist.md`: screenshot list for report, PPT, and poster.
- `final_course_report_materials.md`: material for the course report, with computational thinking and design thinking.
- `final_presentation_outline.md`: 10-slide final presentation outline.
- `final_poster_copy.md`: poster text copy.
- `final_project_summary.md`: Chinese final project summary.
- `final_known_limitations.md`: explicit current limitations and non-production boundary.
- `final_next_steps.md`: staged roadmap after submission.
- `final_release_manifest.json`: generated manifest for final release artifacts and production-readiness status.
- `final_artifact_index.md`: index of code, docs, pilot package, demo data, and release artifacts.

## Which Files To Use

- Course report: `final_course_report_materials.md`, `final_project_summary.md`, `final_acceptance_report.md`.
- PPT: `final_presentation_outline.md`, `final_demo_script.md`, `final_screenshot_checklist.md`.
- Poster: `final_poster_copy.md`.
- Project demo: `final_demo_script.md`, `final_screenshot_checklist.md`.
- Code handoff acceptance: `final_delivery_checklist.md`, `final_acceptance_report.md`, `final_test_report.md`, `final_release_manifest.json`.

## Regenerate Final Delivery

```bash
python scripts/check_final_delivery.py
python scripts/generate_final_release_manifest.py --output final_delivery/final_release_manifest.json
python scripts/build_final_release.py
```

The final release check must confirm that the zip package does not include `.env`, API keys, database files, uploads, virtual environments, cache files, or local private paths.
