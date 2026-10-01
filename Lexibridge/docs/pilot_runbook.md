# Pilot Runbook

Updated: 2026-08-17

This runbook is for local demo and small-course pilot operation. It is not a production deployment guide.

## Environment Requirements

- Canonical external Python runtime created with `bash scripts/bootstrap_runtime.sh`.
- SQLite database for local/demo/small pilot.
- Browser capable of opening `frontend/index.html`.
- No external LLM provider is required or enabled.
- Do not place real API keys in `.env`, README, demo fixtures, logs, or release packages.

## Safe Configuration

Use environment variables similar to:

```bash
DATABASE_URL=sqlite:////absolute/path/to/lexibridge.db
UPLOAD_FOLDER=/absolute/path/to/uploads
AUTH_REQUIRED=True
AI_PROVIDER=none
ALLOW_MOCK_AI=True
OCR_PROVIDER=none
FORMULA_OCR_PROVIDER=none
```

External provider keys such as `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` are not needed for the pilot. External provider classes remain disabled by policy/governance gates.

## Database Initialization

Run:

```bash
bash scripts/bootstrap_runtime.sh
bash scripts/run_python.sh scripts/migrate_db.py --apply
```

The default macOS runtime is outside the Desktop repository at
`~/Library/Application Support/LexiBridge-AI/runtime`. The launcher probes the
interpreter and required distributions before use. `backend/.venv-macos` is a
temporary compatibility fallback only; new pilot environments must not depend
on it.

The current migration mechanism is `db.create_all()` plus additive `ensure_schema_columns()`. It is suitable for local development, demo, and small-scale pilot upgrade checks. It is not a production-grade Alembic migration system.

## Demo Seed

Create or refresh demo data:

```bash
bash scripts/run_python.sh scripts/seed_review_demo.py --reset-demo
```

Repeat without reset to verify idempotency:

```bash
bash scripts/run_python.sh scripts/seed_review_demo.py
```

The seed creates local-only demo users, course review policy/permissions, student memberships, visibility policies, governed evidence, reviewable cards, approved student cards, learning states, student feedback, and teacher analytics data.

## Start Backend

For the controlled local pilot:

```bash
bash scripts/run_backend.sh
```

The default launcher performs explicit migration and starts Gunicorn through
the WSGI entrypoint. It uses one process by default for the SQLite concurrency
boundary. The Flask development server is available only for deliberate local
debugging:

```bash
LEXIBRIDGE_SERVER_MODE=development bash scripts/run_backend.sh
```

Start the worker through the same verified interpreter selection:

```bash
bash scripts/run_worker.sh
```

## Open Frontend

Open:

```text
frontend/index.html
```

Use the login form with the demo credentials printed by `scripts/seed_review_demo.py`.

## Demo Accounts

Demo accounts are local-only and must not be used in production. The seed prints:

- demo teacher
- demo admin
- demo student
- second demo student for analytics distribution

## Core Demo Route

1. Log in as demo teacher.
2. Open `Concept Card Review`.
3. Review the queue for `DEMO Signals and Systems`.
4. Open a card and inspect English/Chinese evidence, risk labels, verification summary, and review history.
5. Try approving a blocking-risk card and observe backend policy rejection with `request_id`.
6. Log in as demo admin.
7. Approve a card with explicit risk override reason.
8. Log in as demo student.
9. Open `Concept Cards`.
10. Confirm approved cards for `DEMO Signals and Systems` are visible.
11. Confirm `DEMO Hidden Course` cards are not visible.
12. Favorite and mark a card mastered.
13. Submit feedback and export favorited cards.
14. Return to demo teacher.
15. Open `Student Feedback` and triage feedback.
16. Open `Course Learning Analytics` and inspect summary, chapter table, low-mastery list, feedback hotspots, and export.

## Provider Boundary

- `mock-rule-v1` is deterministic mock/rule based.
- `fake-llm-v1` simulates LLM JSON output for parser/gate tests.
- `external-llm-replay-v1` replays local fixtures and does not call the network.
- `deepseek-alignment-v1-disabled` is registered as disabled and must fail safely.

Current pilot has no real LLM production verification.

## Checks

