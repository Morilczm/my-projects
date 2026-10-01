# Production Readiness Checklist

## Security

- [ ] `DEBUG=false`.
- [ ] Strong `SECRET_KEY`.
- [ ] CORS allowlist has no wildcard.
- [ ] Mock AI/payment/email disabled or clearly blocked.
- [ ] No default test passwords in production.
- [ ] Logs redact secrets and student content.

## Data

- [ ] PostgreSQL or managed production database.
- [ ] Object storage or durable file storage.
- [ ] Migration plan and backup before migration.
- [ ] Restore drill completed.

## Operations

- [ ] Gunicorn or equivalent WSGI server.
- [ ] HTTPS reverse proxy.
- [ ] Worker process manager.
- [ ] Health report scheduled.
- [ ] Alerts for failed jobs/provider failures.

## Product Quality

- [ ] Smoke evaluation passed.
- [ ] Teacher-reviewed gold set expanded.
- [ ] No-evidence forced alignment rate remains `0`.
- [ ] Pilot feedback reviewed.

## Release

- [ ] `pytest` passed.
- [ ] OpenAPI contract tests passed.
- [ ] Release package checker passed.
- [ ] `scripts/check_production_readiness.py` reviewed.
