# Formal Workflow Frontend Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the teacher document-alignment action with the formal workflow API, including bounded polling, session-scoped recovery, paginated items, and browser evidence that the main UI no longer calls the legacy alignment endpoint.

**Architecture:** Keep the existing single-page `frontend/index.html` composition and add one dependency-free browser module, `frontend/js/formal-workflow.js`, for API, storage, idempotency, and polling concerns. The inline application remains the view adapter: it resolves an uploaded document to a server-created governed `source_uid`, renders the existing page with a compact formal-run panel, and delegates transport/state behavior to the module.

**Tech Stack:** Vanilla HTML/CSS/JavaScript, browser Fetch/AbortController/Web Crypto/sessionStorage, Flask formal workflow API, Python pytest contract tests, Playwright Chromium E2E.

## Global Constraints

- Baseline is `2afe5b404c9d50d923a83c68a0876d2ed2248a8c`; branch is `feat/formal-workflow-frontend-cutover-9c5h`.
- Do not modify backend production code, models, schema, routes, OpenAPI, admission, query, worker, orchestrator, provider, retry, or the legacy backend endpoint.
- The teacher main flow must use only `POST /api/document-alignment-runs`, `GET /api/document-alignment-runs/{run_uid}`, and `GET /api/document-alignment-runs/{run_uid}/items` for alignment execution and results.
- The legacy `/api/alignment/run` route remains registered, but the teacher frontend must neither call it nor fall back to it.
- Formal start accepts only the server-issued governed `source_uid`; never derive it from filename, `parse_uid`, DOM text, or browser-generated values.
- New idempotency keys use Web Crypto, are at most 128 characters, are never placed in URLs or logs, and are reused after ambiguous POST failures.
- Persist only the versioned active-run allowlist in `sessionStorage`; never persist auth, evidence, prompts, raw output, transport ownership, or whole API responses.
- Poll one request at a time, clamp intervals to 1-10 seconds, stop at formal terminal states, abort superseded work, and stop after three consecutive network failures.
- Render API strings with escaped HTML or DOM `textContent`; never inject API text directly through `innerHTML`.
- No new frontend framework, state-management library, Node build chain, history center, review workbench, or visual redesign.
- Never use `git add .` or `git add -A`.

---

### Task 1: Freeze Frontend Boundaries and Write Failing Contract Tests

**Files:**
- Create: `tests/test_formal_workflow_frontend_cutover_contract.py`
- Create: `tests/test_formal_workflow_frontend_state_contract.py`
- Modify: `tests/test_document_alignment_processing_boundary.py`
- Modify: `tests/test_formal_document_alignment_workflow_boundary.py`
- Modify: `tests/test_legacy_alignment_run_characterization.py`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: current teacher course-upload page, `KnowledgeSource.document_id/source_uid`, formal API paths, existing bearer authentication.
- Produces: executable expectations for `window.LexiFormalWorkflow`, formal teacher endpoints, storage key `lexibridge.formalAlignment.activeRun.v1`, and zero teacher legacy calls.

- [ ] **Step 1: Add contract tests for the formal module and teacher integration**

```python
def test_teacher_alignment_entry_uses_formal_workflow_only():
    index = FRONTEND.read_text(encoding="utf-8")
    module = FORMAL_MODULE.read_text(encoding="utf-8")
    assert "/api/document-alignment-runs" in module
    assert 'api("/api/alignment/run"' not in index
    assert "runAlignmentForDocument" not in index
    assert "startFormalAlignmentForDocument" in index
    assert "legacy" not in module.casefold()
```

- [ ] **Step 2: Add state-policy tests for crypto keys, storage allowlist, terminal states, polling bounds, and safe rendering**

```python
def test_formal_state_contract_is_bounded_and_secret_free():
    source = FORMAL_MODULE.read_text(encoding="utf-8")
    assert "crypto.randomUUID" in source
    assert "crypto.getRandomValues" in source
    assert "Math.random" not in source
    assert "Date.now()" not in source
    assert "MAX_NETWORK_FAILURES = 3" in source
    assert "MIN_POLL_INTERVAL_SECONDS = 1" in source
    assert "MAX_POLL_INTERVAL_SECONDS = 10" in source
    assert "innerHTML" not in source
```

