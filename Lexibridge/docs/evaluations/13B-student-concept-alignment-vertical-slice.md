# Task 13B — Shared Student One-Concept Alignment Vertical Slice

## Executive conclusion

Technical status: `STUDENT_CONCEPT_ALIGNMENT_VERTICAL_SLICE_CLOSED`

Quality status: `STUDENT_CONCEPT_ALIGNMENT_BASELINE_ESTABLISHED`

Baseline main commit: `1720aa1d76dba6e5508e5405ea924eacfd33b42f`.

This is a synthetic/local engineering baseline, not a real-student product
validation. It does not start Task 13C, call a real Provider, or create a second
alignment pipeline.

## Production before / after

Before:

`Student → published ConceptAlignmentCard → StudentConceptCardState`

Students could read governed published cards, but could not create a private
machine AlignmentResult from a selected concept in an authorized English
material.

After:

`Personal or Managed English KnowledgeChunk → server-validated selection/span → bounded context → workspace Chinese-source allow-list → existing Task 12 bilingual evidence workflow → qualification 1.1.0 → shared Student serializer → private AlignmentResult → PersonalLearningRecord`

The published-card path remains independent and unchanged.

## Reused objects and migration decision

The slice reuses `KnowledgeSource`, `KnowledgeChunk`, `Course`,
`CourseMember`, Task 12 multilingual retrieval/candidate/pairing/qualification,
Task 13A result dimensions, `AuditRecord`, and the existing Student shell.

`StudentConceptCardState` was not reused for private results because it is bound
to an approved/published `card_uid`. Two narrow tables were therefore added:

- `student_concept_query`: owner, workspace/source version, selected span,
  idempotent fingerprint, evidence-scope identity and sanitized machine result.
- `personal_learning_record`: one Student/result, save state, private note,
  understanding state, last-viewed time and optimistic version.

No Workspace, retrieval, review, Provider, official-card, or parallel
AlignmentResult table/workflow was added.

## Contracts

`student-concept-query@1.0.0` accepts only workspace/source/chunk identity and a
bounded selection. The server re-reads the chunk, validates exact offsets,
reconstructs at most 800 characters of context, verifies personal ownership or
active course membership, and derives a stable source/policy-versioned
fingerprint.

`student-alignment-result@1.1.0` maps the unchanged qualification decision:

- `QUALIFIED` → `READY` / `EVIDENCE_BACKED_RECOMMENDATION`
- `REVIEW_REQUIRED` → `REVIEW_REQUIRED` /
  `EVIDENCE_BACKED_ALTERNATIVES`
- rejected, missing, unknown or failed → `NOT_READY` /
  `NO_RELIABLE_ALIGNMENT`

Every ordinary query is `PRIVATE + NON_OFFICIAL + NOT_APPLICABLE`.
`NOT_READY` has no canonical Chinese term. Generated hints remain marked
non-evidence. Raw scoring components, raw reason codes, Prompt/Provider data and
Reviewer internals are omitted and replaced by bounded student-facing
explanations.

`personal-learning-record@1.0.0` supports save/unsave, note,
understood/still-confused/clear and GET state. Writes require the owning Student,
an expected version, and produce a body-free audit record.

## Shared Personal / Managed Course proof

Both scopes use the same routes, service adapter, Task 12 workflow, serializer,
frontend component and personal-record service. Workspace scope changes only
source ownership/governance and course membership.

Personal evidence is restricted to the owner’s governed Chinese sources.
Managed Course evidence is restricted to governed Chinese sources from that
course. Optional platform evidence requires an explicit policy flag. Other
students, other courses, inactive/unlicensed sources and sources not enabled for
student search are excluded. An empty allow-list fails closed before retrieval;
it never becomes an unrestricted search.

## Student experience and privacy

The shared Concept Query page supports selecting a real DOM span from an
authorized English chunk, loading, result, evidence, alternatives,
uncertainty, save, note and understanding state. It includes English Concept,
What It Means Here, Why They Align, English/Chinese Evidence, Alternatives,
Do Not Confuse With and Confidence/Uncertainty.

