# Personal Concept Notebook and Learning Loop

## Scope

Task 13C.4 turns the existing per-result `PersonalLearningRecord` into one
student-facing notebook. It introduces no second alignment/card state machine,
no Provider call and no new database table. Published `ConceptAlignmentCard`
learning state remains an independent official-course path.

## Before and after

Before:

```text
Student ConceptQuery
  -> one private AlignmentResult
  -> per-result save / note / understanding update
```

There was no aggregate private notebook. The older “Favorites & Learning” page
read `TerminologyCard` data and therefore could not represent private,
non-official machine results.

After:

```text
Personal or Managed Course ConceptQuery
  -> existing StudentConceptQuery
  -> existing PersonalLearningRecord
  -> personal-concept-notebook@1.0.0 read model
  -> search / workspace / alignment / learning-state filters
  -> bounded detail and explicit revisit
  -> existing result editor for save, note and understanding state
```

## Contract

Routes are Student-only:

- `GET /api/student/personal-concept-notebook`
- `GET /api/student/personal-concept-notebook/<query_uid>`
- `POST /api/student/personal-concept-notebook/<query_uid>/revisit`
- existing `GET/PUT /api/student/concept-queries/<query_uid>/personal-record`

The default notebook view is `SAVED`; `HISTORY`, `UNDERSTOOD` and
`STILL_CONFUSED` are explicit views. Results can be filtered by `PERSONAL` or
`MANAGED_COURSE`, by the frozen machine alignment status, and by a bounded
search over the student’s own English concept, recommended Chinese concept,
source/course label and private note. Pagination is bounded to 50 rows.

List rows omit full evidence and full notes. They include a 240-character note
preview, evidence/source availability and fixed content dimensions. Detail
reuses the existing bounded Student AlignmentResult serializer.

## Reuse and persistence

- `StudentConceptQuery` remains the immutable private query/result aggregate.
- `PersonalLearningRecord` remains the only writable private learning state.
- `KnowledgeSource` is used only to report source title and current
  availability.
- `CourseMember` is checked on every Managed Course list/detail/revisit.
- `AuditRecord` stores identifiers, action and a mutation fingerprint; note
  bodies are never copied into audit payloads.

No migration is needed. `last_viewed_at` and optimistic `version` already
express the required revisit loop. Query history is read from the existing
student-owned query aggregate; saving, notes and learning status continue to
write only one `PersonalLearningRecord` per student/result.

## Privacy and authority

Every notebook item is fixed to:

```text
visibility = PRIVATE
authority = NON_OFFICIAL
publication_status = NOT_APPLICABLE
```

Another Student sees only an empty own notebook and receives not-found for a
foreign detail. Instructor, Reviewer and Admin cannot use these Student routes.
Managed Course membership revocation removes that result from subsequent
student reads. Personal material deletion does not erase historical learning;
the result remains visible with `SOURCE_UNAVAILABLE` and unavailable evidence.

Notebook operations never enqueue Reviewer work and cannot publish content.

## Idempotency

State mutations keep optimistic version checks. When an `Idempotency-Key` is
provided, the first mutation stores only an HMAC-SHA-256 mutation fingerprint in its
audit record. A repeat with the same key and semantic payload replays the
current result; a different payload using the same key fails closed. Revisit
requires an idempotency key and uses the same contract.

## Frontend

Student navigation now contains “个人概念本 / My Concept Notebook”. Personal
and Managed Course records share one page, filters and the existing Student
Concept Result component. Students can revisit evidence, save/unsave, edit a
private note and mark `UNDERSTOOD` or `STILL_CONFUSED`. Source-unavailable
history is clearly labelled and never presented as revalidated evidence.

This is a synthetic/local engineering baseline. Real student usefulness is a
later roadmap gate.