- [ ] **Step 3: Revise legacy characterization to assert route retention and frontend independence**

```python
assert "/api/alignment/run" in contract["paths"]
assert '@app.route("/api/alignment/run", methods=["POST"])' in app_source
assert 'api("/api/alignment/run"' not in frontend
assert "startFormalAlignmentForDocument" in frontend
```

- [ ] **Step 4: Run the tests and verify the intended failures**

Run: `backend/.venv-macos/bin/python -m pytest tests/test_formal_workflow_frontend_cutover_contract.py tests/test_formal_workflow_frontend_state_contract.py tests/test_document_alignment_processing_boundary.py tests/test_formal_document_alignment_workflow_boundary.py tests/test_legacy_alignment_run_characterization.py tests/test_frontend_contract.py -q`

Expected: FAIL because `frontend/js/formal-workflow.js`, the formal teacher action, and formal active-run UI are absent.

### Task 2: Implement the Formal API, Storage, and Polling Module

**Files:**
- Create: `frontend/js/formal-workflow.js`
- Test: `tests/test_formal_workflow_frontend_cutover_contract.py`
- Test: `tests/test_formal_workflow_frontend_state_contract.py`

**Interfaces:**
- Consumes: `baseUrl`, bearer-token callback, `fetch`, `sessionStorage`, Web Crypto, timer functions.
- Produces: `window.LexiFormalWorkflow.createController(options)` with `start`, `resume`, `loadItems`, `retryPolling`, `cancel`, `clear`, and `getState`.

- [ ] **Step 1: Define frozen constants and the persisted state allowlist**

```javascript
const STORAGE_KEY = "lexibridge.formalAlignment.activeRun.v1";
const TERMINAL_STATUSES = new Set(["ready_for_review", "completed_with_warnings", "blocked", "failed"]);
const PERSISTED_FIELDS = [
  "source_uid", "idempotency_key", "run_uid", "location", "items_url",
  "started_at", "last_status", "poll_interval_seconds", "page", "page_size"
];
```

- [ ] **Step 2: Implement crypto-backed idempotency generation and strict state validation**

```javascript
function createIdempotencyKey(cryptoApi = window.crypto) {
  const value = typeof cryptoApi.randomUUID === "function"
    ? cryptoApi.randomUUID()
    : randomUuidFromBytes(cryptoApi.getRandomValues(new Uint8Array(16)));
  return `ui-formal-alignment-v1-${value}`;
}
```

- [ ] **Step 3: Implement the formal HTTP client**

```javascript
async function request(path, options = {}) {
  const response = await fetchImpl(`${baseUrl}${path}`, {
    ...options,
    headers: buildHeaders(options.headers)
  });
  const payload = await readJson(response);
  if (!response.ok) throw toSafeHttpError(response, payload);
  return { data: payload.data || {}, requestId: response.headers.get("X-Request-ID") || "", response };
}
```

- [ ] **Step 4: Implement start/replay without changing the pending key after uncertainty**

```javascript
async function start(sourceUid) {
  ensureNoCompetingStart(sourceUid);
  const active = state.source_uid === sourceUid && state.idempotency_key
    ? state
    : createPendingState(sourceUid, createIdempotencyKey());
  persist(active);
  const result = await request("/api/document-alignment-runs", {
    method: "POST",
    headers: { "Idempotency-Key": active.idempotency_key },
    body: JSON.stringify({ source_uid: sourceUid })
  });
  applyStartResponse(result);
  return poll();
}
```

- [ ] **Step 5: Implement one-at-a-time polling, abort, monotonic status checks, and bounded recovery**

```javascript
async function poll() {
  while (!TERMINAL_STATUSES.has(state.last_status)) {
    if (networkFailures >= MAX_NETWORK_FAILURES) return emit("connection_error");
    await wait(clampPollSeconds(state.poll_interval_seconds) * 1000);
    await fetchRunWithSingleAbortController();
  }
  await loadItems(state.page || 1);
  return state;
}
```

- [ ] **Step 6: Implement API-backed item pages and cleanup rules**

