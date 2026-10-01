# Task 13C.6-A — Personal Workspace Real-student Pilot Readiness

## Status

- Technical status: `PERSONAL_WORKSPACE_REAL_STUDENT_PILOT_INFRASTRUCTURE_CLOSED`
- Quality status: `REAL_STUDENT_PILOT_NOT_EXECUTED`
- Baseline: `88e38bea5d24a54e65a01a4a67ff2686319a45d1`
- Real consented participants: `0`
- Real completed sessions: `0`
- External application API requests: `0`
- Real Provider requests: `0`
- Real credentials read: `false`

The technical status closes only the consent, measurement, privacy and
synthetic execution contract. No real student has been recruited or measured,
so this report makes no student-value or learning-outcome claim.

## Audit conclusion

The pre-existing pilot modules were built around Teacher-managed courses,
legacy TerminologyCard review, published course cards and old feedback queues.
They do not measure the current Student-first Personal Workspace flow and must
not be reused as evidence of a real student pilot.

The reusable production objects are `StudentConceptQuery`,
`PersonalLearningRecord`, `KnowledgeSource`, `KnowledgeChunk` and
`AuditRecord`. The new pilot layer observes derived completion state around
these objects and does not modify their product semantics.

## Contract implemented

- feature flag defaults to disabled;
- normal Student use never requires enrollment;
- consent and eligibility attestation are explicit and versioned;
- only an owned completed `PERSONAL` query may complete a session;
- server derives status/evidence/save/note-present/understanding metrics;
- pilot persistence contains no term, evidence, source UID, note text or raw
  query UID;
- Instructor and Reviewer access is denied;
- Admin receives only deidentified aggregate metrics;
- metrics are suppressed below three completed sessions;
- withdrawal deletes pilot sessions and surveys but retains product data;
- all writes are idempotent, and completion is version guarded.

## Synthetic browser result

The Student Browser E2E passed the optional panel flow:

```text
explicit consent -> start synthetic task
-> existing Personal PDF / Chinese evidence upload
-> existing selection / alignment / evidence result
-> existing save / note / understanding state
-> complete pilot task -> bounded survey
```

The existing Managed Course shared path and cross-student isolation also
passed. This is synthetic contract validation, not a real participant result.

## Quality gate for Task 13C.6-B

Do not proceed to Managed Course pilot work yet. After this PR is reviewed and
merged, the user must arrange at least five independently consenting students
and run the repository-external pilot described in `docs/pilot-runbook.md`.
Only the resulting aggregate can establish or reject a real-student usability
baseline.

Initial acceptance targets are completion >=80%, end-to-end median task time
<=10 minutes, evidence-helpfulness and uncertainty-understanding means
>=4/5, and zero privacy/provenance/external-request incidents.

## Safety baseline

Frozen Cross-Corpus V2 inputs and the accident database are verified during
final validation. No Prompt, Provider, retrieval, candidate, pairing,
qualification or readiness policy is changed by this task.

## Validation results

- targeted Student/pilot/13B–13C.5/OpenAPI/migration regression: `69 passed`;
- full pytest with `.env` loading disabled and credential variables empty:
  `1689 passed, 5 skipped`;
- Browser E2E: Student PASS (`71` steps), Instructor PASS (`7` steps),
  Reviewer PASS (`15` steps), console/page errors `0`, external dependencies
  `0`;
- `scripts/dev_check.py`: passed, including its independent `1689 passed,
  5 skipped` pytest, migration, release safety and backend smoke;
- `scripts/check_release_safety.py`: passed;
- `git diff --check`: passed;
- tracked model/cache scan: no tracked weights or cache directories.

The test and Browser runtimes set `LEXIBRIDGE_SKIP_ENV_FILE=true` and explicit
empty Provider credential variables before backend import. External application
API requests and real Provider requests remained zero.

## Frozen inputs and accident database

Cross-Corpus V2 remained:

- English: `e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5`
- Chinese: `cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7`
- Gold: `3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0`
- Manifest: `a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88`

The accident database before/final state is identical:

- SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- size: `1015808`
- mtime: `1785496597`
- WAL/SHM: `absent / absent`.

## Artifact hashes

- `13C6-privacy-measurement-contract.json`:
  `4ede2850b091eb461a564aa5259de9e1af33fd6c4a71fad9acf1bc57fcf2ac02`
- `13C6-real-session-status.json`:
  `bce8a4d70c39cc4492a9e577a3dd0c3a981b220eb33af510980f148b6149e951`
- `13C6-student-pilot-contract.json`:
  `ad3a74df79d530d4a90d8469cfb69480403efd99cf61ab9df14902dccc522e32`
- `13C6-synthetic-browser-result.json`:
  `ac67962233cc32f884614dd78bb911ea594dab84c1747a01f6f65a2fc18df9fc`
