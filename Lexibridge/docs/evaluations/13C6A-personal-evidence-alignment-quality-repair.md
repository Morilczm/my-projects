# Task 13C.6-A Repair — Personal Evidence Alignment Quality

## Status

- Technical status: `PERSONAL_EVIDENCE_ALIGNMENT_QUALITY_REPAIR_CLOSED`
- Quality status: `PERSONAL_EVIDENCE_ALIGNMENT_REHEARSAL_BASELINE_ESTABLISHED`
- Baseline: `666a6ea77e67a93c742eca56c0dd9c541eacb44c`
- Scope: Personal Workspace, private and non-official Student result
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

This repair closes defects exposed by the local synthetic Student rehearsal. It
does not claim real-student learning value and does not change the governed
qualification, readiness, Prompt or Provider contracts.

## Observed failure and root causes

The `Electric charge` query originally returned `NOT_READY`; its Chinese
candidate order was `电势`, `电场`, `电荷`. Four independent problems combined:

1. the multilingual embedding received an entire page-sized chunk, including
   repeated footer/page text and later neighboring concept sections;
2. punctuation and unit notation such as `(C)`, `N/C`, `(V)` and a prose
   hyphen were misclassified as mathematical formula content;
3. ConceptQuery idempotency did not include the current Chinese evidence
   corpus identity, so a source addition or source-version change could replay
   a result computed against an older evidence scope;
4. the Student serializer treated every formal `REJECTED` result as
   `NOT_READY`, even when the only blockers were unresolved pair ambiguity or
   a missing local reranker and the selected candidate itself had bounded
   independent Chinese evidence.

The formal score exceeded its minimum threshold in the observed run. Lowering
qualification thresholds would therefore have addressed neither the wrong
ranking nor the stale formula and idempotency defects.

## Production repair

Cross-language retrieval now builds a deterministic, bounded, concept-local
embedding representation. It removes repeated edge boilerplate and page
markers, keeps a heading with its definition, and stops before later
properties/boundary sections when those structural markers exist. Returned
evidence snippets remain bounded original source text, and source/chunk/page/
block/heading provenance is retained.

Personal PDF parsing uses a substantive formula-text policy: unit notation and
ordinary prose punctuation do not require formula OCR, while equations,
powers, mathematical functions, strong symbols and detected formula regions
remain review/fail-closed. The governed legacy policy remains the default for
non-Personal workflows, preserving frozen Task 12 behavior. Existing Personal
records with the historical false flags are handled without database mutation
only when the chunk explicitly has zero formula blocks and the current
substantive detector finds no formula signal.

The ConceptQuery fingerprint now includes a deterministic evidence-scope ID
derived from each permitted source UID, version and content hash. The same
selection replays only while the governed Chinese evidence scope is unchanged.

The Student display adapter may show `REVIEW_REQUIRED` for a formal
`REJECTED` result only when every reason belongs to the bounded ambiguity/
execution-unavailable set and the production-selected candidate itself is
non-generated and bound to permitted Chinese evidence. The stored formal
qualification remains `REJECTED`; Provider readiness and execution remain
closed. Fatal provenance, source-governance, missing-evidence and generated-
hint cases remain `NOT_READY`.

## Before / after rehearsal

The pinned offline model remained
`intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3`.

- before candidate order: `电势`, `电场`, `电荷`;
- after real-model retrieval: `电荷` page 1 rank 1, `电势` page 3 rank 2,
  `电场` page 2 rank 3;
- after full workflow candidate order: `电荷`, `电场`, `电势`;
- Student result: `REVIEW_REQUIRED`, recommended candidate `电荷`;
- formal qualification: still `REJECTED` with ambiguity and local execution
  availability reasons;
- stale replay: false;
- formula-context risk on the prose-only Personal sources: false.

This is the intended safe result: the student can inspect the evidence-backed
candidate and uncertainty, but the system does not claim formal automatic
qualification and cannot enter Provider execution.

## Regression and safety validation

- targeted parsing/retrieval/qualification/readiness/execution/Student tests:
  `134 passed`;
- full pytest: `1698 passed, 5 skipped`;
- Browser E2E: Student, Instructor and Reviewer flows `PASS`, no console/page
  errors and no external dependency requests;
- `scripts/dev_check.py`: `PASS`, including an independent full pytest run,
  migration, release safety and backend smoke;
- standalone release safety: `PASS`;
- `git diff --check`: `PASS`.

Frozen Cross-Corpus V2 retrieval remained hit@1 `0.7222`, hit@3 `0.8333` and
MRR `0.7778`; its input hashes are unchanged. No retrieval model, pairing/
qualification/readiness threshold, Prompt or Provider transport was changed.

The accident database remained byte-for-byte unchanged:

- SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`;
- size: `1015808`;
- mtime: `1785496597`;
- WAL/SHM: `absent / absent`.

## Artifact

- `13C6A-personal-evidence-alignment-quality-repair.json`:
  `7b235ecab092ac3f7eb4fc089aa14a37fda9f6604c364eb30d44778b7d602f89`.
