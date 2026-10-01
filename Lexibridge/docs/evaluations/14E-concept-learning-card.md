# Task 14E — Student Concept Learning Card

## Status

- Technical status: `STUDENT_CONCEPT_LEARNING_CARD_CONTRACT_CLOSED`
- Quality status: `STUDENT_CONCEPT_LEARNING_CARD_OFFLINE_BASELINE_ESTABLISHED`
- Baseline commit: `b20dc4d50773923f6089b49e215a004137a25689`
- Scope: student presentation and learning interaction only
- Real Provider requests: `0`
- Application external API requests: `0`

This task is an offline/synthetic engineering baseline. It is not evidence of
real student learning value and does not start the multi-student pilot.

## Before and after

Before, the ConceptQuery result rendered as one long report containing the raw
machine status, all evidence, alternatives and personal controls at once.

After:

```text
existing PDF.js selection
  -> existing AlignmentResult
  -> compact concept learning card
       -> reveal answer
       -> expand bounded evidence / alternatives
       -> save, note, understood/confused
       -> active-recall review from the existing notebook
```

No second alignment, card, retrieval or personal-record workflow was created.

## Product contract

- `READY` is displayed as evidence-backed, not official.
- `REVIEW_REQUIRED` displays bounded evidence-backed alternatives and remains
  available for private study.
- `NOT_READY` explicitly says that no reliable Chinese correspondence was
  found; generated hints cannot become evidence.
- Both Personal and Managed Course results use the same renderer, the same
  ConceptQuery service, and the same private notebook.
- Every result remains `PRIVATE / NON_OFFICIAL`; publication is not introduced.

## Browser acceptance

The controlled Chromium runner passed all three flows after correcting its
synthetic Managed Course source metadata to the governed values required by the
qualification policy (`allowed_for_course_use` and normalized parse quality
`ready`). The production qualification policy and thresholds were not changed.

- Student: direct PDF selection, Personal and Managed Course cards, evidence
  expansion, private save, note, understanding state, notebook search/filter,
  active recall and Student 2 privacy boundary: pass.
- Instructor: English course-side dashboard, Reviewer Console navigation hidden,
  no Reviewer-only initialization prefetch: pass.
- Reviewer: existing Task 12J-B queue/detail/review/fake draft flow: pass.
- Console errors: `0`.
- Page errors: `0`.
- External dependency requests: `0`.
- The three `example.invalid` probes were blocked as expected.

The final Browser E2E run recorded 80 Student steps, 7 Instructor steps and
15 Reviewer steps, with zero console/page errors.

## Verification boundaries

Unchanged:

- parser and layout pipeline;
- PDF.js selection mapping;
- multilingual retrieval;
- Chinese candidate generation;
- pairing/reranker;
- qualification/readiness thresholds;
- Prompt and Provider transport;
- V2 corpus and gold.

The fixture correction was necessary because a generic `authorized` source
value and UI label `qualified` do not satisfy the formal source governance
contract. Keeping the fixture invalid would have tested stale assumptions rather
than the student card.

## Verification

- targeted card/notebook/PDF.js/browser-runner tests: `38 passed`;
- full pytest: `1749 passed, 5 skipped, 56 warnings`;
- `scripts/dev_check.py`: pass, including its independent pytest, migration and
  backend smoke;
- `scripts/check_release_safety.py`: pass;
- `git diff --check`: pass;
- accident database before/final: SHA-256
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`, size
  `1015808`, mtime `1785496597`, WAL/SHM absent/absent;
- frozen V2 hashes unchanged: manifest
  `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`, gold
  `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`, English
  `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`, Chinese
  `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`.

## Artifacts

- `14E-learning-card-contract.json`:
  `e00d50dcfc8a0537e9f6b22e96a568b50844f6fcb81a1320c1d5a918394ef7ea`;
- `14E-interaction-matrix.csv`:
  `cb163c4959cb4dd62881c9ccfb7b89b7fe34389086e9644b3588a3f247b28269`;
- `14E-browser-e2e-result.json`:
  `d67b21cae17b01413830d1c38cd5893db2e9fb36530d4d008a6d0160abe5cb2d`.

## Next ordered step

After this branch is reviewed and merged, proceed to the controlled
multi-student pilot. Do not interpret this offline baseline as a real-user
validation.
