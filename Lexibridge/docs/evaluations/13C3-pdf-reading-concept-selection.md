# Task 13C.3 — PDF Reading and Concept Selection

## Status

- Technical status: `PDF_READING_CONCEPT_SELECTION_CONTRACT_CLOSED`
- Quality status: `PDF_READING_CONCEPT_SELECTION_BASELINE_ESTABLISHED`
- Baseline: `fb04a6201e0bbcd99e3dbcf525dbde4e1bd35133`
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

This is a synthetic/local engineering baseline. It does not claim real-student
usability or broad course-material quality validation.

## Production before and after

Before, the Student ConceptQuery page flattened at most 100 English chunks into
one list. The page did validate selected text on the server, but it did not show
the original PDF, did not expose complete page navigation and could silently
omit later chunks.

After:

```text
My Workspace or Managed Course English source
  -> shared page-aware Student reader
  -> authenticated private PDF Blob preview when the original is retained
  -> governed parsed text for the same page
  -> exact bounded selection with source/page/block/span
  -> existing ConceptQuery and Task 12 alignment chain
  -> existing private/non-official result and PersonalLearningRecord
```

No parser, chunker, embedding, retrieval, pairing, qualification, readiness,
Provider or publication policy was changed.

## Contract and implementation

The new `student-material-reader@1.0.0` route serializes one requested page and
all governed English chunks on that page. It reports available pages,
previous/next navigation, parser identity and complete source/page/block/span
provenance. Missing provenance and unbounded chunks fail closed.

The Student-only PDF endpoint applies the same ownership/membership checks and
returns `private, no-store` inline PDF content. The frontend obtains the file
with its existing Bearer token, creates a local Blob URL and revokes it on source
change or logout. No credential enters the URL and no storage path enters JSON.

The original PDF and selectable parsed text are shown side by side. Selection
uses the parsed text because embedded PDF viewers do not expose a reliable DOM
selection contract. The server still re-reads the chunk and validates exact
text and offsets before existing alignment begins.

## Workspace and privacy result

- Personal owner: reader, PDF and ConceptQuery allowed.
- Active Managed Course member: same reader and ConceptQuery contract allowed.
- Other Student/non-member: not-found semantics.
- Instructor/Reviewer/Admin: Student routes denied.
- Original PDF unavailable: parsed-text reader remains available when governed
  chunks exist; the UI does not fabricate a preview.
- All ordinary results remain `PRIVATE`, `NON_OFFICIAL`, `NOT_APPLICABLE`.

No migration was needed. `Document`, `DocumentParseRecord`, `KnowledgeSource`,
`KnowledgeChunk`, `CourseMember`, `StudentConceptQuery` and
`PersonalLearningRecord` are reused.

## Browser acceptance

The full browser acceptance used temporary storage and a synthetic two-page
English PDF. It verified:

- upload and background parsing;
- authenticated original-PDF Blob preview;
- page 1 -> page 2 -> page 1 navigation;
- synchronized governed text (`electric potential` / `electric field`);
- Personal Workspace selection, alignment, save, note and understanding state;
- the same reader and alignment page for Managed Course;
- Student 2 isolation;
- Instructor and Reviewer regression flows.

Result: Student `PASS` (47 steps), Instructor `PASS` (7), Reviewer `PASS` (15),
with zero JavaScript/page errors and zero external dependency requests.

Chromium's built-in PDF viewer reports internal `blob:` navigation cancellations
as `net::ERR_ABORTED` while replacing/re-rendering the same Blob document. The
E2E harness now classifies only `blob:` + `ERR_ABORTED` as an expected browser
lifecycle event; other failed requests still fail the run.

## Verification

- RED tests: confirmed missing reader/file routes and missing frontend reader;
- targeted reader/frontend and related regression tests: `65 passed`;
- Task 13B–13C.2 related regression: `PASS`;
- Browser E2E: Student/Instructor/Reviewer `PASS`;
- full pytest: `1652 passed, 5 skipped`;
- `scripts/dev_check.py`: `PASS`;
- `scripts/check_release_safety.py`: `PASS`;
- `git diff --check`: `PASS`.

Frozen Cross-Corpus V2 hashes verified unchanged:

- English: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

Accident database final state verified unchanged:

- SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: `absent / absent`.

Artifact SHA-256 hashes:

- `13C3-reader-contract.json`:
  `d6002315cf8c3c044b45bf7de25922929d61ae778b5bea207357a1443c6a525d`
- `13C3-access-provenance-matrix.csv`:
  `bac4ee1b68bd5dcfd6752a9e449340df49cceabd68a41a25dbbc779c1522a116`
- `13C3-browser-e2e-result.json`:
  `1a79d3db7ac5bb72be7353dad36332349b34aa9c2d8657d7e94a0acc264a98f8`
