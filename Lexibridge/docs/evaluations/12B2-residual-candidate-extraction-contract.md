# Task 12B.2 — Residual Candidate Extraction Contract Repair

Status: `RESIDUAL_CANDIDATE_EXTRACTION_CONTRACT_PARTIAL`

## Executive conclusion

Task 12B.2 repaired one dominant, general extraction-contract gap without
changing candidate governance, bounded-admission ordering, binding, retrieval,
Chinese candidates, prompts, providers, the frozen corpus, gold, or aliases.
The extractor now recognizes a bounded one-to-four-token subject at the start
of an English copular definition (`X is ...` or `X are ...`) as an exact
candidate span. This is a structural rule derived only from production text;
it contains no benchmark term or alias.

On the frozen 25-concept benchmark, exact binding improved from 14/25 to 22/25
and recall from 0.5600 to 0.8800. All nine residual
`EXTRACTION_MISSING` attributions disappeared: eight concepts matched and
`torque` became an explicit `OVERFLOW_NOT_ADMITTED` item. The other two
residual concepts remain definition-boundary defects. Because those are
different root causes and were deliberately not repaired in this task, the
status is PARTIAL.

## Residual 11 re-attribution

Before this change, the Task 12B.1 pipeline's remaining 11 items were:

| Concept | Before | After |
| --- | --- | --- |
| physics-04 `force` | `EXTRACTION_MISSING` | `MATCHED` |
| physics-05 `mass` | `CANDIDATE_BOUNDARY_DEFECT` | `CANDIDATE_BOUNDARY_DEFECT` |
| physics-06 `inertia` | `EXTRACTION_MISSING` | `MATCHED` |
| physics-08 `impulse` | `EXTRACTION_MISSING` | `MATCHED` |
| physics-09 `kinetic energy` | `EXTRACTION_MISSING` | `MATCHED` |
| physics-11 `work` | `EXTRACTION_MISSING` | `MATCHED` |
| physics-12 `power` | `EXTRACTION_MISSING` | `MATCHED` |
| physics-19 `angular momentum` | `CANDIDATE_BOUNDARY_DEFECT` | `CANDIDATE_BOUNDARY_DEFECT` |
| physics-20 `torque` | `EXTRACTION_MISSING` | `OVERFLOW_NOT_ADMITTED` |
| physics-21 `electric charge` | `EXTRACTION_MISSING` | `MATCHED` |
| physics-22 `electric field` | `EXTRACTION_MISSING` | `MATCHED` |

The post-change residual counts are: matched 8, candidate-boundary defect 2,
overflow-not-admitted 1, extraction missing 0, fragmentation 0, normalization
0, binding 0, and benchmark-alias gap 0. Every row remained in the
denominator. The sanitized artifact records source/parse/chunk presence,
runtime chunk and candidate IDs, bounded candidate summaries, normalization,
admission/overflow, binding, and earliest failure stage.

## Electric charge and electric field failure chain

Both terms occur as exact, sentence-leading subjects in the frozen English
electricity source:

- `Electric charge is ...`
- `Electric field is ...`

The exact text survived parsing and appeared in the production chunk input.
Before the change, n-gram enumeration formed each two-token span, but the
single occurrence received 45 base points plus 12 for being multi-word: 57,
one point below the existing admission threshold of 58. The definition-clue
list recognized forms such as `is defined as`, but not the plain copula
immediately following the term. Consequently, neither exact candidate reached
canonical deduplication, governance, normalization, or binding. Neighboring
outputs included `Electric`, `Electric potential`, and other electricity
phrases, but neither target was hidden in a longer candidate or split across
candidates.

The terms were not removed by the generic-term filter, token-length rule,
deduplication, or overflow governance. They shared the same root cause:
the extractor scored the contents of a definition but did not treat the
leading copular subject as a definition boundary.

After the change, both exact candidates are present, canonical, admitted,
normalized, and bound. The electricity source contains 28 canonical
candidates, all 28 admitted and none overflowed. The artifact contains the
runtime chunk identifiers; no full source text is retained.

## Modified extraction contract

