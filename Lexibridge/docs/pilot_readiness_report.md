# Pilot Readiness Report

Execution date: 2026-07-11
Commit checked: current working tree after Task 9B.1 browser E2E gate hardening
Scope: Task 9B.1 small-pilot hardening audit for the current local LexiBridge-AI workspace.

## Verdict

**READY WITH CONDITIONS**

The automated readiness gate (`scripts/pilot_readiness_check.py`) completed with final machine-readable status **READY_WITH_CONDITIONS**. This now matches the report verdict. The system is suitable for a controlled local/demo/small-course pilot, not production deployment.

Readiness verdict semantics:

- `READY`: all mandatory checks pass and no operating conditions remain.
- `READY_WITH_CONDITIONS`: pilot-blocking checks pass, but bounded operating conditions remain.
- `NOT_READY`: a blocking check failed, including backup/restore, security, data integrity, permissions, or browser E2E failure when the browser runtime is available.

Current conditions:

- `small_pilot_only`
- `sqlite_database`
- `flask_development_server`
- `external_llm_disabled`
- `demo_local_account_restrictions`
- `formal_migration_not_enabled`
- `production_monitoring_not_enabled`

## Test Summary

- Full pytest: `434 passed, 6 warnings in 87.99s`.
- `scripts/check_release_safety.py`: passed.
- `scripts/dev_check.py`: passed; internal pytest reported `434 passed, 6 warnings in 88.41s`.
- `scripts/pilot_readiness_check.py`: passed; final output `READY_WITH_CONDITIONS`.
- `scripts/run_browser_e2e.py`: passed twice in real Chromium with student and teacher flows.
- Playwright version: `1.60.0`.
- Chromium version: `148.0.7778.96`.

Known warnings:

- SQLAlchemy `Query.get()` legacy warning in `tests/test_ai_provider_registry.py`.
- PDF/SWIG deprecation warnings in mixed PDF test.

## Core Business Flow Results

| Scenario | Result | Notes |
|---|---:|---|
| A. Document to knowledge asset | PASS | TXT upload creates `DocumentParseRecord`, governed source/chunks, parse provenance, and AuditRecord. No ConceptAlignmentCard confidence is fabricated. |
| B. Low-quality file blocked | PASS | Empty upload returns stable 422 JSON with `request_id`, blocked ingestion status, no active chunks, and blocked audit. |
| C. Evidence to Concept Card draft | PASS | Governed bilingual chunks support evidence retrieval, Chinese candidate extraction, bilingual package, and `needs_review` draft with null confidence. |
| D. Alignment verification safety chain | PASS | mock, fake, replay, disabled external, provider policy gate, preflight, attach-only safety, and no-network guard passed. |
| E. Teacher review | PASS | Course permission/policy gates, blocking-risk rejection, admin override with reason, ReviewRecord, AuditRecord, and student review denial passed. |
| F. Student learning | PASS | Approved-only plus course visibility, hidden-course exclusion, favorite, mastered, feedback, export, and no card-status mutation passed. |
| G. Feedback loop | PASS | Student feedback enters teacher queue; unauthorized teacher sees none; triage can acknowledge/request revision; ReviewRecord/AuditRecord created. |
| H. Teacher analytics | PASS | Aggregates approved authorized-course cards only; student denied; export excludes sensitive fields. |

## Permission Matrix

| Actor | Allowed | Denied / Gated | Result |
|---|---|---|---:|
| Student | Visible approved cards, own learning state, own feedback, student export | Review actions, feedback triage, teacher analytics, provider policy, course review policy, hidden-course state | PASS |
| Teacher | Review queue, feedback queue, analytics for authorized course | Unauthorized course data, provider policy management, policy-blocked override | PASS |
| Admin | Review policy, review permission, all-course analytics, allowed risk override | Auto-approve provider output, fake confidence writes, provider gate bypass | PASS |
| Unauthenticated | None for write paths | Review write returns stable JSON auth error | PASS |