```javascript
async function loadItems(page = 1) {
  const result = await request(`${state.items_url}?page=${page}&page_size=${PAGE_SIZE}`);
  state.page = result.data.pagination.page;
  persist(state);
  emit("items", result.data);
  return result.data;
}
```

- [ ] **Step 7: Run focused tests**

Run: `backend/.venv-macos/bin/python -m pytest tests/test_formal_workflow_frontend_cutover_contract.py tests/test_formal_workflow_frontend_state_contract.py -q`

Expected: module-level contracts PASS; page integration assertions remain FAIL until Task 3.

### Task 3: Integrate the Teacher View and Source Identity

**Files:**
- Modify: `frontend/index.html`
- Test: `tests/test_formal_workflow_frontend_cutover_contract.py`
- Test: `tests/test_formal_workflow_frontend_state_contract.py`
- Test: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: `window.LexiFormalWorkflow.createController`, `state.cache.documents`, `state.cache.sources`, existing `api`, bearer token, render cycle.
- Produces: `Lexi.startFormalAlignmentForDocument(documentId)`, `Lexi.resumeFormalAlignment()`, `Lexi.loadFormalAlignmentItems(page)`, and stable `data-testid` controls.

- [ ] **Step 1: Load the module before the existing inline application**

```html
<script src="./js/config.js"></script>
<script src="./js/formal-workflow.js"></script>
```

- [ ] **Step 2: Add the formal active-run state and governed source resolver**

```javascript
function governedSourceForDocument(documentId) {
  return (state.cache.sources || []).find(source => Number(source.document_id) === Number(documentId)) || null;
}
```

- [ ] **Step 3: Replace the teacher button with the formal start action and stable test id**

```html
<button data-testid="formal-alignment-start" class="small secondary"
  onclick="Lexi.startFormalAlignmentForDocument(${doc.id})">
  ${bilingual("开始正式术语对齐", "Start Formal Alignment")}
</button>
```

- [ ] **Step 4: Add minimal run/status/error/items/pagination markup**

```html
<section data-testid="formal-alignment-status" aria-live="polite"></section>
<div data-testid="formal-alignment-progress"></div>
<div data-testid="formal-alignment-error"></div>
<div data-testid="formal-alignment-items"></div>
<button data-testid="formal-alignment-prev">Previous</button>
<button data-testid="formal-alignment-next">Next</button>
<button data-testid="formal-alignment-resume">Continue</button>
```

- [ ] **Step 5: Render statuses distinctly and escape every API value**

```javascript
const FORMAL_STATUS_LABELS = {
  processing: bilingual("处理中", "Processing"),
  ready_for_review: bilingual("可供审核", "Ready for review"),
  completed_with_warnings: bilingual("完成但有警告", "Completed with warnings"),
  blocked: bilingual("业务条件阻断", "Blocked"),
  failed: bilingual("处理失败", "Failed"),
  connection_error: bilingual("连接中断", "Connection interrupted")
};
```

- [ ] **Step 6: Clear active formal state on logout and authentication/not-found outcomes**

```javascript
async logout() {
  formalWorkflow.cancel();
  formalWorkflow.clear();
  // existing logout behavior follows
}
```

- [ ] **Step 7: Restore after authenticated boot without issuing POST**

```javascript
if (user) {
  await loadEverything();
  await formalWorkflow.resume();
}
```

- [ ] **Step 8: Run frontend syntax and contract tests**

Run: `backend/.venv-macos/bin/python -m pytest tests/test_formal_workflow_frontend_cutover_contract.py tests/test_formal_workflow_frontend_state_contract.py tests/test_frontend_contract.py tests/test_document_alignment_processing_boundary.py tests/test_formal_document_alignment_workflow_boundary.py tests/test_legacy_alignment_run_characterization.py -q`

Expected: PASS.

### Task 4: Add Real UI and Reload-Resume E2E

**Files:**
- Create: `scripts/run_formal_workflow_frontend_e2e.py`
- Create: `scripts/run_formal_workflow_frontend_resume_e2e.py`
- Create: `tests/test_formal_workflow_frontend_e2e_runner.py`
- Create: `tests/test_formal_workflow_frontend_security.py`

