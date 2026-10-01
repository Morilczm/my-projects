# Task 12B.1 Candidate-Set Overflow Governance Repair

## Status

`CANDIDATE_SET_OVERFLOW_GOVERNANCE_CLOSED`

Task 12B.1 changes only candidate-set overflow governance. It does not change
PDF parsing, OCR, chunking, candidate discovery patterns, normalization,
benchmark binding, Chinese candidates, retrieval, Prompt, Provider, corpus,
gold, aliases, thresholds, schema, migrations, seeds, frontend, or
release-safety rules. Real Provider requests: `0`.

## Exact root cause and original boundary

The limit is
`FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS = 50` in
`backend/services/document_alignment_term_candidates.py`. It is applied by
`extract_chunk_scoped_term_candidates`, which is called from
`bootstrap_document_alignment_workflow_items` through the production Formal
processing composition.

It is a per-governed-source, per-Formal-run bootstrap admission limit. It is not
per chunk, per card, or Provider batch. Its purpose is to bound workflow-item
persistence and all downstream per-item preparation and verification fan-out.
The separate 100-reference limit bounds provenance scope per candidate.

Before this task, extraction grouped raw occurrences by normalized term.
Therefore normalization and deduplication occurred before the threshold:

1. chunks were sorted by `(chunk_index, chunk_uid)`;
2. each chunk was passed to the unchanged deterministic extractor;
3. candidates were NFKC/whitespace normalized and case-folded;
4. occurrences with the same normalized term were grouped;
5. `len(grouped) > 50` returned `item_limit_exceeded` immediately;
6. candidate DTO construction and canonical sorting never occurred;
7. bootstrap marked the entire workflow root blocked and persisted zero items.

The whole-set rejection came from an explicit fail-closed branch and an
existing regression assertion, not from a documented requirement that partial
admission was forbidden. It protected downstream fan-out, but conflated a
bounded-governance event with total candidate absence.

The frozen Mechanics run contained 63 raw occurrences and 55 canonical
candidates, demonstrating repeated normalized terms before canonicalization.
The threshold was correctly applied to the 55-item canonical set, but the
result discarded all 55.

Candidates have occurrence count, first chunk index, source/chunk provenance,
and risk labels. They do not have a semantic score, confidence, benchmark
score, or ranking model. The production-derived canonical order is:

`(first_chunk_index, normalized_term, candidate_term)`.

Previously the result retained only counts and a safe limit error. The blocked
run exposed the limit error to the workflow API, so a teacher could distinguish
overflow from “no candidates,” but no per-candidate overflow identities were
retained. Existing bounded patterns include retrieval slicing, Chinese
candidate bounded ranking, audit-list truncation, and controlled Provider
batches; none was an existing Formal candidate partial-admission contract.

## Governance strategy

The implemented strategy is **A: bounded partial admission**:

- canonicalize and deterministically sort the complete extracted set;
- admit the first 50 candidates;
- mark every remaining candidate `overflow_rejected`;
- retain the 50-item production maximum even if a caller supplies a larger
  `max_items`;
- preserve lower caller limits;
- never use gold terms, Chinese terms, aliases, benchmark scores, required
  propositions, or quality outcomes for selection.

Every admitted and overflow candidate has a deterministic SHA-256 candidate
identity derived only from extraction version, source identity, normalized
term, and sorted chunk identities. Both groups retain source ID, chunk IDs,
normalized text, governance status, and governance reason.

For an overflow run, the existing workflow root `risk_summary` stores the
canonical/admitted/overflow counts, fixed limit, selection-order contract, and
per-overflow candidate identity/provenance/reason. No schema or migration was
required. The 50 admitted workflow items remain the only downstream
preparation/verification inputs, so ordinary APIs cannot bypass the bound and
overflow candidates cannot masquerade as parsing, extraction, or retrieval
failures.

Inputs of 50 or fewer retain the prior extracted candidate order and admission
behavior. Duplicate inputs are still canonicalized before governance.

## Frozen 55-candidate result

Frozen hashes remained:

- corpus:
  `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- gold:
  `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`

| Measure | Before | After |
| --- | ---: | ---: |
| Total canonical candidates | 81 | 81 |
| Admitted candidates | 26 | 76 |
| Explicit overflow/rejected candidates | 55 | 5 |
| Whole-set rejected sources | 1 | 0 |
| Exact matched | 3 | 14 |
| Missing | 22 | 11 |
| Ambiguous | 0 | 0 |
| Exact binding recall | 0.1200 | 0.5600 |
| Provider-ready | 3 | 3 |

The Mechanics source changed from atomic rejection of 55 candidates to 50
admitted plus 5 explicitly rejected overflow candidates. None of the five
overflow candidates was an exact frozen benchmark term, so benchmark misses
attributed directly to governance overflow fell to zero. The remaining 11
missing rows expose pre-existing candidate-discovery/boundary limitations,
including `electric charge` and `electric field`; those patterns were not
changed in this task.

Provider-ready remained 3 because the additional exact-bound candidates did
not satisfy the existing bilingual evidence preparation predicate. No
retrieval, Chinese-candidate, threshold, or Provider adjustment was made.
Task 11J's Chinese candidate-recall metric was not redefined or repaired;
the 0.1200 to 0.5600 figure above is specifically production English exact
binding recall for this candidate-governance evaluation.

## Test-first evidence

RED:

- `8 failed, 19 passed`;
- the 51-item case returned the current `item_limit_exceeded` whole-set
  rejection;
- the other failures showed that admitted/overflow metadata and the diagnostic
  distinction did not yet exist.

GREEN:

- focused candidate, bootstrap, diagnostic, and frozen evaluation:
  `55 passed`;
- required targeted set: `44 passed`;
- related candidate, Formal admission, worker, route, pagination, and API
  boundary regressions: `53 passed`.

Tests cover 50, 51, and 55 canonical candidates; normalized deduplication;
deterministic identities/order; gold isolation; source/chunk provenance;
explicit governance reasons; public limit clamping; production bootstrap
persistence; frozen Mechanics binding/readiness; zero Provider calls; and
accident-database immutability.

The mainline acceptance test previously expected candidate governance to remain
the final blocker. With this repair it correctly advances to the existing
bilingual-evidence blocker, so only that stale test expectation was updated;
the acceptance implementation and release-safety rules were unchanged.

## Full verification

- Full pytest: `1295 passed, 6 warnings`.
- `dev_check`: passed, including release safety, all 1295 tests, temporary
  database migration, and backend API smoke.
- Release safety: passed.
- Real Provider requests: `0`.
- Temporary SQLite was outside the repository and `DATABASE_URL` was set before
  backend import.
- Accident database before/final SHA-256, size, mtime, and absent WAL/SHM state
  were unchanged.

## Artifact

`docs/evaluations/artifacts/12B1-candidate-overflow-results.json`

SHA-256:
`9f837d50b886e90dd26318e2c7c601f7c3c9789d5275b5dbda41932fa370bf9f`

The artifact contains sanitized counts, frozen concept IDs, binding/readiness
statuses, and database fingerprints. It contains no source text, local absolute
path, credential, request/response, or Provider payload.