## Database Fresh / Upgrade Results

- Fresh database migration: PASS.
- Repeated migration: PASS.
- Existing legacy database upgrade simulation: PASS.
- Legacy rows preserved: PASS.
- New tables verified: review, provider, preflight, usage, student membership/state, visibility, feedback triage, audit.
- Demo seed on upgraded DB: PASS.
- Demo seed idempotency: PASS.
- Pilot backup creation: PASS.
- Pilot backup verification: PASS.
- Pilot restore: PASS.
- Restored SQLite `integrity_check`: PASS.
- Restored core table checks: PASS.
- Backup tamper rejection: covered by `tests/test_pilot_backup_restore.py`.

Current migration mechanism:

- Suitable for local development, demo, and small-scale pilot.
- Not production-grade migration management. A versioned Alembic migration path is still recommended before production.

## OpenAPI Parity

Result: PASS.

Main-chain route/method parity is enforced for:

- document upload;
- governed evidence and bilingual evidence;
- Chinese candidates;
- Concept Card draft/review;
- alignment verification, provider policy/usage/preflight;
- course review policy/permission;
- student Concept Cards, memberships, visibility, progress;
- student feedback queue/triage;
- teacher learning analytics/export.

Legacy/internal routes are not exhaustively checked by the new parity test.

## Data Integrity

Result: PASS.

Checks include:

- approved cards have English term, Chinese term, course, and evidence;
- student states reference existing cards;
- Concept Card feedback references existing cards;
- chunks reference sources;
- parse block provenance is valid when parse records exist;
- review records and provider runs reference valid cards or empty allowed card IDs;
- active memberships and visibility policies are not duplicated;
- JSON list fields parse as lists;
- confidence values are in range;
- mock/fake/replay provider outputs are not production results;
- provider policies do not allow auto-approve;
- student API excludes rejected/deprecated/non-approved cards.

## Request ID / Error Response Consistency

Result: PASS for covered main-chain APIs.

Validated behavior:

- success responses include `request_id`;
- permission/policy/validation errors return stable JSON rather than HTML;
- selected upload, evidence, alignment, review, student, feedback, analytics, provider policy/preflight paths are covered through E2E and permission tests;
- `X-Request-ID` is preserved when supplied.

This task did not rewrite the global error framework.

## Security and No-Network

Result: PASS.

- `check_release_safety.py` passed.
- `pilot_readiness_check.py` removes common real LLM API key variables from its subprocess environment.
- Disabled external provider was executed under a patched `socket.socket.connect` and produced a failed run without network.
- fake/replay providers used local fixtures only.
- Audit/data-integrity tests check that `Authorization`, `Cookie`, and `sk-` secrets are not stored in audit summaries.
- No real DeepSeek/OpenAI/Claude/translation/embedding/vector/reranker calls occurred.
- Browser E2E executed with localhost-only routing. Two deliberate probe requests were blocked per full run, and no page-owned external dependency requests were observed.

## Browser E2E

Result: PASS.

- `scripts/run_browser_e2e.py --json-output /private/tmp/lexibridge-browser-e2e.json`: PASS.
- `scripts/run_browser_e2e.py --json-output /private/tmp/lexibridge-browser-e2e-repeat.json`: PASS.
- Student flow: login, Concept Cards navigation, approved card visibility, hidden-course exclusion, detail/evidence display, favorite, mastered, feedback, progress refresh, export download, and no review action all passed.
- Teacher flow: login, Concept Review navigation, review queue, course filter, card evidence/risk/history, request revision, feedback acknowledge, learning analytics, analytics export, and policy-block request_id display all passed.
- Browser: Chromium `148.0.7778.96`.
- Playwright: `1.60.0`.
- JavaScript console errors: 0.
- Page errors: 0.
- Page-owned external dependency requests: 0.
- Deliberately blocked external probe requests: 2 per full run.
- Student export download: `concept-cards-all.json`, 2413 bytes.
- Teacher export download: `teacher_learning_analytics.csv`, 460 bytes.

