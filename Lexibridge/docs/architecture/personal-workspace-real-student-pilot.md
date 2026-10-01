# Personal Workspace Real-student Pilot Contract

## Purpose

This contract adds privacy-safe measurement around the existing Student-first
Personal Workspace flow. It does not create a second product, alignment chain,
learning-record path, telemetry provider, or Reviewer workflow.

## Before and after

```text
before
Student -> PersonalMaterial -> StudentConceptQuery -> AlignmentResult
        -> PersonalLearningRecord

after
optional explicit consent -> StudentPilotSession STARTED
Student -> the unchanged PersonalMaterial / StudentConceptQuery / AlignmentResult
        -> the unchanged PersonalLearningRecord
        -> server-derived content-free session metrics -> bounded survey
        -> small-cell-suppressed Admin aggregate
```

Normal product use never depends on enrollment. Managed Course results cannot
complete this Personal Workspace pilot.

## Reused product objects

- `StudentConceptQuery`: validates ownership and provides the completed machine
  status. Its UID is hashed and not stored in the pilot table.
- `PersonalLearningRecord`: provides derived save, note-present and
  understanding-state fields. Note content is never copied.
- `AuditRecord`: records consent/session state transitions without source,
  term, evidence, query UID, note or survey comment.
- the existing Personal Workspace UI and Browser E2E flow.

## New study-only objects

### StudentPilotEnrollment

One record per Student and pilot version. It stores explicit consent status,
consent version, eligibility attestation, idempotency references and timestamps.

### StudentPilotSession

One task attempt. It stores only derived state, bounded duration, a one-way
query reference hash and idempotency/version fields. It has no `query_uid`,
term, source, evidence, note or comment column.

### StudentPilotSurvey

Four bounded 1–5 ratings, a reuse-intent boolean and one optional 500-character
student-owned comment. The comment is excluded from serializers, audit and
admin aggregates.

All three tables are created through the existing `db.create_all()` migration
path. No existing product table or frozen pipeline schema is changed.

## API and authorization

Student-only:

- `GET /api/student/pilot`
- `POST|DELETE /api/student/pilot/enrollment`
- `POST /api/student/pilot/sessions`
- `PUT /api/student/pilot/sessions/{session_uid}/complete`
- `PUT /api/student/pilot/sessions/{session_uid}/survey`

Admin-only aggregate:

- `GET /api/admin/student-pilot/aggregate`

Instructor and Reviewer are denied. The feature flag defaults to false. All
writes require an idempotency key; completion also requires an expected
version. The server, not the client, derives metrics from an owned, completed,
`PERSONAL` query.

## Privacy and withdrawal

The aggregate returns no individual row or identifier and suppresses metrics
until at least three completed sessions exist. Withdrawal erases the Student's
pilot sessions and surveys while preserving normal product data. This keeps
research participation independent from the student's learning materials and
records.

## Validation boundary

Synthetic tests and Browser E2E prove only that the contract and UI operate
deterministically without external requests. Product quality remains
unvalidated until real, consenting students complete the separate pilot run.
The test runtime sets `LEXIBRIDGE_SKIP_ENV_FILE=true` and explicit empty
credential variables before importing the backend, so local developer secrets
are not consumed by automated validation.
