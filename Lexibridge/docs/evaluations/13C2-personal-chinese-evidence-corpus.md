# Task 13C.2 — Personal Chinese Evidence Corpus Closure

## Status

- Technical status: `PERSONAL_CHINESE_EVIDENCE_CORPUS_CONTRACT_CLOSED`
- Quality status: `PERSONAL_CHINESE_EVIDENCE_CORPUS_BASELINE_ESTABLISHED`
- Baseline: `4342dbc10a24ca3d96df6b39631a693d4c2a5e0c`
- Task 13C.1 ancestor: `1b1995324c88c1cd9ce1604caf2d5397731f3cb8`
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

This task closes the controlled quality gap identified by Task 13C.1. It is a
synthetic/offline engineering baseline, not a real-student or broad corpus
quality validation.

## Before and root cause

Task 13C.1 proved that a newly uploaded English source reached the production
Student alignment chain and retrieved an independently uploaded Chinese
source. The result still failed closed as `NOT_READY` because qualification
returned `EVIDENCE_SOURCE_NOT_ELIGIBLE`.

The failure had two concrete adapter causes:

1. the parser adds `[Page N]` location markers to raw text, while the formula
   heuristic interpreted their brackets as mathematical content and applied
   `formula_ocr_required` to otherwise clean PDFs;
2. after that marker was corrected, the qualification adapter still treated
   known layout/parser identity labels as unknown source-quality risks.

This was not a retrieval miss or a reason to lower qualification thresholds.

## After call graph

`My Workspace`
→ choose English course material or Chinese reference evidence
→ confirm private-use rights
→ existing PDF storage/background job
→ existing parser/layout-aware chunking
→ role-specific private governed `KnowledgeSource`
→ existing owner-scoped evidence resolver
→ existing multilingual E5 retrieval
→ existing Chinese candidate identification
→ existing bilingual pairing/reranking
→ frozen qualification policy
→ private/non-official Student result
→ existing `PersonalLearningRecord`.

No second parser, index, retrieval, alignment, card, review or personal-record
system was created. No database migration was needed.

## Material and evidence contract

The Student upload form now makes the evidence boundary explicit:

- `ENGLISH_COURSE_MATERIAL` becomes `english_course_material`;
- `CHINESE_REFERENCE_EVIDENCE` becomes
  `chinese_reference_material`;
- the server validates role/language consistency and requires a private-use
  rights attestation;
- both remain `PRIVATE`, restricted, Student-owned and ineligible for
  derivative official cards;
- only the English role exposes the selection/query action.

The Personal material list exposes bounded lifecycle and governance metadata:
material role, evidence tier, search eligibility and qualification-quality
status. It does not expose source bodies or credentials.

The evidence resolver records `PERSONAL_PRIVATE` for owner-scoped Chinese
evidence. Other Students' and private course sources are excluded. A
platform-governed tier remains an explicit configured fallback and is not
silently mixed into this acceptance.

## Parse and qualification safety

Only parser-generated page/slide location lines are removed before formula
text classification. Historical formula symbols and word signals are
unchanged, and formula image routing remains intact.

Known layout/parser identity flags are adapted as structural provenance. OCR,
formula, partial-text, governance and unknown future flags continue to fail
closed. Qualification thresholds and policy versions are unchanged.

The Student adapter maps the existing workflow's actual production rank-1 pair
to the Student recommendation and removes only stale pre-pairing risk labels
from the Student read model after a qualified decision. The frozen Task 12
workflow output remains unchanged. `evidence_from_low_trust_source` remains
visible because private Student uploads are intentionally non-official.

## Offline fixed-model acceptance

The acceptance used two synthetic PDFs, a temporary external SQLite database,
temporary upload storage and the pinned local model in offline mode:

- model: `intfloat/multilingual-e5-small`
- revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- exact uploaded English source retained: `true`
- only the uploaded Personal Chinese source used: `true`
- evidence scope: `PERSONAL_PRIVATE`
- English evidence: `1`
- Chinese evidence: `1`
- Chinese candidates: `1`
- qualification: `QUALIFIED`
- Student alignment status: `READY`
- provenance retained: `true`
- PersonalLearningRecord saved: `true`
- query latency: `2935.33 ms`
- total upload/query/save latency: `3044.15 ms`
- external API requests: `0`
- real Provider requests: `0`

The fixed BGE reranker contract was exercised by its existing deterministic
replay backend; this result is not a real-reranker or broad semantic-quality
claim.

## Browser and privacy result

Full Browser E2E passed for Student, Instructor and Reviewer. The Student flow
now proves:

`upload Chinese evidence PDF`
→ `PERSONAL_PRIVATE` searchable corpus
→ upload English course PDF
→ select an English concept from that exact source
→ view English/Chinese evidence
→ save a private learning record.

Student 2 remains unable to read Student 1's query or record. Instructor and
Reviewer regressions pass and neither gains access to Personal materials.

## Verification

- targeted and Task 12 scope regression: `158 passed, 1 skipped`
- formula/layout/ingestion regression: included and `PASS`
- Browser E2E: Student, Instructor and Reviewer `PASS`
- full pytest: `1640 passed, 5 skipped`
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

- `13C2-browser-e2e-result.json`:
  `a583a39ccb0a6a723b196e022428ed7bdf1ee9bf8ef57a2fc3cc774e2736b6ec`
- `13C2-evidence-source-admission.json`:
  `c32ad079b345cec2204c6d7bcbb79b48fa12f1f856470c2f6fa455eb8196c1b8`
- `13C2-personal-chinese-evidence-result.json`:
  `57e03284d897bbdfdaec1b7a73a21ded1018c6a28fef832f6c61d7445a03f49c`

Accident database before/final:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: `absent / absent`

## Safety

- synthetic fixtures only;
- temporary databases and uploads outside the repository;
- no complete source text in artifacts;
- no translation/glossary hint used as evidence;
- no Provider or external application request;
- no credential read;
- no Task 12 threshold, model or frozen benchmark change;
- accident database must match its before/final baseline.
