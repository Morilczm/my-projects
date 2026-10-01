# Task 11D: Publication Integrity and Provenance Hardening

- Status: `PUBLICATION_INTEGRITY_PROVENANCE_HARDENED`
- Baseline commit: `e6334f8dce6d4cd07b3c89675a76456fa181c417`
- Branch: `feature/publication-integrity-provenance-11d`
- Database schema changed: `False`
- Parser/OCR/provider changed: `False`

## Initial Defects

| Area | Before 11D | Risk |
|---|---|---|
| Stale review | Review actions did not require a client-side concurrency token. A stale teacher page could submit an action after another actor changed the card. | Lost update or stale approval. |
| Source withdrawal | Student publication checks primarily used card status. Approved cards could remain visible after core evidence source state changed. | Withdrawn or invalid evidence could remain student-visible. |
| Provenance display | API evidence payloads often retained source/chunk and parse metadata, but teacher/student UI did not consistently surface page, bbox, block, parser, quality, or source availability. | Reviewers and students could not audit the evidence location. |
| Browser coverage | 11B covered the flow, but 11D-specific stale review and withdrawal behavior lacked real browser interaction coverage. | Static frontend contract could miss UI/API integration failures. |

## Final API Contract

| Capability | Endpoint | Contract |
|---|---|---|
| Review detail | `GET /api/concept-cards/<card_uid>` | Returns `review_token`, source availability summary, and enriched English/Chinese evidence provenance. |
| Edit card | `PATCH /api/concept-cards/<card_uid>` | Requires `expected_version`; stale or missing token returns `409 CONCEPT_CARD_STALE_REVIEW`. |
| Review action | `POST /api/concept-cards/<card_uid>/review` | Requires `expected_version`; stale token returns `409 CONCEPT_CARD_STALE_REVIEW`; unavailable core source blocks approval with `422 CONCEPT_CARD_SOURCE_UNAVAILABLE`. |
| Student list/detail | `GET /api/student/concept-cards`, `GET /api/student/concept-cards/<card_uid>` | Returns only approved cards whose core evidence sources are still available to the course. |
| Student feedback | `POST /api/student/concept-cards/<card_uid>/feedback` | Fails closed for unpublished or source-unavailable cards. |
| Source status | `PATCH /api/knowledge-sources/<source_uid>` | Allows authorized teacher/admin source status updates through existing knowledge governance service. |

## Stale Review Protection

The review token is the existing `ConceptAlignmentCard.version`. Review queue/detail responses expose it as `review_token`. Teacher/admin edit, approve, reject, revision, evidence, reopen, and deprecate forms send it back as `expected_version`.

The backend validates the token before applying changes:

```text
client expected_version == persisted card.version
```

If it does not match, the request returns:

```text
HTTP 409
error_code = CONCEPT_CARD_STALE_REVIEW
```

No teacher edits, review records, status changes, or publication changes are applied on stale submission.

## Source Availability Policy

Publication is fail-closed. A card is student-visible only when:

```text
card.status == approved
and all referenced core English/Chinese evidence sources are available
and the student is enrolled in the course
```

Source availability is evaluated from the existing `KnowledgeSource.status` and evidence source/chunk references. A non-active source blocks:

- approving a draft or needs-review card;
- listing the approved card for students;
- loading the student detail;
- submitting new student feedback.

Historical card/review records are retained for authorized teachers and admins. The teacher review view displays source-unavailable warnings instead of deleting the card.

## Provenance Data Chain

Evidence payloads are enriched from existing card evidence and knowledge records:

```text
ConceptAlignmentCard.english_evidence / chinese_evidence
→ KnowledgeChunk.chunk_uid
→ KnowledgeSource.source_uid
→ optional DocumentParseRecord.parse_uid
```

When available, the API returns:

- `source_uid`
- `chunk_uid`
- `language`
- `source_title`
- `course`
- `source_role`
- `quality_status`
- `source_locator`
- `snippet`
- `parse_uid`
- `parse_block_uid`
- `page_number`
- `bbox`
- `bbox_available`
- `location_available`
- `block_type`
- `parser`
- `parse_quality_status`
- `source_status`
- `source_available`

