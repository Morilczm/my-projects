# Release Checklist

This checklist applies to the LexiBridge AI Local MVP / Course Demo Release.

## Preflight

```bash
backend/.venv-macos/bin/python -m py_compile backend/app.py scripts/migrate_db.py
backend/.venv-macos/bin/python -m py_compile backend/services/*.py
bash -n scripts/run_backend.sh
python scripts/migrate_db.py
```

Frontend syntax:

```bash
awk '/<script>/{flag=1;next}/<\/script>/{flag=0}flag' frontend/index.html > /tmp/lexibridge-frontend.js
node --check /tmp/lexibridge-frontend.js
```

## Regression Tests

```bash
backend/.venv-macos/bin/python -m pytest tests/test_api_contract.py
backend/.venv-macos/bin/python -m pytest tests/test_auth.py tests/test_permissions.py
backend/.venv-macos/bin/python -m pytest tests/test_upload_security.py
backend/.venv-macos/bin/python -m pytest tests/test_personal_privacy.py
backend/.venv-macos/bin/python -m pytest tests/test_migrations.py
backend/.venv-macos/bin/python -m pytest tests/test_jobs.py tests/test_job_api.py tests/test_worker.py
backend/.venv-macos/bin/python -m pytest
```

## Release Package

```bash
bash scripts/package_release.sh
```

The generated archive is written to `dist/` with a version and date in the file name, for example:

```text
dist/LexiBridge-AI-Local-MVP-v0.8-20260622.zip
```

Validate an existing zip manually:

```bash
python scripts/check_release_package.py dist/<release>.zip
```

## Files That Must Not Be In The Zip

- `.env`
- real API keys
- `*.db`, `*.sqlite`, `*.sqlite3`
- `uploads/`
- derived upload images
- virtual environments
- `.git/`
- `__pycache__/`
- `.pytest_cache/`
- `.DS_Store`
- `__MACOSX`
- `node_modules/`
- personal local paths such as machine-specific home-directory paths

## Manual Demo Smoke

1. Run migration.
2. Start backend.
3. Open `frontend/index.html`.
4. Login as Teacher, upload a TXT course document, inspect `Job Status`, then run `python scripts/run_worker.py --once`; this standard mode handles Formal Workflow plus generic ingestion/evaluation jobs and never legacy `alignment_run` jobs.
5. When explicitly validating legacy compatibility, use a separate `python scripts/run_worker.py --mode legacy-alignment --once` process and record the reason.
6. Before a Legacy freeze rehearsal, run `python scripts/legacy_alignment_runtime.py status`, record queue counts, and confirm the apply gate remains false unless a reviewed stale-job disposition is being executed.
7. During a Legacy observation window, retain payload-free application logs and summarize them with `python scripts/legacy_alignment_observation_report.py`; do not treat local E2E traffic as target-environment evidence.
8. Run terminology alignment and inspect cards/QC.
9. Login as Student, search cards, favorite, mastered, feedback.
10. Student uploads personal TXT and verifies another student cannot access it.
11. Login as Admin, inspect users, logs, usage, ingestion jobs, background jobs, personal access audit.
12. Run evaluation smoke set through `/api/evaluation/run`, then process the queued job with the worker.

## Release Notes Must Be Honest

Do not describe the release as production-ready. State clearly:

- Local Flask + SQLite MVP.
- Mock email.
- Mock payment.
- DeepSeek only when configured.
- Mock/local AI cannot auto-approve.
- No production vector database.
- No school/publisher/ByrDocs connector.
- Formula OCR requires optional provider.
- Background jobs use a local SQLite polling worker, not a production distributed queue.
