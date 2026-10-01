# Task 12J-B — Teacher Alignment Review Vertical Slice

## Executive conclusion

Technical status: `TEACHER_ALIGNMENT_REVIEW_VERTICAL_SLICE_CLOSED`

Quality status: `TEACHER_ALIGNMENT_REVIEW_BASELINE_ESTABLISHED`

LexiBridge now has one teacher-facing vertical path from an existing
production alignment recommendation to a persisted human decision, governed
readiness re-evaluation, deterministic fake-Provider draft generation, and
teacher draft editing. The path does not publish a card, call a real Provider,
or alter any retrieval, term-identification, pairing, reranking,
qualification, Prompt, or Provider-transport contract.

## Existing objects reused

- `DocumentAlignmentWorkflowRun` and `DocumentAlignmentWorkflowItem` remain
  the Formal run/item identities.
- `ConceptAlignmentCard` remains the alignment read model and unpublished
  draft record. No parallel card or draft table was added.
- `ConceptCardReviewRecord` persists human decisions, machine recommendation
  snapshots, selected candidate identity, reviewer, rationale, time, request
  identity, and before/after status.
- Existing `AuditRecord`, course review policy/permission, optimistic card
  version, provider readiness, provider execution, and deterministic fake
  transport abstractions are reused.
- Existing student Concept Card routes remain the publication boundary.

No schema or migration was added.

## Production call graph

Before:

`Formal item → ConceptAlignmentCard → generic review queue/detail → legacy
approve/reject/revision actions → publication-oriented card state`

The old teacher page could inspect evidence and record legacy reviews, but it
did not expose the production bounded Chinese candidate pool, did not persist
accept-vs-alternative-vs-defer semantics, and had no governed human-approval
adapter into readiness and draft execution.

After:

`Formal item → existing ConceptAlignmentCard → unified teacher review case →
accept/select/reject/defer → ConceptCardReviewRecord + AuditRecord → human
approval readiness adapter → existing provider execution admission →
DeterministicFakeProviderTransport → existing parser → unpublished
ConceptAlignmentCard draft → teacher edit + AuditRecord`

Machine state and human state are returned separately. An alternative
selection updates the effective draft term but preserves the original machine
candidate in the review snapshot.

## Read and command contracts

The unified read model exposes bounded English evidence and Chinese candidate
evidence with source, chunk, page, parse block, span, extraction rank,
retrieval rank, machine decisions, risks/reasons, policy/model versions, human
review state, and draft/publication state. Evidence snippets are capped at 600
characters and the candidate pool at 20 candidates.

The teacher commands are:

- `ACCEPT_RECOMMENDATION`
- `SELECT_ALTERNATIVE_CANDIDATE`
- `REJECT_ALIGNMENT`
- `DEFER_REVIEW`

Alternative selection is limited to the existing bounded, evidence-backed
candidate pool. Generated translation hints, candidates without governed
source/chunk/block provenance, and arbitrary submitted term strings are not
eligible. Fatal upstream/provenance/source-governance states cannot be
approved through either the new commands or the legacy `approve` action.

Every write requires a teacher/admin identity, course permission, an expected
version, and audit context. Review and draft generation use idempotency keys.
A stale expected version returns a conflict and repeated draft generation
with the same key returns the original result rather than creating a second
draft.

## State contract

Machine state is preserved independently from human review state:

- machine: `READY`, `REVIEW_REQUIRED`, or `NOT_READY` (existing producer
  terminology is retained when present);
- human: `UNREVIEWED`, `ACCEPTED`, `ALTERNATIVE_SELECTED`, `REJECTED`, or
  `DEFERRED`;
- business: `REVIEW_REQUIRED`, `HUMAN_APPROVED`, `HUMAN_REJECTED`,
  `DEFERRED`, or `DRAFT_GENERATED`.

Human approval does not mutate the original machine recommendation to
`READY`, and it does not publish the card.

## Governed readiness after human approval