Run release safety:

```bash
bash scripts/run_python.sh scripts/check_release_safety.py
```

Run development checks:

```bash
bash scripts/run_python.sh scripts/dev_check.py
```

Run pilot readiness:

```bash
bash scripts/run_python.sh scripts/pilot_readiness_check.py
```

For a small pilot profile with JSON output:

```bash
bash scripts/run_python.sh scripts/pilot_readiness_check.py \
  --profile small-pilot \
  --json-output /private/tmp/lexibridge-pilot-result.json
```

For a faster local loop:

```bash
bash scripts/run_python.sh scripts/pilot_readiness_check.py --skip-full-tests
```

## Payload-Free Runtime Observation

Record loopback-only health samples outside the repository. The probe rejects
remote targets, credentials, query strings, and non-health paths:

```bash
bash scripts/run_python.sh scripts/collect_runtime_probe.py \
  --endpoint http://127.0.0.1:5000/api/test \
  --target-label pilot-local \
  --jsonl-output /private/tmp/lexibridge-runtime-observation.jsonl
```

Generate an evidence-based report after the declared window:

```bash
bash scripts/run_python.sh scripts/runtime_observation_report.py \
  --log /private/tmp/lexibridge-runtime-observation.jsonl \
  --window-start 2026-08-17T00:00:00Z \
  --window-end 2026-08-31T00:00:00Z \
  --json-output /private/tmp/lexibridge-runtime-observation-report.json
```

The report must remain `RUNTIME_OBSERVATION_PENDING` until actual elapsed days,
active days, samples, and health gates are satisfied. Tooling does not backdate
or infer uptime. This runtime report complements, but does not replace, the
separate legacy-alignment consumer/deprecation observation contract.

Readiness verdicts:

- `READY`: no blocking failures and no remaining operating conditions.
- `READY_WITH_CONDITIONS`: all pilot blockers passed, but operation is bounded by conditions such as SQLite, Flask dev server, disabled external LLM, local demo accounts, no formal migrations, or unavailable browser runtime.
- `NOT_READY`: a blocking check failed. Do not start the pilot until fixed.

The current expected result for local demo or small-course pilot is `READY_WITH_CONDITIONS`, not unqualified `READY`.

## Backup SQLite And Uploads

Stop writes before backup. Then run:

```bash
bash scripts/run_python.sh scripts/pilot_backup.py \
  --database /absolute/path/to/lexibridge.db \
  --uploads /absolute/path/to/uploads \
  --output /private/tmp/lexibridge-pilot-backup
```

The backup directory contains:

- `database.sqlite`
- `uploads/`
- `backup_manifest.json`

The manifest records SHA-256 hashes, table counts, file counts, sizes, timestamp, and commit. It does not include `.env`, Authorization, Cookie, API keys, or provider secrets.

Verify the backup:

```bash
bash scripts/run_python.sh scripts/verify_pilot_backup.py \
  --backup /private/tmp/lexibridge-pilot-backup
```

If the backup is tampered with or hash checks fail, verification returns non-zero.

## Restore SQLite

Restore to new targets first:

```bash
bash scripts/run_python.sh scripts/pilot_restore.py \
  --backup /private/tmp/lexibridge-pilot-backup \
  --database-target /absolute/path/to/restored.db \
  --uploads-target /absolute/path/to/restored-uploads
```

Restore behavior:

- validates manifest and all SHA-256 values before copying;
- refuses to overwrite existing targets unless `--force` is passed;
- does not restore `.env` or secrets;
- runs SQLite `integrity_check`;
- checks core tables after restore.

After restore:

1. Point `DATABASE_URL` and `UPLOAD_FOLDER` to the restored targets.
2. Run `bash scripts/run_python.sh scripts/migrate_db.py --apply`.
3. Run `bash scripts/run_python.sh scripts/pilot_readiness_check.py --skip-full-tests`.
4. Keep external providers disabled during recovery verification.

## Browser E2E

Run browser E2E separately:

```bash
bash scripts/run_python.sh scripts/run_browser_e2e.py \
  --json-output /private/tmp/lexibridge-browser-e2e.json
```

