# Formal Document Alignment API End-to-End Evidence

Status: `FORMAL_DOCUMENT_ALIGNMENT_API_END_TO_END_VERIFIED`

Scope: Task 9C.5G v3 verifies the formal API on an isolated SQLite file,
single local process, threaded loopback Flask server, local worker iteration,
and deterministic `mock-rule-v1` provider. It does not verify frontend cutover,
PostgreSQL, distributed workers, external providers, provider exactly-once, or
production deployment.

## Verified Boundary

The main scenario begins with authenticated HTTP and does not create or repair
the Run or Job through ORM test setup:

```text
POST /api/document-alignment-runs
-> Admission freezes workflow/provider/retry defaults
-> BackgroundJob atomic claim
-> formal worker handler
-> processing orchestrator
-> per-item preparation and verification
-> Root/Job finalization
-> GET Run polling
-> GET paginated Items
```

The production-default gate verifies `formal-document-alignment-v1` as the
workflow version and `formal_document_alignment_workflow_v1` as the distinct
transport job type. Admission freezes `mock-rule-v1`, `mock-rule-v1:v1`,
`alignment-v1`, and `max_attempts=3`. The job payload contains only
`workflow_run_uid` and `workflow_version`.

## Scenario Coverage

- Normal flow reaches `ready_for_review`; all items reach `needs_review`; the
  BackgroundJob reaches `completed`.
- Polling accepts fast completion, stops at terminal state, applies a timeout,
  and rejects status regression.
- Source-scoped idempotent replay returns the same Run and does not duplicate
  Run, Job, or admission AuditRecord. The same key on another source creates a
  separate Run. Canonical drift in the same scope returns `409`.
- Five threaded rounds use two independent HTTP clients/connections and a
  synchronization barrier; each round produces one logical Run and Job.
- A 25-item Run verifies database pagination, stable order, page bounds, and
  invalid filter handling through HTTP.
- Partial business failure reaches `completed_with_warnings`; all-blocked
  evidence/candidate outcomes reach Root `blocked` while Job remains
  `completed`.
- Retryable interruption requeues an HTTP-created Job and resumes on the next
  claim. Claim crash/stale reclaim, partial checkpoint resume, terminal-Root
  recovery, and retry exhaustion are exercised through formal public worker
  and ownership boundaries. Each recovery scenario finishes with authenticated
  HTTP `GET` requests for the Run and Items, so the artifact records the
  externally serialized terminal state rather than only inspecting ORM state.
- Requester, admin, authorized course teacher, unrelated teacher, student, and
  anonymous outcomes are exercised. The unrelated teacher receives the frozen
  anti-enumerating response; students cannot start or query a formal workflow.
- Browser evidence uses the real login page and same-origin `fetch` for POST,
  a bounded monotonic status timeline, item query, and student denial. Fast
  completion is valid, so the observed timeline may move directly from
  `queued` to a terminal status. It is API evidence, not frontend workflow UI
  evidence.

## Safety Evidence

The harness rejects Python-side and browser-page external network access while
allowing loopback HTTP. Blocked attempts remain counted even when a scenario
fails, while failure artifacts use fixed safe messages rather than raw
exceptions.
Responses and artifacts are recursively checked for transport ownership,
execution identity, evidence body, prompt, provider output, credentials,
database integer IDs, absolute paths, and the task sentinel. Artifacts record
zero external dependency requests. Legacy AlignmentRun and TerminologyCard
writes are checked in the normal formal flow.

## Artifacts

- `/private/tmp/lexibridge-9c5g-v3-api-e2e.json`
- `/private/tmp/lexibridge-9c5g-v3-browser-api-e2e.json`
- `/private/tmp/lexibridge-9c5g-v3-recovery.json`
- `/private/tmp/lexibridge-9c5g-v3-readiness.json`

Artifacts contain verdicts, safe Run UIDs, state timelines, item counts,
permission outcomes, recovery outcomes, timeout status, browser errors, and
external request counts. They intentionally exclude tokens, payload bodies,
evidence, prompts, provider output, credentials, and private paths.

## Remaining Limits

The proof does not establish SQLite behavior under multi-process load or any
PostgreSQL locking, isolation, uniqueness, or transaction semantics. The local
worker is not a supervised production daemon, and uncounted pre-outcome crash
generations have no separate persisted loop cap. The deterministic provider is
not semantic validation of a live model. The current frontend still calls the
contained legacy endpoint, so Task 9C.5H must perform the cutover before the
formal workflow becomes the teacher-facing document-alignment experience.
