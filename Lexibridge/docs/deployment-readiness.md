# Deployment Readiness

LexiBridge AI is currently local pilot-ready, not production-ready.

## Current Local Architecture

```text
Single-page frontend
-> Flask app
-> SQLite
-> local uploads
-> local SQLite-backed background jobs
```

## Recommended Staging Architecture

```text
Nginx or local reverse proxy
-> Gunicorn Flask app
-> SQLite or PostgreSQL
-> isolated uploads directory
-> worker process
-> structured logs
-> scheduled backup
```

## Recommended Production Architecture

```text
Nginx / HTTPS
-> Gunicorn Flask App
-> PostgreSQL
-> Object Storage
-> Redis Queue
-> Worker Process
-> Structured Logs
-> Backup Job
-> Monitoring / Alerting
```

## Flask Runtime

Do not use Flask's debug server for production. Use Gunicorn or another WSGI server behind HTTPS termination.

## Database

SQLite is acceptable for local demos only. Production should use PostgreSQL with reviewed migration scripts, backups, and restore drills.

## File Storage

Local uploads are acceptable for demos. Production should use object storage or durable mounted storage with lifecycle controls.

## Worker

The local worker is SQLite-friendly. Production should move to Redis/Celery/RQ or equivalent durable queue.

## Before Production

Run:

```bash
python scripts/check_production_readiness.py
```

`NOT READY` is expected until production infrastructure and real providers are configured.
