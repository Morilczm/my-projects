# Workspace, Role, and Content Boundaries

Contract: `student-first-boundaries@1.0.0`

## Workspace model

`PERSONAL` and `MANAGED_COURSE` are scopes around the same alignment engine. They change ownership, governance, authorization, course context, analytics availability, and official-publication availability. They do not select a different parser, retrieval model, pairing pipeline, result page, or notebook.

Task 13A deliberately introduces no database table. A student’s personal scope can currently be represented by existing `owner_user_id/scope_type/visibility` metadata; managed scope uses `Course`, `CourseMember`, course-scoped sources, and visibility policies. Durable Workspace identity and PersonalLearningRecord persistence remain migration gaps for 13B/13C.

## Independent result dimensions

The production contract lives in `backend/services/student_first_boundaries.py`.

| Dimension | Values |
|---|---|
| workspace_scope | PERSONAL, MANAGED_COURSE |
| visibility | PRIVATE, COURSE_SHARED |
| authority | NON_OFFICIAL, OFFICIAL |
| alignment_status | READY, REVIEW_REQUIRED, NOT_READY |
| publication_status | NOT_APPLICABLE, DRAFT, PUBLISHED, WITHDRAWN |

`AlignmentResult` and `PersonalLearningRecord` use private/non-official/not-applicable defaults. Official cards require a managed course, course-shared visibility, an official authority marker, a publication state, and a Reviewer/Admin decision reference.

### Legal combinations

- Personal query: `PERSONAL + PRIVATE + NON_OFFICIAL + any alignment status + NOT_APPLICABLE`.
- Managed student query: `MANAGED_COURSE + PRIVATE + NON_OFFICIAL + any alignment status + NOT_APPLICABLE`.
- Official card: `MANAGED_COURSE + COURSE_SHARED + OFFICIAL + DRAFT/PUBLISHED/WITHDRAWN`, with Reviewer decision.

### Rejected combinations

- Personal + official or course-shared.
- Personal learning result + any publication state.
- Non-official + published/withdrawn.
- Student/Instructor establishing official content.
- Official card without Reviewer decision.
- Generated hint as evidence or official content.

## Student status serialization

The same serializer is used for both workspace scopes:

- READY → `EVIDENCE_BACKED_RECOMMENDATION`.
- REVIEW_REQUIRED → `EVIDENCE_BACKED_ALTERNATIVES`, uncertain, still viewable.
- NOT_READY → `NO_RELIABLE_ALIGNMENT`, with no canonical Chinese term.

Only bounded source/chunk/span evidence and evidence-backed candidates are returned. Prompt text, secrets, raw JSON, and low-level scoring internals are omitted. Generated hints require `generated=true`, `no_evidence=true`, `provenance_type=GENERATED_HINT`; the serializer emits `evidence_backed=false` and `authority=NON_OFFICIAL`.

## Role capability matrix

| Capability | Student | Instructor | Reviewer | Admin |
|---|---:|---:|---:|---:|
| Personal/managed student query | yes | no daily duty | no daily duty | governance only |
| Manage English course context | no | yes | no | compatible |
| Review bilingual exceptions | no | no | yes | compatible |
| Review official course card | no | no | yes | compatible |
| Provider/policy administration | no | no | no | yes |
| View private notes/queries of other students | no | no | no | not granted by this contract |

`teacher` route access to the legacy review endpoints is retained as **transitional compatibility**, because existing course permissions and tests encode it. It is removed from Instructor navigation. A later migration can narrow backend access after institutions have assigned dedicated Reviewer accounts.

## Reused domain objects

| Object | Reused responsibility | Boundary |
|---|---|---|
| DocumentAlignmentWorkflowRun/Item | formal machine workflow and recommendation | not student notes or publication authority |
| ConceptAlignmentCard | existing alignment/draft/publication carrier | five-dimensional view is supplied by service DTO, not a new card table |
| ConceptCardReviewRecord | immutable human decision/audit trail | Reviewer exception/official flow only |
| Course/CourseMember | managed course and membership | does not imply official result |
| StudentConceptCardState | existing published-card learning state | not yet general PersonalLearningRecord |
| AuditRecord | route/decision audit | no full private source |
| TerminologyCard | legacy compatibility | do not extend as new product model |

## PersonalLearningRecord vs OfficialCourseCard

Both reference an AlignmentResult; neither overwrites it. A PersonalLearningRecord belongs to one student, remains private/non-official, needs no review, and is not publishable. An OfficialCourseCard is managed-course-only, reviewer-governed, course-shared, versioned, and independently publishable/withdrawable.

Task 13A supplies `personal_learning_record_contract()` only. Durable personal-record storage is intentionally deferred.

## Navigation and route compatibility

- Instructor navigation is English and contains course, English material, run coverage, QC, and aggregate-signal entries; no Chinese candidate review entry.
- Reviewer navigation exposes the existing `conceptReview` page as “Reviewer Console”.
- Existing `/api/concept-cards/.../review*` routes are reused. Reviewer is admitted subject to `CourseReviewPermission`.
- Student remains blocked from review routes and unpublished drafts.
- Admin behavior is retained.

Internal names such as `teacher_alignment_review.py` remain compatibility names; renaming them without a migration adds no product safety and risks breaking imports.

## Migration gaps

1. Durable Workspace and workspace membership abstraction spanning personal/managed scopes.
2. General AlignmentResult persistence independent from existing card publication fields.
3. Full PersonalLearningRecord table and notebook lifecycle.
4. Dedicated OfficialCourseCard publication aggregate rather than status projections on ConceptAlignmentCard.
5. Removal of transitional teacher review permission after Reviewer accounts/permissions are migrated.
6. Reviewer-specific student feedback queue authorization.

These are explicit follow-on migrations, not reasons to create parallel Task 13A workflows.

