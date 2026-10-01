# Admin Manual

## Main Admin Tasks

- Manage users and roles.
- Review courses and memberships.
- Monitor background jobs.
- Inspect EvaluationRun records.
- Inspect AI Provider status.
- Review KnowledgeBaseVersion records.
- Review RetrievalExperimentRun records.
- Generate Pilot Reports.
- Run backup and restore scripts.
- Run health reports.
- Run production readiness checks.

## Operational Commands

```bash
python scripts/migrate_db.py
python scripts/collect_health_report.py
python scripts/check_database_readiness.py
python scripts/storage_integrity_check.py
python scripts/check_production_readiness.py
python scripts/generate_pilot_report.py --course-id 1 --output docs/generated/pilot_report_course_1.md
```

## Production Readiness

Run `python scripts/check_production_readiness.py` before any external pilot review. A `NOT READY` result is acceptable for the current local pilot stage, but blockers must be recorded and communicated.

## Data Visibility

Admins can see more records than teachers and students, but admin actions must still respect privacy. Do not publish full student email addresses, personal document content, raw OCR text, tokens, secrets, or full AI prompts/responses.

## Jobs And Logs

Review failed jobs before the pilot session. A failed OCR, formula OCR, alignment, evaluation, vector index, or export task should be recorded in the pilot log with cause and next action.

## Evaluation And Retrieval

Admins can run EvaluationRun, retrieval regression, vector index health checks, and retrieval experiments. Do not switch default retrieval mode unless experiments show improvement without privacy or source-governance violations.

## Production Boundary

The system is local pilot-ready. It is not production-ready until PostgreSQL, object storage, production queue, real mail service, real payment or closed payment entry, HTTPS, backups, monitoring, and privacy/legal review are complete.
