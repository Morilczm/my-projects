# Task 14F — Controlled Multi-Student Pilot

## Status

- Technical status: `CONTROLLED_MULTI_STUDENT_PILOT_CONTRACT_CLOSED`
- Quality status: `SELF_SIMULATED_MULTI_STUDENT_BASELINE_ESTABLISHED`
- Participant mode: `self_simulated`
- Real consenting participants: `0`
- Real Provider requests: `0`
- Application external API requests: `0`

The technical contract is closed for a local, content-minimized,
multi-identity rehearsal. This is not a claim that real students have
validated usability or learning value.

## Run and reused path

`scripts/run_controlled_multi_student_pilot_14f.py` creates five isolated
Student identities in a repository-external SQLite database. For each
identity it drives:

```text
consent -> start session -> upload English PDF
        -> upload Chinese evidence PDF -> run existing ingestion job
        -> read authenticated PDF material -> select bounded concept
        -> existing ConceptQuery/alignment -> save private record
        -> notebook revisit -> complete session -> bounded survey
```

The runner also attempts a foreign-persona completion request for every
identity. The existing owner guard rejects every attempt with HTTP 404. The
runner uses the existing local embedding/reranker test doubles and never
contacts a Provider.

## Results

| Metric | Result |
|---|---:|
| Personas | 5 |
| Explicit consent | 5/5 |
| Sessions started | 5/5 |
| Sessions completed | 5/5 |
| Completion rate | 100% |
| Evidence-complete sessions | 100% |
| Saved records | 100% |
| Notes present | 100% |
| Notebook revisit | 5/5 |
| Evidence helpfulness mean | 4.0/5 |
| Uncertainty understanding mean | 4.0/5 |
| Cross-account access blocked | 5/5 |
| External requests | 0 |
| Real Provider requests | 0 |

The recorded duration is `0 ms` in this scripted run because the session is
completed immediately after the API operations. It must not be interpreted as
a student task-time measurement. A real study must measure wall-clock time
from consent/session start through completion.

## Privacy and artifact boundary

Artifacts contain only aggregate metrics, opaque persona labels and bounded
booleans. They contain no PDF body, term, evidence, note, query UID, source UID,
credential, absolute path or Provider response. The admin aggregate returned
no individual rows and the pilot database was temporary and external to the
repository.

Artifacts:

- `14F-multi-student-pilot-results.json` — SHA-256
  `519cbe2ced71bc41b92d5f740fbf3322cd3bccb118bc120cd343c79fe7d43b8b`
- `14F-multi-student-pilot-matrix.csv` — SHA-256
  `13c8bc5fb54cdf1c041746d87540323777cecd5bd302a1534fb42a6bc9368996`
- `14F-multi-student-pilot-privacy-audit.json` — SHA-256
  `675db7f747e17ab9b449d38b299f7f185ed44ac8689ef4628387d6c649fd3cb4`

## Verification

- Multi-student pilot and related Student/PDF.js/card tests: `47 passed`.
- Full pytest: `1756 passed, 5 skipped, 56 warnings`.
- `scripts/dev_check.py`: passed; its embedded full suite reported
  `1756 passed, 5 skipped`, followed by temporary-database migration and API
  smoke.
- Chromium Browser E2E: Student `80` steps, Instructor `7` steps and Reviewer
  `15` steps passed; console/page errors were `0/0`, external dependency
  requests were `0`, and the three `example.invalid` probes were blocked as
  expected.
- Release safety and `git diff --check`: passed.
- Frozen V2 hashes unchanged.
- Accident database before/final: SHA-256
  `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`, size
  `1015808`, mtime `1785496597`, WAL/SHM absent/absent.

## Interpretation and next action

The run establishes that the Student-first flow composes across five isolated
accounts and that the privacy boundary holds under this deterministic
rehearsal. It does not establish the real-student quality baseline. Before
making a usability claim, deploy the documented local/private pilot with at
least five independently consenting students using authorized materials, then
replace the self-simulated status with a separately audited real-participant
report. Do not tune parsing, retrieval, qualification or Prompt behavior from
this rehearsal alone.