## Performance Smoke

Demo data, local Flask test client:

| API | Time | Result count |
|---|---:|---:|
| Review queue | 9 ms | 3 |
| Student card list | 5 ms | 3 |
| Student progress | 6 ms | 1 summary |
| Feedback queue | 5 ms | 4 |
| Teacher analytics | 4 ms | 3 approved cards |

No demo endpoint exceeded the 2 second warning threshold.

Performance numbers are demo-scale smoke results only. They are not production capacity metrics.

## Warnings

- Current analytics are real-time aggregate queries; they are acceptable for demo data but need profiling/indexes for larger cohorts.
- OpenAPI parity is scoped to main-chain APIs and does not guarantee every legacy/internal route is documented.
- Frontend is still a single large HTML file with inline script.
- Browser-level E2E is active for core student and teacher flows, but coverage is limited to desktop Chromium and does not include mobile, cross-browser, accessibility, or visual regression checks.
- SQLite and Flask dev server are not production deployment primitives.

## Blocking Issues

Resolved during Task 9A:

- Provider registry/policy GET routes allowed `student`; fixed to require teacher/admin.
- Legacy `feedback` table upgrade missed fields needed by Concept Card feedback/analytics; fixed additive schema columns.

Resolved during Task 9B.1:

- Browser E2E runtime was installed and the unavailable-runtime condition was removed from the pilot verdict.
- Browser E2E runner strict selector ambiguity was fixed by using deterministic first-match locators for repeated rows/nav entries.
- The expected teacher policy-block API response is now verified through the UI request_id path without being misclassified as an unhandled JavaScript error.
- `pilot_readiness_check.py` now invokes the current browser runner arguments and records browser E2E JSON summary fields.

Unresolved blocking issues:

- None for a controlled local/small-course pilot.

## Non-Blocking Technical Debt

See `docs/technical_debt_register.md`. Highest remaining non-blocking items:

- `backend/app.py` size and route/model/service coupling.
- Additive migration mechanism instead of versioned Alembic migrations.
- SQLite concurrency boundary.
- Single-file frontend maintainability.
- Browser E2E is installed and passing locally; it still needs regular CI/pilot-host execution.
- Fragmented RBAC domains across role, course permission, course visibility, and provider policy.

## Pilot Conditions

Proceed only if:

- deployment remains local/demo/small-course pilot;
- external providers remain disabled;
- demo credentials remain local-only;
- database and uploads are backed up before trials;
- `scripts/pilot_backup.py`, `scripts/verify_pilot_backup.py`, and `scripts/pilot_restore.py` are used for backup/restore rehearsal;
- teacher/admin review remains the only approval path;
- students only use approved and course-visible Concept Cards;
- any production rollout is preceded by proper migration, deployment, secret, backup, and RBAC hardening.

## Rollback

1. Stop backend writes.
2. Restore the previous SQLite database and uploads backup with `scripts/pilot_restore.py`.
3. Run `scripts/verify_pilot_backup.py` against the backup before restore.
4. Run `scripts/migrate_db.py` once after restore.
5. Run `scripts/pilot_readiness_check.py --skip-full-tests`.
5. Keep external providers disabled during rollback verification.

## Backup Recommendation

Before a pilot session:

- create a backup with `scripts/pilot_backup.py`;
- verify it with `scripts/verify_pilot_backup.py`;
- rehearse restore to a temporary target with `scripts/pilot_restore.py`;
- export or snapshot `AuditRecord` summaries if the session needs after-action review;
- record the commit hash and readiness report used for the pilot.

## Next Steps

1. Split `backend/app.py` into route modules/blueprints after pilot.
2. Introduce versioned migrations before production.
3. Keep browser E2E as a blocking pilot gate and expand later to mobile/cross-browser/visual coverage.
4. Add indexes/profiling for analytics and review queues after pilot data volume is known.
5. Keep provider governance/preflight gates in place before any real LLM provider task.