**Interfaces:**
- Consumes: existing `scripts/run_browser_e2e.py` runtime/login/capture helpers, formal source fixtures, formal worker dispatcher, real UI controls.
- Produces: safe artifacts at `/private/tmp/lexibridge-9c5h-formal-ui-e2e.json` and `/private/tmp/lexibridge-9c5h-resume-e2e.json`.

- [ ] **Step 1: Write failing runner-contract tests**

```python
def test_formal_ui_runner_uses_real_controls_not_browser_fetch_shortcut():
    source = RUNNER.read_text(encoding="utf-8")
    assert 'data-testid="formal-alignment-start"' in INDEX.read_text(encoding="utf-8")
    assert "page.evaluate(async () => fetch" not in source
    assert "run_formal_worker_once" in source
```

- [ ] **Step 2: Implement isolated browser setup and a governed upload/source fixture**

```python
runtime = run_quiet_e2e_setup(base_e2e, database, uploads, "formal_frontend_9c5h")
source = create_formal_source(module, suffix="frontend", owner_email=teacher["email"])
```

- [ ] **Step 3: Drive the actual teacher UI and network assertions**

```python
page.get_by_test_id("formal-alignment-start").click()
assert wait_for_request_count(capture, "/api/document-alignment-runs", "POST") == 1
assert request_count(capture, "/api/alignment/run") == 0
with module.app.app_context():
    assert module.run_formal_worker_once(worker_id="formal-ui-worker").outcome == "completed"
expect_visible(page, '[data-testid="formal-alignment-items"]', "formal items", flow)
```

- [ ] **Step 4: Verify duplicate-click protection, warning/blocked copy, pagination, and security sentinel absence**

```python
start.click(click_count=2, delay=0)
assert formal_post_count == 1
assert legacy_request_count == 0
assert SENTINEL not in page.locator("body").inner_text()
```

- [ ] **Step 5: Implement real reload recovery**

```python
run_uid = page.evaluate("() => JSON.parse(sessionStorage.getItem('lexibridge.formalAlignment.activeRun.v1')).run_uid")
page.reload(wait_until="networkidle")
assert post_count_after_reload == post_count_before_reload
assert restored_run_uid(page) == run_uid
```

- [ ] **Step 6: Run runner/security tests**

Run: `backend/.venv-macos/bin/python -m pytest tests/test_formal_workflow_frontend_e2e_runner.py tests/test_formal_workflow_frontend_security.py -q`

Expected: PASS.

### Task 5: Update Readiness and Documentation