When page or bbox data is absent, the API does not fabricate it. The UI displays a location-unavailable message.

## Frontend Display

The existing single-file frontend now sends the review token in review forms and displays:

- separate English and Chinese evidence sections;
- source title and bounded snippet;
- page/source locator when available;
- bbox availability;
- block type;
- parser or parse quality status;
- active/unavailable source badge;
- stale review and source-unavailable error messages.

The browser E2E verifies teacher review, stale review feedback, post-reload approval, student publication, student feedback, source withdrawal hiding, and teacher historical warning through real page interactions and local API calls.

## Authorization Matrix

| Action | Teacher | Enrolled Student | Non-enrolled Student | Other Teacher | Admin |
|---|---:|---:|---:|---:|---:|
| View review queue for owned/permitted course | yes | no | no | no | yes |
| Edit/review permitted card with current token | yes | no | no | no | yes |
| Review with stale token | 409 | no | no | 409/403 | 409 |
| Approve card with withdrawn core source | 422 | no | no | 403/422 | 422 |
| View approved student card | no | yes | no | no | admin-only management |
| View source-unavailable approved card as student | no | no | no | no | no student publication |
| Submit student feedback | no | yes, approved and available only | no | no | no |
| View historical withdrawn-source card in review UI | permitted course only | no | no | no | yes |

## Browser E2E

Command:

```text
backend/.venv-macos/bin/python scripts/run_publication_integrity_browser_e2e.py --json-output /private/tmp/lexibridge-11d-browser-e2e.json
```

Result:

```text
PASS
browser = Chromium 148.0.7778.96
console_errors = 0
page_errors = 0
blocked_external_requests = 0
external_dependency_requests = 0
```

The browser scenario used a temporary SQLite database and local loopback server. The source-withdrawal 404 checks were performed against the local API to avoid counting expected fail-closed responses as page console errors.

## Test Double Boundary

The task does not call a real Provider. Existing deterministic/mock alignment data is used only where the existing test/demo flow already provides Concept Cards. The following were not mocked in the new integrity tests:

- review token validation;
- review action persistence;
- student visibility query;
- source availability gate;
- feedback persistence;
- course authorization;
- evidence/provenance serialization.

## Database Protection

- Incident database: `backend/lexibridge.db`
- Incident SHA-256: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- Accepted as normal baseline: `False`
- Tests use temporary SQLite databases.
- No migration or seed was run against the incident database.
- No WAL/SHM files are expected.

## Privacy And Network

- Provider requests: `0`
- External document API requests: `0`
- Document egress: `0`
- Private data usage: `0`
- Model downloads: `0`
- External network requests: `0`
- Local loopback browser/API traffic: used for browser E2E only.

## Test Results

| Command | Result |
|---|---|
| `backend/.venv-macos/bin/python -m pytest tests/test_concept_card_publication_integrity.py -q` | `4 passed` |
| `backend/.venv-macos/bin/python -m pytest tests/test_concept_card_provenance_api.py -q` | `2 passed` |
| Related Concept Card/frontend regression suite | `58 passed` |
| KnowledgeSource/Formal workflow related regression suite | `35 passed` |
| Browser E2E | `PASS` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python scripts/dev_check.py` | `All local pre-release checks passed; internal pytest 1219 passed, 6 warnings` |
| `LEXIBRIDGE_TESSERACT_CMD=<verified local tesseract> backend/.venv-macos/bin/python -m pytest -q` | `1219 passed, 6 warnings` |
| `backend/.venv-macos/bin/python scripts/check_release_safety.py` | `Release safety check passed.` |

Warnings are unchanged known warnings: one SQLAlchemy `LegacyAPIWarning` in `tests/test_ai_provider_registry.py`, and five SWIG/PyMuPDF deprecation warnings in document parse quality tests.

## Remaining Limitations

- This task verifies publication integrity and product flow, not real semantic alignment quality.
- Existing records without page or bbox still cannot display page geometry.
- Complex PDF parsing remains subject to earlier parser limitations.
- Formula structure recognition is not implemented.
- LaTeX and MathML recognition are not implemented.
- Production embedding/vector retrieval remains outside this task.

## Final State

`PUBLICATION_INTEGRITY_PROVENANCE_HARDENED`
