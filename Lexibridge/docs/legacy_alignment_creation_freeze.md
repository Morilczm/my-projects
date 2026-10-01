# Legacy Alignment Creation Freeze

## Decision

- Task: `9C.5N.2`
- Baseline: `9762b03197b0a919b72fd6ced913982d0da4a794`
- Target: stop production-reachable legacy creation without deleting history
- Route status: active deprecated compatibility surface
- HTTP 410 authorization: not granted

## Creation Matrix

| Entry | Location | Production reachable | Admission controlled | Classification | Action |
|---|---|---:|---:|---|---|
| Legacy POST async | `backend/app.py` `run_alignment()` | yes | yes: route guard plus job factory guard | Must remain during migration | close at Freeze; retain 503 migration response |
| Legacy POST sync term | `backend/app.py` `run_alignment()` | yes | yes: route guard | Must remain during migration | close at Freeze |
| Legacy POST sync document | `backend/app.py` `run_alignment()` | yes | yes: route guard plus helper guard | Must remain during migration | close at Freeze |
| Sync document upload | `backend/app.py` `upload_document()` | yes | yes: rejected before file/domain writes when creation is closed | Migration only | use async upload plus Formal Workflow |
| Direct alignment helper | `backend/app.py` `run_alignment_for_chunks()` | yes through internal callers | yes when no existing run is supplied | Migration only | no new run outside Active |
| Legacy job factory | `backend/app.py` `create_background_job()` | yes through internal callers | yes for `alignment_run` | Migration only | no new job outside Active |
| Legacy worker document execution | `backend/app.py` `process_alignment_job()` | yes for existing jobs | does not create a new run; reuses linked run | Must remain during migration | allowed only in Active or Draining |
| Demo/readiness setup | `scripts/run_demo_flow.py`, `scripts/pilot_readiness_check.py` | no | test-owned setup may construct isolated records | Test only | retain until deprecation tests are converted |
| Tests and fixtures | `tests/` | no | isolated test setup | Test only | retain as contract evidence |
| Admin creation action | repository scan | no action found | not applicable | Can remove later | no implementation exists |
| External callers | outside repository | potentially through Legacy POST | controlled at server route | Must remain during migration | identify during observation window |

## Unified Admission

Production creation is allowed only when both conditions are true:

```text
LEGACY_ALIGNMENT_RUNTIME_STATE=active
LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=true
```

The central admission check is applied at the HTTP route, synchronous upload,
direct helper, and job factory. The helper accepts an existing linked run only
for drain execution; it does not create another `AlignmentRun` in that path.

When admission is closed:

- the Legacy POST returns HTTP 503 `LEGACY_ALIGNMENT_ADMISSION_DISABLED`;
- synchronous upload returns the same safe code before upload/domain writes;
- internal helper and job-factory bypass attempts raise
  `LegacyAlignmentAdmissionError`;
- asynchronous document upload and the Formal Workflow remain available.

## Classification Result

All repository production-reachable creation paths are covered by the unified
admission boundary. Direct model construction remains only in test/demo audit
setup and is not an application creation API.

```text
LEGACY_ALIGNMENT_CREATION_FREEZE_BOUNDARY_COMPLETE
```
