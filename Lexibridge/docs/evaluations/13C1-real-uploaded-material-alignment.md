# Task 13C.1 — Real Uploaded Material Alignment Continuity

## Status

- Technical status: `REAL_UPLOADED_MATERIAL_ALIGNMENT_CONTRACT_CLOSED`
- Quality status: `REAL_UPLOADED_MATERIAL_ALIGNMENT_QUALITY_INSUFFICIENT`
- Baseline: `46c3902407404617f4ce2e677f79eba4093dc157`
- Task 13C ancestor: `08dcf5eb483b3861c78d208747b7c6a0119dfdeb`
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

This task closes the engineering continuity gap between a newly uploaded
Personal Workspace PDF and the existing Student ConceptQuery alignment chain.
It is a synthetic/offline acceptance, not a real-student or corpus-quality
validation.

## Production audit and root cause

Before Task 13C.1, the product presented this apparent path:

`upload PDF` → `READY material` → `Concept Query` → `AlignmentResult`.

However, Browser E2E uploaded and processed one synthetic PDF, then selected a
different pre-seeded English `KnowledgeSource`. The entire production alignment
runner was also replaced by `browser_fake_alignment_runner`. Consequently, the
test proved the upload lifecycle and a separate query UI, but did not prove
their continuity.

The real production route did call the Task 12 workflow, but three adapter gaps
were exposed:

1. deterministic CI model backends could not be injected without replacing the
   complete alignment runner;
2. review-grade evidence explicitly admitted by the Student adapter was dropped
   inside cross-language passage filtering, and the selected English side could
   be dropped for the same reason;
3. clean `native_text_ok` parser vocabulary was not adapted to the frozen
   qualification vocabulary, while a stale `no_chinese_candidate_found` label
   survived after candidate identification succeeded.

## After call graph

The verified production composition is now:

`My Workspace PDF upload`
→ existing document storage and background job
→ existing parser/layout analysis
→ existing heading-aware `KnowledgeChunk`
→ private governed `KnowledgeSource`
→ the exact uploaded source selected in the shared Student page
→ server-side span validation and bounded context
→ existing cross-language retrieval
→ existing Chinese candidate identification
→ existing bilingual pairing and reranking
→ frozen evidence qualification 1.1.0
→ Student `AlignmentResult`
→ `PersonalLearningRecord`.

No second parser, retrieval, alignment, qualification, or personal-record
workflow was created. The route accepts only server-configuration model backend
objects; ordinary API callers cannot select or disable them.

## Browser continuity contract

Browser E2E now uses the `source_uid` created by the actual upload job and opens
the query action from that material row. It asserts that the returned query is
bound to the same source. It no longer installs a full fake alignment runner.

CI still uses deterministic, fixed-contract scoring backends for the pinned
embedding and reranker interfaces so it performs no model download or network
request. The actual production orchestration—retrieval, candidate extraction,
pairing, qualification, serialization and personal-record persistence—is
executed.

Full Browser E2E result:

- Student: `PASS`
- Instructor: `PASS`
- Reviewer: `PASS`
- uploaded English source retained: `true`
- English and Chinese evidence visible: `true`
- PersonalLearningRecord saved: `true`
- external dependency requests: `0`
- real Provider requests: `0`

## Offline fixed-model acceptance

A separate repository runner uses an external temporary SQLite database,
external temporary upload storage and a model cache outside Git. It uploads one
synthetic English PDF and one independent synthetic Chinese PDF through the
production route, then runs the Student route without `STUDENT_ALIGNMENT_RUNNER`.

Embedding execution used the pinned local model:

- backend: `local_multilingual_e5_pytorch_cpu_v1`
- model: `intfloat/multilingual-e5-small`
- revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- offline mode: `true`

The large BGE reranker weights were not downloaded for this acceptance. Its
existing fixed model identity and interface were exercised using a
deterministic fixed-contract replay backend. This distinction is recorded in
the artifact and must not be interpreted as real reranker quality validation.

Acceptance result:

- workflow processing: `completed`
- exact uploaded English source retained: `true`
- only the uploaded Chinese source used: `true`
- English evidence: `1`
- Chinese evidence: `1`
- Chinese candidates: `1`
- provenance retained: `true`
- PersonalLearningRecord saved: `true`
- query latency: `2755.05 ms`
- total upload/query/save latency: `2864.32 ms`
- external API requests during acceptance: `0`
- real Provider requests: `0`

## Quality decision

The resulting student alignment status is `NOT_READY`; qualification is
`REJECTED` with `EVIDENCE_SOURCE_NOT_ELIGIBLE`. The synthetic ReportLab PDFs
are admitted for retrieval with review-grade parser/source risks, so evidence
and candidates remain visible to the qualification policy, but the policy
correctly fails closed.

This is materially better than either dropping the evidence or returning an
execution failure: the source-to-result contract is closed and its dominant
quality failure is now explicit. The quality status remains insufficient
because a newly uploaded synthetic source did not produce a qualified Student
recommendation with the actual fixed embedding model. No qualification
threshold, retrieval model, pairing rule or readiness policy was changed to
manufacture a READY result.

The next sequential task should address governed Chinese evidence coverage and
source-quality admission using a controlled corpus. It must preserve this
fail-closed behavior.

## Safety and scope

- both input PDFs are synthetic test material;
- no private source body is stored in artifacts;
- all test databases and uploads are outside the repository;
- no credential is read;
- no Provider or external application request is made;
- translation/glossary hints are not used as evidence;
- Task 12 retrieval, pairing and qualification thresholds are unchanged;
- Browser E2E continues to cover Student, Instructor and Reviewer role flows.

## Verification

- targeted regression: `69 passed`
- final fail-closed qualification regression: `18 passed`
- upload-quota isolation regression: `11 passed`
- Browser E2E: `PASS` (Student, Instructor and Reviewer)
- full pytest: `1631 passed, 5 skipped`
- `scripts/dev_check.py`: `PASS` (independent full pytest, migration and API smoke)
- `scripts/check_release_safety.py`: `PASS`
- `git diff --check`: `PASS`
- tracked model/cache files added: `0`

Frozen Cross-Corpus V2 hashes remain:

- English bundle:
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese bundle:
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold:
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest:
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Artifact hashes:

- `13C1-browser-continuity-result.json`:
  `dcb082b5bceeaafbcc4c76a5cbe5f85f14ca2daf0bcc4598b4aa11971a2efdad`
- `13C1-real-uploaded-alignment-result.json`:
  `69b0d2d3de0cc709fa6298908f59e51259a1684286d8e60c01fa2b0a639598bb`

Accident database before/final:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: `absent / absent`
