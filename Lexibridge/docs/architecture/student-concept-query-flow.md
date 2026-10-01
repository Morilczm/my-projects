# Student ConceptQuery Flow

## Scope

Task 13B adds one student-owned concept-learning vertical slice. It composes the
existing Task 12 bilingual evidence workflow; it does not search published cards,
create a student-only retrieval engine, or call an LLM Provider.

## Production flow

```text
authorized English KnowledgeSource / KnowledgeChunk
  -> server-side selection and span validation
  -> bounded context reconstruction
  -> workspace Evidence Scope Resolver
  -> bilingual_evidence_workflow.retrieve_bilingual_evidence
  -> existing multilingual retrieval / Chinese candidates / pairing / reranking
  -> evidence qualification 1.1.0
  -> student alignment-result serializer
  -> private PersonalLearningRecord
```

Before Task 13B, the student UI could only read published
`ConceptAlignmentCard` objects. After Task 13B, published cards remain an
independent course-content path while `/api/student/concept-queries` creates a
real, private machine result from a validated source selection.

## ConceptQuery

`StudentConceptQuery` is the minimal private query aggregate. It records owner,
workspace, source version, selected span, a stable fingerprint, evidence-scope
identity, sanitized machine-result JSON, and processing state.

The server accepts only workspace/source/chunk and selection coordinates. It
re-reads the governed chunk and rejects empty, punctuation-only, numeric,
overlong, out-of-range, or text-mismatched selections. The bounded context is
reconstructed on the server and capped at 800 characters.

The fingerprint covers student, workspace, source/version, chunk/span,
normalized selection, and qualification policy version. A repeat against the
same source version reuses the existing query. A source or policy version change
permits a new result.

## Evidence Scope Resolver

The resolver returns an immutable, sorted allow-list of Chinese source UIDs:

- Personal: the student’s governed private Chinese sources; optional governed
  platform sources only when an explicit application policy enables them.
- Managed Course: governed Chinese sources owned by the current course; optional
  platform sources only when that same explicit policy enables them.

It excludes another student’s private sources, other courses, inactive sources,
unlicensed/unauthorized sources, and sources not enabled for student search.
The allow-list is passed into the existing Task 12 retrieval functions as
`source_uids`; both lexical and multilingual paths enforce it.

The English evidence lookup receives a separate `english_source_uid`, so the
selected English source remains bound while Chinese retrieval uses the workspace
allow-list.

An empty Chinese allow-list is not treated as an unrestricted search. The
student adapter stops before retrieval and returns a fail-closed `NOT_READY`
result with a stable evidence-unavailable reason.

## AlignmentResult

The student read model maps qualification decisions without changing thresholds:

- `QUALIFIED` -> `READY` / `EVIDENCE_BACKED_RECOMMENDATION`
- `REVIEW_REQUIRED` -> `REVIEW_REQUIRED` /
  `EVIDENCE_BACKED_ALTERNATIVES`
- rejected, missing, unknown, or execution failure -> `NOT_READY` /
  `NO_RELIABLE_ALIGNMENT`

Every result is `PRIVATE`, `NON_OFFICIAL`, and `NOT_APPLICABLE` for publication.
`NOT_READY` never exposes a canonical Chinese term. Generated hints remain
non-evidence, non-official hints. The DTO bounds evidence snippets and omits
Provider, Prompt, cost, credential, raw payload, raw scoring/reason codes, and
Reviewer internals. Stable machine reasons are translated into bounded
student-facing explanations.

## PersonalLearningRecord

The existing `StudentConceptCardState` is intentionally not reused: it is bound
to an approved/published `card_uid`. Reusing it would make an unpublished
machine result look like a published course card.

`PersonalLearningRecord` is therefore the second and final minimal Task 13B
table. It has one owner and one result, supports save/unsave, note,
`UNDERSTOOD`/`STILL_CONFUSED`/clear state, last viewed time, and optimistic
versioning. It has no authority/publication fields because the service contract
fixes them to private, non-official, non-publishable semantics.

Audits record identifiers, action and status; note/source/evidence bodies are
not copied into audit payloads.

## Access control

- Personal materials and results require exact student ownership.
- Managed Course materials and results require an active `CourseMember` on every
  read, not only at query creation.
- Other students receive not-found semantics.
- Instructor, Reviewer, and Admin cannot use the student-owned routes.
- Membership revocation removes subsequent access to course snippets and
  evidence while retaining the internal row for audit.

## Frontend

Personal and Managed Course sources use one `Concept Query` page, one selection
handler, one result component and one personal-state editor. Workspace labels
change source context only. READY, REVIEW_REQUIRED and NOT_READY share the same
result contract and never require Instructor or Reviewer approval.

## No-Provider fallback

The route calls the evidence/alignment chain directly. Provider execution is not
part of query success. If local alignment execution is unavailable, the result
fails closed as NOT_READY while retaining the validated English selection and
bounded English evidence. Unit tests may inject a complete Task 12 result at
the explicit server-side test seam. The main Browser E2E instead runs the
production retrieval/candidate/pairing/qualification orchestration with
deterministic fixed-contract model-scoring backends; it does not replace the
alignment runner. Both modes issue zero Provider or external application
requests.

## Migration decision

Two narrow tables were added with existing SQLAlchemy/create-all migration
conventions:

1. `student_concept_query`
2. `personal_learning_record`

No Workspace, AlignmentResult, OfficialCourseCard, retrieval, review, or
publication aggregate/table was added. Existing `KnowledgeSource`,
`KnowledgeChunk`, `CourseMember`, Task 12 services and `AuditRecord` are reused.
