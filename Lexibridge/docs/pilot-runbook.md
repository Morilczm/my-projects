# Student-first Personal Workspace Pilot Runbook

This runbook supersedes the pre-13A teacher/course-card pilot sequence. The old
teacher-led report remains supported for historical compatibility, but it is
not evidence of the current Student-first product.

## Scope and product claim

The pilot asks one question: can a consenting student independently upload
authorized English and Chinese reference PDFs, select one English course
concept, understand the evidence-backed alignment or uncertainty, and save a
private learning record?

It does not test official cards, Instructor review, Reviewer throughput,
translation, chat, or real Provider quality. Participation is optional and is
never required to use Personal Workspace.

## Before recruiting participants

1. Merge the pilot-infrastructure PR and deploy it with a repository-external
   pilot database and private upload storage. Never use `backend/lexibridge.db`.
2. Set `STUDENT_REAL_PILOT_ENABLED=true`. Keep external LLM/Provider execution
   disabled unless separately approved by a later task.
3. Use the exact consent contract
   `student-pilot-consent-zh@1.0.0`; do not enrol a participant implicitly.
4. Recruit only people who can independently consent. A study involving
   minors, publication, sensitive data, or institutional research requires the
   applicable ethics/privacy review before recruitment.
5. Ask each participant to use materials they are authorized to use. Do not
   place private documents in the repository, CI, screenshots, or artifacts.
6. Verify permission, cross-account isolation, withdrawal, release safety and
   Browser E2E on the release candidate.

## Participant task

1. Sign in as Student and open **My Workspace**.
2. Read the pilot disclosure. Declining leaves the whole product usable.
3. If participating, explicitly consent and start one pilot session.
4. Upload one English course PDF and one authorized Chinese reference PDF.
5. Wait for both materials to become `READY`.
6. Open the English PDF, select one bounded professional concept, and ask
   LexiBridge for an alignment.
7. Inspect both evidence sides and any uncertainty or alternatives.
8. Save the result, optionally write a private note, and choose an
   understanding state.
9. Complete the pilot task and submit the bounded post-task survey.
10. The participant may withdraw at any time. Withdrawal deletes pilot
    sessions/surveys but does not delete their normal materials, query results,
    or PersonalLearningRecord.

## Data minimization

The pilot session stores only:

- task state and bounded duration;
- alignment status and evidence-complete boolean;
- save, note-present and understanding-state booleans/categories;
- four 1–5 ratings and a reuse-intent boolean;
- an opaque one-way query reference hash.

It does not store the selected term, source/chunk UID, evidence text, note text,
Prompt, Provider payload, or raw query UID. Optional survey comments are
student-owned, excluded from aggregates and erased on withdrawal.

Instructor and Reviewer roles cannot access the pilot routes. Admin receives
only aggregates, and metrics remain suppressed below three completed sessions.

## Pilot gate and stop conditions

Target at least five consented, completed sessions before drawing even a small
usability conclusion. The initial product thresholds are:

- task completion rate at least 80%;
- median end-to-end task duration at most 10 minutes, including upload and
  local parsing wait;
- mean evidence-helpfulness and uncertainty-understanding at least 4/5;
- zero cross-account/private-content disclosure;
- zero external/real Provider requests for this controlled pilot;
- zero unsupported evidence/provenance incidents.

Stop immediately on a privacy/access-control incident, unexpected network or
Provider request, consent/version mismatch, or use of unauthorized material.
Do not tune Prompt, retrieval, pairing or qualification during the same run.

## Reporting boundary

The admin aggregate may be exported only after the small-cell gate opens. A
report must distinguish:

- synthetic contract validation;
- number of real consented/completed participants;
- excluded or withdrawn sessions;
- aggregate metrics;
- observed usability issues;
- engineering changes proposed for a separate task.

Never call CI/Browser E2E a real-student pilot. The legacy
`generate_pilot_report.py` course-card report is not the report for this pilot.

## Repository-external multi-identity rehearsal

Before recruiting human participants, the ordered engineering baseline can be
replayed with five isolated synthetic Student identities:

```bash
backend/.venv-macos/bin/python scripts/run_controlled_multi_student_pilot_14f.py \
  --personas 5 \
  --output-dir docs/evaluations/artifacts
```

The runner generates synthetic English and Chinese PDFs in memory, uses a
temporary SQLite database and upload directory, and drives the existing
upload, ingestion, reader, ConceptQuery, PersonalLearningRecord and notebook
routes. Its `self_simulated` result is engineering evidence only. It must not
be reported as a real-student outcome, and a real run still requires explicit
consent, authorized material and the privacy/ethics checks above.
