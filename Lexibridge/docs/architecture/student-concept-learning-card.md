# Student Concept Learning Card

## Purpose

The concept learning card is the student-facing presentation of an existing
`StudentConceptQuery` / `AlignmentResult` and its existing
`PersonalLearningRecord`. It is a learning surface, not a second alignment
workflow and not a second persistence model.

```text
PDF.js text selection
  -> existing ConceptQuery
  -> existing retrieval / candidate / pairing / qualification chain
  -> existing Student AlignmentResult
  -> Concept Learning Card
  -> existing PersonalLearningRecord
```

The card never changes retrieval, pairing, qualification, readiness, Prompt,
Provider or evidence provenance.

## Progressive card contract

The first view is deliberately small:

- English concept and bounded course context;
- a student-facing explanation of `READY`, `REVIEW_REQUIRED` or `NOT_READY`;
- the existing `PRIVATE / NON_OFFICIAL` content boundary;
- the selected or possible Chinese concept, without claiming official status.

The student can then explicitly open:

1. evidence and candidate comparison;
2. a bounded “why they align” explanation;
3. personal notes and understanding state.

Evidence, alternatives, risk labels and provenance remain the existing bounded
fields from `AlignmentResult`; the UI does not reconstruct or invent them.

## Student status language

| Machine status | Student-facing label | Behaviour |
| --- | --- | --- |
| `READY` | 证据充分 | show the evidence-backed recommendation |
| `REVIEW_REQUIRED` | 存在多个有证据的候选 | show bounded alternatives and uncertainty |
| `NOT_READY` | 暂无可靠中文对应 | do not fabricate a canonical Chinese term |

The raw machine status remains available as a non-prominent data attribute for
tests and diagnostics, but is not used as the main student heading.

## Learning interactions

- Save/unsave, note, `UNDERSTOOD` and `STILL_CONFUSED` continue to use the
  existing personal-record API and optimistic/idempotent mutation contract.
- “Start review” is ephemeral UI state. It does not create a new domain object
  or a second card table.
- Review mode hides the Chinese answer until the student explicitly reveals it;
  evidence is not exposed as a substitute answer while it is hidden.
- Reopening a saved notebook item enters review mode. A new query or material
  selection clears the previous card before the new result is requested, so a
  stale result cannot be mistaken for the current selection.

## Safety and privacy

The card remains a private, non-official result in both `PERSONAL` and
`MANAGED_COURSE` workspaces. It does not expose Prompt text, Provider details,
credentials, raw payloads, other students' data or complete source material.
Generated translation hints remain visibly separate from evidence-backed
Chinese candidates.

## Known limits

This is an offline/synthetic interaction baseline. It does not establish real
student learning effectiveness, broad PDF quality, or production deployment
readiness. Those require the next ordered multi-student controlled pilot.
