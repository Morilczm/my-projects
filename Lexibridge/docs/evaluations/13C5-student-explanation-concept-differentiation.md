# Task 13C.5 — Evidence-grounded Student Explanation and Concept Differentiation

## Status

- Technical status: `STUDENT_EXPLANATION_DIFFERENTIATION_CONTRACT_CLOSED`
- Quality status: `STUDENT_EXPLANATION_DIFFERENTIATION_BASELINE_ESTABLISHED`
- Baseline: `22fea5e95d4bd5ea0744be47426f3fdfa2a04101`
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

This status is a deterministic synthetic/local engineering baseline. It is not
evidence that real students understand the explanation or learn better from
the concept-comparison view.

## Read-only production audit

The existing Student Concept Result already had headings for `What It Means
Here`, `Why They Align`, `Alternatives` and `Do Not Confuse With`, but the
semantics were incomplete:

- `What It Means Here` displayed raw bounded context without a citation
  contract;
- `Why They Align` was a generic machine-status sentence;
- alternatives exposed term labels without their own evidence;
- `Do Not Confuse With` reused risk labels instead of a concept comparison;
- ordinary Student queries did not use Provider explanation output, and adding
  a Provider dependency would have weakened the evidence-only fallback;
- source deletion marked evidence unavailable but could still serialize cached
  bounded evidence and learning text.

The Chinese candidate aggregate already contained source/chunk bindings, and
the Student alignment aggregate already contained bounded Chinese evidence.
This allowed a deterministic read-model repair without changing retrieval,
candidate generation, pairing, qualification, readiness, Prompt or Provider.

## Production before/after

```text
before:
StudentConceptQuery
  -> Task 12 alignment result
  -> generic status text + bounded evidence
  -> Student Concept Result / PersonalLearningRecord

after:
StudentConceptQuery
  -> the same Task 12 alignment result
  -> student-alignment-result@1.2.0
     -> student-learning-support@1.0.0
        -> extractive English context + citation
        -> evidence-bound recommendation rationale
        -> alternative-specific Chinese evidence
        -> side-by-side evidence with unresolved boundary
  -> the same Student Concept Result / PersonalLearningRecord
```

Personal Workspace and Managed Course Workspace use the same service,
serializer, page and notebook. Both remain
`PRIVATE / NON_OFFICIAL / NOT_APPLICABLE`.

## Learning-support contract

Candidate admission requires all of the following:

- existing candidate UID;
- `evidence_backed=true`;
- `generated=false`;
- source/chunk pair present in the result's bounded Chinese evidence;
- bounded candidate and evidence limits.

The learning-support layer never reads gold, aliases or required propositions.
It emits no pair/reranker/qualification scores, raw reason codes, Prompt,
Provider or audit internals. Provider usage is fixed to false.

Status behavior:

- `READY`: `EVIDENCE_GROUNDED` only with complete source-bound inputs;
- `REVIEW_REQUIRED`: `ALTERNATIVES_UNRESOLVED`, with tentative candidates;
- `NOT_READY`: `NO_RELIABLE_ALIGNMENT`, no candidate rationale/comparison;
- incomplete provenance: `GROUNDING_INCOMPLETE`;
- deleted/inaccessible source: `SOURCE_UNAVAILABLE`, historical result and
  personal record retained but source text/evidence/explanation redacted.

Generated translation/glossary hints remain separate, non-evidence notices.

## Concept differentiation result

Each allowed alternative now carries its own bounded Chinese evidence. When a
selected candidate and alternative can be compared, the page displays their
evidence side by side. The boundary conclusion stays `UNRESOLVED`; the service
explicitly declines to invent the semantic distinction when no governed
contrast-evidence contract exists.

This is safer and more accurate than turning ranking scores into a student
explanation. A future quality task may introduce governed pedagogical contrast
claims, but only with auditable supporting evidence and separate evaluation.

## Tests and verification

- initial RED contract run: 13 expected failures and 1 pre-existing pass;
- deleted-source fail-closed RED: 1 expected failure before route redaction;
- targeted Student/workspace/notebook/Reviewer/translation-boundary tests:
  `94 passed`;
- Browser E2E: Student PASS (63 steps), Instructor PASS (7 steps), Reviewer
  PASS (15 steps), no console/page errors and external dependency requests 0;
- full pytest: `1678 passed, 5 skipped, 56 warnings`;
- `scripts/dev_check.py`: passed, including its independent full pytest,
  migration, release safety and backend smoke;
- `scripts/check_release_safety.py`: passed;
- `git diff --check`: passed;
- tracked model/cache scan: no tracked weights or cache directories.

The initial sandboxed full test run had only loopback bind permission failures;
the same suite passed outside the sandbox with a repository-external temporary
database. No real or external Provider request was made.

## Frozen inputs and safety

Cross-Corpus V2 hashes remained:

- English: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

The accident database remained:

- SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: `absent / absent`.

## Artifact hashes

- `13C5-browser-e2e-result.json`:
  `c0f43b02fdd1981cc7ccc248734b99dc18a0d26d416bb8cd042f850d9cc3c07d`
- `13C5-grounding-audit.json`:
  `7504582b4791e6da7063d0e026708a8d5dff2c61dc7ad2ffcb478852e9838e1b`
- `13C5-learning-support-contract.json`:
  `7ebe4a1e25e115013d07939237352879f97a6433e9ad12ac4c98b8fc7c41c92e`
- `13C5-status-behavior-matrix.csv`:
  `bbcc61bfbf4cd7ec1965727195db4704c3309d80cc9410190e320154de159581`

## Next gate

The next roadmap phase is a separately authorized real-student pilot. It must
measure whether students understand the uncertainty language, whether the
evidence comparison is useful, and where they remain confused. It must not
start until this PR is reviewed and merged.
