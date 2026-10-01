# Environment Configuration

LexiBridge AI now separates configuration into `development`, `staging`, and `production`.

## Development

Purpose: local development, course demo, feature validation, and Codex changes.

Allowed:

- SQLite.
- Local uploads.
- Mock email.
- Mock payment.
- Local heuristic/mock AI.
- `OCR_PROVIDER=none` or local OCR.
- `FORMULA_OCR_PROVIDER=none`.
- `DEBUG=true`.

Never use real student private data or production databases in development.

## Staging

Purpose: small pilot verification with controlled data and production-like settings.

Recommended:

- `DEBUG=false`.
- Separate database and upload folder.
- Structured logs enabled.
- Optional live AI and OCR provider.
- Mock payment may remain enabled if billing is not under test.
- Full pytest and smoke evaluation before user trials.

## Production

Production must be conservative:

- `APP_ENV=production`.
- `DEBUG=false`.
- Strong `SECRET_KEY`.
- No mock AI, mock email, or mock payment as real capabilities.
- PostgreSQL or equivalent managed database.
- Object storage or durable file storage.
- Concrete CORS allowlist.
- Structured logs with redaction.
- Backup and restore plan.
- Cost and quota limits.

Run:

```bash
python scripts/check_env.py --env production --file .env.production
```

The production template intentionally fails until placeholders are replaced.