Only semantic/ranking uncertainty may be resolved by a human decision. The
adapter rechecks bilingual evidence references, parse-block provenance, source
governance, privacy classification, bounded budget, fixed Prompt registry
identity, fake Provider configuration, audit context, and idempotency.

The readiness audit records:

- `approval_source=HUMAN_REVIEW`;
- the approving review UID;
- active qualification policy
  `governed-bilingual-evidence-qualification@1.1.0`;
- readiness policy `governed-provider-readiness@1.0.0`.

Fatal upstream state, missing provenance, or an absent generated-draft audit
record blocks editing/execution.

## Draft generation and publication boundary

The vertical slice uses the existing provider execution request and parser
with `DeterministicFakeProviderTransport`. A draft is generated only after
readiness returns `READY`, is bound to the alignment case and approving review
decision, retains bilingual evidence references, and remains
`NOT_PUBLISHED`.

Teacher edits use the existing card update/audit mechanism, preserving the
machine draft and teacher changes in audit before/after snapshots. Repeated
generation does not create another draft. No real credential is read and no
Provider/network request is issued.

Students receive 403 for review-case, review command, draft, and unpublished
generic card reads. The existing student route continues to expose only
approved, publishable cards.

## Routes

Existing routes retained:

- `GET /api/concept-cards/review-queue`
- `GET /api/concept-cards/<card_uid>/reviews`
- `POST /api/concept-cards/<card_uid>/review`

New governed capabilities in the same namespace:

- `GET /api/concept-cards/<card_uid>/review-case`
- `POST /api/concept-cards/<card_uid>/generate-draft`
- `GET /api/concept-cards/<card_uid>/draft`
- `PUT /api/concept-cards/<card_uid>/draft`

The review queue supports machine status, human review status, course, risk,
and updated-time filtering.

## Teacher page and browser validation

The existing Concept Card teacher review page was extended rather than
duplicated. It displays:

- review list, status, risks, and evidence counts;
- two-sided bounded evidence and page/block provenance;
- production Chinese candidate pool with extraction/retrieval ranks;
- machine recommendation, risk labels, and reason codes;
- accept, select alternative, reject, and defer controls;
- governed fake draft generation and a draft editor;
- loading, empty, error, permission, stale-version, and success feedback.

The local Chromium flow passed:

`login → list → course filter → detail → bilingual evidence → accept
recommendation → HUMAN_APPROVED → readiness READY → fake draft → edit/save →
NOT_PUBLISHED`

It also retained existing review history, teacher analytics, feedback, and
policy-block checks. Console errors, page errors, unexpected failed requests,
and external dependency requests were all zero.

## Safety and regression result

- external API used: `false`
- real Provider requests: `0`
- real credentials read: `false`
- private course material used: `false`
- Prompt changed: `false`
- Provider transport changed: `false`
- upstream retrieval/identification/pairing/qualification changed: `false`
- automatic publication: `false`

Validation:

- targeted teacher/card/readiness/execution/browser contracts:
  `69 passed`;
- full pytest: `1579 passed, 1 skipped`;
- `scripts/dev_check.py`: passed, including its independent full pytest and
  backend API smoke;
- `scripts/check_release_safety.py`: passed;
- real Chromium teacher flow: passed;
- `git diff --check`: passed.

Sanitized artifact hashes:

- `12JB-review-case-contract.json`:
  `b354337321c0e23cc4130cb01e656e5282ba10f115156a7228329912dae69bc8`
- `12JB-review-command-matrix.csv`:
  `b7d7eb781de02b1345dd517cbb96f7d47d60cf9c0b6fd961d04063a6ec5a9079`
- `12JB-browser-e2e-result.json`:
  `7c3065bfb3fc97778d0b2d1059595b1c35f1d9175af15245848985cd6ba8cb4a`

Accident database before/final:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: absent/absent

Frozen Cross-Corpus V2 hashes:

- English:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

## Recommendation

Stop at the teacher draft boundary. The next separately authorized product
slice may address governed publication and the student-visible learning
experience. It should not be combined with real Provider batching, Prompt
optimization, or a student chatbot.
