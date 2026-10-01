# Task 13C.4 — Personal Concept Notebook

## Status

- Technical status: `PERSONAL_CONCEPT_NOTEBOOK_CONTRACT_CLOSED`
- Quality status: `PERSONAL_CONCEPT_NOTEBOOK_BASELINE_ESTABLISHED`
- Baseline: `8f09cec79dc4d9ae85cdeea1b9a9f94cd4c93acc`
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

This status is a synthetic/local engineering baseline, not evidence of real
student learning value.

## Read-only audit

The production audit found a reusable `StudentConceptQuery` result aggregate
and one private `PersonalLearningRecord` write path. Per-result save, note,
understanding state, last-viewed time, ownership and optimistic versioning were
already present. Missing product capabilities were the aggregate notebook
read model, list/search/filter/history/revisit APIs, private notebook navigation
and browser acceptance. The older learning page was tied to published/legacy
card state and could not substitute for the private notebook.

## Production change

```text
before:
ConceptQuery -> private result -> per-result personal state

after:
ConceptQuery -> same private result -> same PersonalLearningRecord
  -> private notebook list/search/filter
  -> bounded result detail
  -> idempotent revisit
  -> same note/save/understanding editor
```

Personal and Managed Course records use the same route, serializer, frontend
page and state editor. Course membership is rechecked on every read. Ordinary
course results remain private and non-official.

No migration or new table was introduced. Alignment, retrieval, Chinese
candidate generation, pairing, qualification, readiness, Prompt and Provider
code were not modified.

## Contract results

- default view: saved private results;
- additional views: history, understood, still confused;
- filters: workspace, alignment status and bounded owner-only search;
- list pagination: maximum 50 rows;
- list note exposure: maximum 240-character owner-only preview;
- detail evidence: existing bounded Student AlignmentResult contract;
- mutation concurrency: optimistic version;
- mutation idempotency: audit-backed HMAC-SHA-256 fingerprint;
- source deletion: history retained, source/evidence marked unavailable;
- course membership revocation: subsequent read blocked;
- authority/publication: fixed `PRIVATE / NON_OFFICIAL / NOT_APPLICABLE`.

## Verification

- RED tests: 10 expected failures from missing Notebook API/UI/idempotency;
- targeted Student/notebook/workspace/Reviewer/publication regression:
  `77 passed`;
- Browser E2E: Student PASS (55 steps), Instructor PASS (7 steps), Reviewer
  PASS (15 steps), no console/page errors and external dependency requests 0;
- full pytest: `1663 passed, 5 skipped, 56 warnings`;
- `scripts/dev_check.py`: passed, including its independent full pytest,
  migration and backend smoke;
- `scripts/check_release_safety.py`: passed;
- `git diff --check`: passed;
- tracked model/cache scan: no tracked weights or cache directories.

Frozen Cross-Corpus V2 hashes must remain unchanged:

- English: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Accident database must remain:

- SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: `absent / absent`.

Final accident database verification matched all four values above.

## Known scale gap

The first notebook read model scans and enriches the current student's query
history before applying derived-state filters. This preserves exact filtering
and privacy semantics without a migration, and is suitable for the current
synthetic/local baseline. A later scale task should add a database-backed read
index and cursor pagination while preserving this API contract.

## Artifact hashes

- `13C4-browser-e2e-result.json`:
  `db4c049c7ad37a09dfa56144eef3e55dd8db39a3ccb8b98a1f663ce4954efe49`
- `13C4-idempotency-audit.json`:
  `99794881ad70f614544b4d78b317a2c2b8c808ccbee934a1b74e73c9cbdfd751`
- `13C4-notebook-access-matrix.csv`:
  `bcc8b0899785852e06041a79471a6afd9554817cfa23f1240c900ec63164a58d`
- `13C4-personal-notebook-contract.json`:
  `c7f47e421b8f64b798a3217a63d9fd86c59b0eb1a06a4793efc3514e936380e5`
