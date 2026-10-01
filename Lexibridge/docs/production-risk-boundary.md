# Production Risk Boundary

LexiBridge AI is local pilot-ready, not production-ready.

## Current Non-Production Capabilities

- Mock payment.
- Mock email.
- SQLite local database.
- Local single-process worker.
- Local uploads.
- No real object storage.
- No production queue.
- No real school, publisher, or ByrDocs connector.
- No production vector database.
- No complete SSO.
- No formal privacy policy.
- No large teacher-reviewed gold set.

## v1.0 Core Engine Capabilities

- Document parsing, OCR, and FormulaBlock architecture.
- Evidence retrieval hard filters and scoring.
- Alignment status machine.
- Confidence scoring and risk gates.
- Evaluation Harness.
- OpenAPI contract.
- Role permissions.
- Personal knowledge-base isolation.
- Local async task queue.
- Demo data and pilot scripts.

## Required Before Production

- PostgreSQL.
- Durable object storage.
- HTTPS.
- Real email service or disabled email flows.
- Real payment or disabled payment UI.
- Production queue such as Celery/RQ/Redis.
- Monitoring and alerting.
- Backup and restore drills.
- Privacy policy and data-retention policy.
- Teacher/professional reviewed gold set.