If Python Playwright or Chromium is not installed, the script returns `E2E_ENVIRONMENT_UNAVAILABLE` with exit code `2`; this is not a pass. In readiness, that state becomes `READY_WITH_CONDITIONS` with `browser_e2e_not_executed`.

Install runtime in the project environment before making browser E2E a blocking gate:

```bash
bash scripts/bootstrap_e2e.sh
```

Do not run those installation commands in environments that must stay offline. Browser E2E uses only localhost once the runtime exists.

Headed debug run:

```bash
bash scripts/run_python.sh scripts/run_browser_e2e.py \
  --headed \
  --keep-artifacts \
  --json-output /private/tmp/lexibridge-browser-e2e-debug.json
```

Run only one flow when isolating failures:

```bash
bash scripts/run_python.sh scripts/run_browser_e2e.py --student-only
bash scripts/run_python.sh scripts/run_browser_e2e.py --teacher-only
```

The browser runner:

- creates a temporary SQLite database and uploads directory;
- runs migration and demo seed;
- starts a local Flask server on a random port;
- serves `frontend/index.html` with local `API_BASE`;
- runs student and teacher DOM flows;
- blocks non-localhost requests;
- records JavaScript errors, page errors, failed requests, blocked external URLs, downloads, and failure screenshots to a temporary artifact directory.

Current local browser gate baseline:

- Python Playwright: `1.60.0`;
- Chromium: `148.0.7778.96`;
- student and teacher flows pass in real Chromium;
- console errors and page errors must remain empty;
- page-owned external dependency requests must remain empty;
- deliberate probe requests are blocked and recorded separately.

Browser E2E troubleshooting:

- If strict selectors fail, add stable `data-testid` attributes instead of relying on text-only selectors.
- If a page-owned external URL is blocked, remove the remote dependency or document it as high technical debt.
- If CSV/JSON export fails, inspect the download entry in the JSON result and the artifact directory.
- If Playwright cannot launch Chromium from the sandboxed terminal, run the browser command with the approved local runtime access used by the pilot host.
- Clean temporary artifacts by deleting the `artifacts_directory` reported in the JSON result when `--keep-artifacts` is used.

## Clean Demo Data

Run:

```bash
bash scripts/run_python.sh scripts/seed_review_demo.py --reset-demo
```

This resets and recreates the demo namespace. It does not delete arbitrary user/course data outside the demo markers.

## View AuditRecord

Use admin APIs or inspect SQLite locally for `audit_record`. Audit payloads are summaries only and should not contain Authorization, Cookie, API keys, full prompts, raw provider output, or full evidence text.

## Common Troubleshooting

- `AUTH_REQUIRED` errors: log in again and use the returned bearer token.
- Empty student cards: verify `StudentCourseMembership`, `CourseStudentVisibilityPolicy`, and `ConceptAlignmentCard.status=approved`.
- Review queue empty for teacher: verify `CourseReviewPermission`.
- Provider disabled: expected for external providers unless a future explicit provider task changes policy.
- Upload blocked: inspect `DocumentParseRecord.quality_status` and quality flags.

## Rollback

For a local/small pilot rollback:

1. Stop backend.
2. Verify the last backup with `scripts/verify_pilot_backup.py`.
3. Restore SQLite and uploads with `scripts/pilot_restore.py`.
4. Do not reuse demo credentials in real pilots.
5. Keep external providers disabled.
6. Re-run `scripts/pilot_readiness_check.py --skip-full-tests`.

## Pre-Pilot Checklist

- `scripts/check_release_safety.py` passes.
- `scripts/dev_check.py` passes.
- `scripts/pilot_readiness_check.py --profile small-pilot` returns `READY_WITH_CONDITIONS`.
- A backup has been created, verified, and restored to a temporary target.
- Browser E2E has passed in real Chromium. `E2E_ENVIRONMENT_UNAVAILABLE` is acceptable only for diagnostic local runs before the pilot gate is active, not for starting a 9B.1-hardened pilot.
- SQLite single-writer limits are acceptable for the planned pilot.
- Flask dev server boundary is accepted for the local/demo setting.
- Demo accounts are marked local-only and cleaned after the session.
- External LLM providers remain disabled.
