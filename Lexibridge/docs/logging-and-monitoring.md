# Logging And Monitoring

LexiBridge AI uses conservative structured logging helpers for deployment preparation.

## Log Types

- `app_log`
- `security_log`
- `job_log`
- `ai_provider_log`
- `ocr_log`
- `retrieval_log`
- `evaluation_log`
- `billing_usage_log`

## Structured Fields

Logs should include:

- `timestamp`
- `level`
- `module`
- `event`
- `message`
- `user_id`
- `course_id`
- `document_id`
- `job_id`
- `alignment_run_id`
- `evaluation_run_id`
- `request_id`
- `duration_ms`
- `status`
- `error_code`

## Redaction Rules

Never log:

- plaintext passwords
- complete tokens
- complete API keys
- student document full text
- OCR full text
- AI prompt full text
- AI response full text
- payment sensitive information

Allowed:

- resource IDs
- provider name
- counts
- page count
- chunk count
- error code
- short redacted summary

Helpers:

- `backend/services/logging_config.py`
- `backend/services/audit_log.py`

## Health Report

Run:

```bash
python scripts/collect_health_report.py
```

The report includes user/course/document counts, job status, OCR/provider failures, terminology card status counts, latest EvaluationRun metrics, upload directory size, and database size.