For each existing English sentence input, the extractor identifies only an
exact leading subject of one to four existing term tokens immediately followed
by `is` or `are`. If that exact span also survives the existing n-gram noise
filter, it receives a deterministic structural boost. The normal scoring,
canonical deduplication, provenance construction, 50-item governance, and
bounded-admission ordering remain in force.

This rule:

- does not accept a term dictionary, gold, aliases, scores, or propositions;
- does not emit the complete definition sentence;
- preserves the first production display span, source ID, chunk IDs,
  normalized term, and candidate identity;
- also extracts unseen fixtures such as `magnetic flux` and `photon energy`;
- does not promote ordinary non-copular prose noun phrases; and
- cannot raise or disable the 50-item limit through the public API.

No benchmark-specific rule was added.

## Unfixed roots

`mass` remains represented only by the longer boundary
`Mass measures the amount`, and `angular momentum` remains represented by a
longer definition fragment. They are definition-boundary problems, not the
copular-subject scoring gap repaired here.

`torque` is now extracted exactly but appears in the Mechanics source's
explicit overflow set. Changing bounded-admission ordering to select it would
violate this task's scope. It is therefore not described as extraction
missing.

## Frozen quality comparison

| Metric | Task 12B.1 | Task 12B.2 |
| --- | ---: | ---: |
| Canonical candidates | 81 | 90 |
| Admitted candidates | 76 | 78 |
| Explicit overflow candidates | 5 | 12 |
| Whole-set rejected sources | 0 | 0 |
| Exact matched | 14 | 22 |
| Missing | 11 | 3 |
| Ambiguous | 0 | 0 |
| Exact-binding recall | 0.5600 | 0.8800 |
| Extraction missing | 9 | 0 |
| Boundary defect | 2 | 2 |
| Overflow not admitted | 0 | 1 |
| Provider-ready | 3 | 5 |
| Exact-match/canonical precision proxy | 0.1728 | 0.2444 |
| Non-benchmark-candidate proxy | 67 | 68 |
| Residual definition-fragment proxy | 2 | 2 |

Canonical candidates rose by nine (11.1%), while the non-benchmark-candidate
proxy rose by one and the definition-fragment proxy did not increase. This
does not indicate candidate explosion. Mechanics now has 62 canonical
candidates, 50 admitted, and 12 explicit overflow candidates. Electricity has
28 canonical and 28 admitted candidates. In both sources,
admitted plus overflow equals canonical, and no source is atomically rejected.

The candidate precision proxy is a benchmark diagnostic, not a production
selection input or a claim of real-world precision.

## RED/GREEN and validation

The RED suite failed on the absent copular definition subjects, including
`electric charge`, `electric field`, and unseen scientific phrases. It also
verified that the failure was the extraction contract rather than fixture or
import setup. After the minimal production change, the focused GREEN suite
passed.

Validation results:

- Focused GREEN: 30 passed.
- Required targeted regression: 53 passed.
- Related candidate, Formal, and API boundary regression: 53 passed.
- Full pytest: 1304 passed, 56 warnings.
- `dev_check`: passed, including release safety, 1304 tests, temporary
  migration, and backend API smoke.
- Standalone release-safety result: passed.

Two API tests initially could not bind a loopback port inside the filesystem
sandbox. They passed when rerun with the required local-port permission; this
was an execution-environment restriction, not a product failure.

## Safety and frozen inputs

The frozen corpus and gold hashes remained:

- Corpus:
  `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- Gold:
  `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`

The incident database was unchanged before and after:

- SHA-256:
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: 1015808
- mtime: 1785496597
- WAL: absent
- SHM: absent

All ingestion and evaluation used repository-external temporary SQLite
databases with `DATABASE_URL` set before importing the backend. No DeepSeek
credential was read. Real Provider requests: 0.

The sanitized artifact is
`docs/evaluations/artifacts/12B2-residual-candidate-results.json`, SHA-256
`e7232342de8e0b665fb50030bb4707a972784292763b775bce722dcc5711e3f8`.
It contains neither credentials, full source text, private files, nor
machine-absolute paths.

Task 12B.2 did not start retrieval, Chinese-candidate, Prompt, or Provider
optimization.
