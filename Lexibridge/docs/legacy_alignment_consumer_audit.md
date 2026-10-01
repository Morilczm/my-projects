# Legacy Alignment Consumer Audit

## Audit Decision

Task 9C.5L establishes the source branch `release/pilot-v1-candidate` from
baseline `8ba533ab43fc36e952268c5ea385397778b6fbd5` as the first LexiBridge AI
Pilot v1.0 Candidate.

`POST /api/alignment/run` remains an `ACTIVE COMPATIBILITY SURFACE`. It is not
removed, changed, or converted to HTTP 410 by this task. The in-repository
production teacher workflow no longer calls it, but compatibility tests,
safety probes, the legacy worker path, OpenAPI, and potentially unknown
external clients still depend on its current behavior.

## Consumer Matrix

| Consumer | Location | Type | Status | Action |
|---|---|---|---|---|
| Formal teacher start, polling, and item pages | `frontend/index.html`; `frontend/js/formal-workflow.js` | frontend | migrated | keep |
| Legacy historical run list | `frontend/index.html` (`loadAlignmentRuns`, `GET /api/alignment/runs`) | frontend | active | keep |
| Legacy alignment POST route | `backend/app.py` (`run_alignment`) | backend | active | keep |
| Legacy alignment job execution | `backend/app.py` (`process_alignment_job`, `run_background_job`) | backend | active | keep |
| Legacy provider-intent containment | `backend/services/legacy_alignment_provider_classification.py` | backend | active | keep |
| Legacy route, permission, persistence, and worker characterization | `tests/test_api_contract.py`; `tests/test_permissions.py`; `tests/test_worker.py`; `tests/test_card_generation.py`; `tests/test_provider_admin_route_characterization.py`; `tests/test_legacy_alignment_run_characterization.py` | test | active | keep |
| Legacy external-execution and no-network containment | `tests/test_legacy_alignment_external_execution_disabled.py`; `tests/test_legacy_alignment_worker_external_execution_disabled.py`; `tests/test_legacy_alignment_browser_e2e_runner.py` | test | active | keep |
| Formal workflow zero-legacy dependency gates | `tests/test_document_alignment_processing_boundary.py`; `tests/test_formal_document_alignment_workflow_boundary.py`; `tests/test_formal_workflow_frontend_cutover_contract.py`; `tests/test_formal_workflow_frontend_e2e_runner.py` | test | migrated | keep |
| Frontend legacy history contract | `tests/test_frontend_contract.py` | test | active | keep |
| Legacy browser compatibility runner | `scripts/run_legacy_alignment_browser_e2e.py` | script | active | keep |
| Pilot readiness legacy containment probe | `scripts/pilot_readiness_check.py` | script | active | keep |
| Formal browser zero-legacy request gates | `scripts/run_formal_workflow_frontend_e2e.py`; `scripts/run_formal_workflow_frontend_resume_e2e.py` | script | migrated | keep |
| OpenAPI legacy operation | `docs/openapi.yaml` | documentation | active | keep |
| Current legacy boundary and deprecation ADR | `docs/legacy_alignment_run_boundary.md`; `docs/adr/ADR-legacy-alignment-run-deprecation.md` | documentation | active | keep |
| Historical design, demo, route-inventory, and extraction references | `README.md`; `docs/alignment-design.md`; `docs/api-contract.md`; `docs/architecture_map.md`; `docs/demo-test-report.md`; `docs/formal_document_alignment_frontend_cutover.md`; `docs/formal_document_alignment_workflow_boundary.md`; `docs/implementation-design.md`; `docs/job-queue-design.md`; `docs/provider_admin_route_inventory.md`; `docs/route_extraction_checkpoint.md`; `docs/technical_debt_register.md`; `docs/adr/ADR-formal-document-alignment-workflow.md`; `docs/adr/ADR-legacy-prompt-mutation-policy.md`; `docs/legacy_provider_admin_surface.md`; `docs/legacy_provider_healthcheck_boundary.md`; `docs/legacy_provider_prompt_mutation_boundary.md`; `docs/superpowers/plans/2026-07-20-formal-workflow-frontend-cutover.md` | documentation | deprecated | remove later |
| Clients outside this repository | external inventory unavailable | external | unknown | investigate |

## Frontend Result

There is no production frontend request to `POST /api/alignment/run`.
`frontend/js/formal-workflow.js` uses only:

- `POST /api/document-alignment-runs`;
- `GET /api/document-alignment-runs/{run_uid}`;
- `GET /api/document-alignment-runs/{run_uid}/items`.

The remaining frontend string is `GET /api/alignment/runs` in
`loadAlignmentRuns()`. It is an active historical-list compatibility view,
not a legacy execution fallback.

## Backend Result

The legacy POST route remains registered once as endpoint `run_alignment`.
It still owns the legacy synchronous and queued execution contracts and the
legacy `alignment_run` worker job type. External/live provider intent remains
fail-closed through `legacy_alignment_provider_classification.py`.

The formal workflow has separate routes, models, admission, query, dispatch,
worker, and processing services. Its job type is
`formal_document_alignment_workflow_v1`; it does not dispatch through the
legacy `alignment_run` execution branch.

## Formal Workflow Independence

The formal teacher chain is:

```text
upload -> governed source_uid -> formal POST -> formal run polling
       -> server-paginated formal items -> result rendering
```

Static route scans, frontend contract tests, formal workflow tests, and browser
request counters establish that this chain does not call or fall back to
`POST /api/alignment/run`. Formal API failure stays on the formal error path.

Result: `FORMAL_WORKFLOW_INDEPENDENT_FROM_LEGACY_ALIGNMENT_EXECUTION`.

## Deprecation Preconditions

Task 9C.5M may prepare deprecation, but HTTP 410 or code removal must wait until:

1. external consumers are inventoried or an explicit compatibility window is approved;
2. the active legacy browser/readiness probes are replaced with deprecation-contract tests;
3. legacy `alignment_run` queued/running jobs have a documented drain or quarantine policy;
4. the historical `GET /api/alignment/runs*` UI contract is separately migrated or retained;
5. OpenAPI and operator documentation receive an approved deprecation notice.

This audit does not authorize route deletion, response changes, permission
changes, parameter changes, or HTTP 410.