**Files:**
- Modify: `scripts/pilot_readiness_check.py`
- Modify: readiness tests matched by `rg -l 'FORMAL_API_BROWSER_SESSION_VERIFIED' tests`
- Create: `docs/formal_document_alignment_frontend_cutover.md`
- Modify: `docs/adr/ADR-formal-document-alignment-workflow.md`
- Modify: `docs/architecture_map.md`
- Modify: `docs/technical_debt_register.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: implemented module, browser artifacts, prior formal API readiness checks.
- Produces: `FORMAL_WORKFLOW_FRONTEND_CUTOVER_ESTABLISHED` documentation and non-blocking declarations for retained legacy route, visual redesign, history, review workbench, and PostgreSQL.

- [ ] **Step 1: Add readiness checks for code, tests, and artifacts**

```python
checks["FORMAL_FRONTEND_CUTOVER_PRESENT"] = formal_module.exists()
checks["FORMAL_FRONTEND_START_USES_FORMAL_API"] = formal_start_present
checks["FORMAL_FRONTEND_LEGACY_ALIGNMENT_NOT_CALLED"] = legacy_call_absent
checks["FORMAL_FRONTEND_UI_E2E_VERIFIED"] = artifact_verdict(ui_artifact) == "PASS"
```

- [ ] **Step 2: Document the frozen UI state, polling, storage, errors, pagination, and non-goals**

The document must explicitly state `LEGACY_ALIGNMENT_ROUTE_STILL_PRESENT`, `FRONTEND_VISUAL_REDESIGN_NOT_COMPLETED`, `HISTORICAL_RUN_LIST_NOT_IMPLEMENTED`, `FULL_REVIEW_WORKBENCH_NOT_IMPLEMENTED`, and `POSTGRESQL_UI_FLOW_NOT_VERIFIED`.

- [ ] **Step 3: Run readiness-focused tests**

Run: `backend/.venv-macos/bin/python -m pytest $(rg -l 'pilot_readiness|FORMAL_FRONTEND_' tests | tr '\n' ' ') -q`

Expected: PASS with readiness still `READY_WITH_CONDITIONS` and `blocking_failures=[]` after artifacts exist.

### Task 6: Verification, Explicit Staging, and Commit

**Files:**
- Verify all task files only; do not modify unrelated files.

**Interfaces:**
- Consumes: complete Task 9C.5H implementation.
- Produces: commit `feat: cut over teacher workflow to formal API` with clean worktree and all required artifacts.

- [ ] **Step 1: Run targeted formal frontend/API/security/legacy tests**

Run: `backend/.venv-macos/bin/python -m pytest tests/test_formal_workflow_frontend_cutover_contract.py tests/test_formal_workflow_frontend_state_contract.py tests/test_formal_workflow_frontend_e2e_runner.py tests/test_formal_workflow_frontend_security.py tests/test_document_alignment_workflow_routes.py tests/test_document_alignment_formal_api_e2e.py tests/test_document_alignment_formal_api_security.py tests/test_permission_matrix.py tests/test_legacy_alignment_run_characterization.py tests/test_test_isolation.py -q`

Expected: PASS.

- [ ] **Step 2: Run full backend regression and safety commands**

Run: `backend/.venv-macos/bin/python -m pytest -q`

Expected: at least `1061 passed`.

Run: `backend/.venv-macos/bin/python scripts/check_release_safety.py`

Expected: PASS.

Run: `backend/.venv-macos/bin/python scripts/dev_check.py`

Expected: PASS.

Run: `backend/.venv-macos/bin/python scripts/migrate_db.py`

Expected: PASS with no schema changes.

- [ ] **Step 3: Generate formal UI artifacts**

Run: `backend/.venv-macos/bin/python scripts/run_formal_workflow_frontend_e2e.py --json-output /private/tmp/lexibridge-9c5h-formal-ui-e2e.json`

Run: `backend/.venv-macos/bin/python scripts/run_formal_workflow_frontend_resume_e2e.py --json-output /private/tmp/lexibridge-9c5h-resume-e2e.json`

Expected: both PASS, console/page/external/legacy/duplicate request counters all zero.

- [ ] **Step 4: Run existing browser/API regressions and readiness**

Run the existing Teacher E2E, Full E2E, Legacy Alignment E2E, Formal API E2E, and `scripts/pilot_readiness_check.py --json-output /private/tmp/lexibridge-9c5h-readiness.json` using their repository entrypoints.

Expected: every verdict PASS; readiness `READY_WITH_CONDITIONS`, `blocking_failures=[]`.

- [ ] **Step 5: Explicitly stage and inspect only task files**

```bash
git add docs/superpowers/plans/2026-07-20-formal-workflow-frontend-cutover.md frontend/index.html frontend/js/formal-workflow.js tests/test_formal_workflow_frontend_cutover_contract.py tests/test_formal_workflow_frontend_state_contract.py tests/test_formal_workflow_frontend_e2e_runner.py tests/test_formal_workflow_frontend_security.py scripts/run_formal_workflow_frontend_e2e.py scripts/run_formal_workflow_frontend_resume_e2e.py scripts/pilot_readiness_check.py docs/formal_document_alignment_frontend_cutover.md docs/adr/ADR-formal-document-alignment-workflow.md docs/architecture_map.md docs/technical_debt_register.md README.md tests/test_document_alignment_processing_boundary.py tests/test_formal_document_alignment_workflow_boundary.py tests/test_legacy_alignment_run_characterization.py tests/test_frontend_contract.py
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
```

- [ ] **Step 6: Commit and run post-commit gates**

```bash
git commit -m "feat: cut over teacher workflow to formal API"
git status --short
```

Expected: clean worktree. Re-run formal frontend tests, both formal UI E2Es, Full E2E, and readiness from the committed tree.