Personal and Managed Course results stay private/non-official. Managed Course
membership is rechecked on every read. Other Students receive not-found
semantics. Instructor, Reviewer and Admin cannot use Student-owned query/state
routes; ordinary Student queries and notes do not enter Reviewer Console.

## No-Provider fallback

Provider execution is not part of query success. The core concept, candidates
and bounded evidence come from the existing local governed chain. If that chain
cannot run, the adapter preserves the validated English context and fails
closed as `NOT_READY`. Automated tests and Browser E2E use deterministic fake
alignment output; application external requests and real Provider requests are
zero.

## Synthetic baseline

- ConceptQuery API samples: 5/5 succeeded with deterministic Task 12-compatible
  fake alignment.
- Local total request time: median 2.973 ms; max 9.871 ms.
- Selection validation microbenchmark: median 0.002667 ms.
- Evidence-scope resolution microbenchmark: median 0.003166 ms.
- Serialization microbenchmark: median 0.016209 ms.
- Personal and Managed Course Browser flows: PASS.
- READY / REVIEW_REQUIRED / NOT_READY serializer cases: PASS.
- Evidence provenance and bounded-snippet contract: PASS.
- Duplicate query/save idempotency and stale-version conflict: PASS.
- Cross-student, Instructor, Reviewer and Admin access denial: PASS.

These values are synthetic integration measurements and are not production
latency or student-value claims.

## Safety and frozen upstream

Parsing, chunking, embedding model, retrieval scoring, Chinese candidate
generation, pairing/reranker, qualification/readiness thresholds, Prompt,
Provider transport and frozen V2 inputs were not changed. The only retrieval
extension is a governed source-UID allow-list used to enforce Workspace data
isolation; the existing algorithms and model remain unchanged.

Application external API used: false.

Real Provider requests: 0.

Real credentials read: false.

The accident database was not used by tests and is verified before/final in the
task handoff.

## Verification

- Targeted Student/workspace/retrieval/Reviewer/publication regression:
  71 passed.
- Full pytest: 1621 passed, 5 skipped, 56 warnings.
- Browser E2E: Student PASS (34 steps), Instructor PASS (7 steps), Reviewer
  PASS (15 steps); external dependency requests 0.
- `scripts/dev_check.py`: passed, including its independent full pytest,
  migration and backend smoke.
- `scripts/check_release_safety.py`: passed.
- `git diff --check`: passed.

Frozen Cross-Corpus V2 hashes:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Artifact hashes:

- `13B-alignment-result-contract.json`:
  `68d5caa5f10d238d3114747f3caaaa76ab2a0321ad4fae924281ce1101026cd0`
- `13B-browser-e2e-result.json`:
  `1beeefceec68e4324b4165a8494446e2066c9ab8cf37557feb3588c4c5ea360a`
- `13B-concept-query-contract.json`:
  `fc1a6bb7756193fc1d3ad836acae51273cdb4254f8dde8f68d59c2dc4f866c3c`
- `13B-evidence-scope-matrix.csv`:
  `dbd343e41bb1ffc24df0a98087610a8ab31ba7bea27f920f87100aad82aac17c`
- `13B-personal-learning-record-contract.json`:
  `0b3660b011649c11e41549d2bb8ade1c745b67f03ac9e2b5baefda09e5a678c3`
- `13B-privacy-access-matrix.csv`:
  `bf72cafa33e31d8a5b38a4ac47e4f8a07af9ae03530c5e0c54685a9a1ce5f227`
- `13B-synthetic-timing.json`:
  `075e33b21d5d2e7f7d1bb6c9ca93b458de3e9a568c614bc4379bc34358549778`
- `13B-workspace-flow-matrix.csv`:
  `dbe77a29b5e566d70ac4951c118e4aeeca9f5bbb524fde8ab6d2e8dd63ff1bd7`

Accident database before/final: SHA-256
`9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`;
size `1015808`; mtime `1785496597`; WAL/SHM absent/absent.
