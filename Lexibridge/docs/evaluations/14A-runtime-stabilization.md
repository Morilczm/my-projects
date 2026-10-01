# Task 14A Runtime Stabilization

## Status

- Technical status: `CONTROLLED_RUNTIME_STABILIZATION_CLOSED`
- Quality status: `CONTROLLED_RUNTIME_BASELINE_ESTABLISHED`
- Baseline: `029111df941ed6582ac88096086829baf66efbfb`

## Before

- `scripts/run_backend.sh` activated the first directory-shaped virtual
  environment it found without probing it.
- Startup ran `python backend/app.py`, which used Flask's development server.
- Base application requirements used unbounded package names.
- Backend, worker, migration, and test instructions named different Python
  entrypoints.
- Legacy observation tooling existed, but there was no generic payload-free
  runtime uptime probe/report contract.

## After

- A canonical Python 3.12 external runtime was created outside the Desktop
  repository and selected before the legacy in-repository environment.
- Runtime, development, and Browser E2E dependencies are separately and exactly
  pinned.
- Browser dependencies and Chromium use a separate verified-TLS bootstrap.
- The default backend starts Gunicorn 23.0.0 through `wsgi:application`.
- SQLite defaults to one Gunicorn process with four bounded threads.
- Development server use requires an explicit mode.
- Backend, worker, migration, test, and operator tools share one interpreter
  resolver.
- Loopback-only payload-free runtime probes and an evidence-based observation
  report are available.

## Verification

- RED-first contract: 8 initial failures due to missing runtime contracts.
- Targeted runtime/dev tests: pass.
- External runtime dependency integrity: `pip check` pass.
- Temporary SQLite migration: pass.
- Gunicorn master and gthread worker boot: pass.
- Loopback `/api/test`: HTTP 200, healthy.
- Safe access log: method/path/status/duration only; no query/body/client request ID.
- Worker `--once`: pass with no queued job.
- Browser E2E: PASS in one complete run.
  - Student: PASS (Personal and Managed Course query, private notebook, privacy boundary).
  - Instructor: PASS (English course-side dashboard, no Reviewer prefetch).
  - Reviewer: PASS (review decision, governed fake draft, no publication).
  - Chromium: 148.0.7778.96 through Playwright 1.60.0.
  - Console/page errors: 0/0.
  - External page dependencies: 0.
- Student browser state validation accepts the governed `READY`,
  `REVIEW_REQUIRED`, and `NOT_READY` display contracts instead of hard-coding
  one fixture as automatically ready.
- Reviewer browser submission waits for the detail/history/review-case renders
  to settle before entering the required rationale.
- Mainline capability acceptance drains the shared fake Formal queue with a
  hard bound until the requested fixture run is terminal, removing an
  order-dependent false failure without changing production parsing.
- Targeted runtime/browser tests: PASS (`26 passed`).
- Full pytest: PASS (`1710 passed`, `7 skipped`).
- `dev_check`: PASS (`1710 passed`, `7 skipped`, migration and API smoke pass).
- Release safety: PASS.
- `git diff --check`: PASS.
- Application external API requests: 0.
- Real Provider requests: 0.
- Real credentials read: false.

## Frozen V2 and Database Safety

- Cross-Corpus V2 manifest SHA-256:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`.
- Cross-Corpus V2 gold SHA-256:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`.
- English bundle SHA-256:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`.
- Chinese bundle SHA-256:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`.
- The frozen parsing/retrieval/pairing/qualification implementation and data
  were not modified.
- Accident database before/final contract:
  SHA-256 `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`,
  size 1015808, mtime 1785496597, WAL/SHM absent.

## Observation Truthfulness

The runtime observation mechanism is established, but the real multi-day
observation window is not declared complete. Its status remains
`RUNTIME_OBSERVATION_PENDING` until actual retained samples satisfy elapsed-day,
active-day, presence, and health gates. This does not block offline parser
benchmark development, but it remains required before claiming sustained pilot
uptime.

## Next Ordered Step

Run the controlled current-parser versus Docling versus MinerU benchmark on
synthetic or explicitly licensed English and Chinese PDFs. No parser may be
connected to production ingestion until the benchmark and provenance audit are
complete.
