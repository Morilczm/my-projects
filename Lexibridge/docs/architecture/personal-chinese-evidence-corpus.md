# Personal Chinese Evidence Corpus

## Purpose

The Personal Workspace supports two governed material roles through the same
document lifecycle:

- `ENGLISH_COURSE_MATERIAL` is the Student's course-side material and may be
  selected to create a `ConceptQuery`.
- `CHINESE_REFERENCE_EVIDENCE` is an independent Chinese reference that may be
  searched as evidence for that Student only.

Neither role is a translation product. Chinese candidates must still be
extracted from independently uploaded Chinese `KnowledgeChunk` records and
must pass the existing retrieval, pairing and qualification chain.

## Admission contract

A Task 13C.2 Personal upload is admitted only when all of these are true:

1. the authenticated caller is a Student uploading to `scope_type=personal`;
2. the file is a PDF;
3. the caller selects one of the two fixed material roles;
4. the submitted language agrees with the role (`en` or `zh`);
5. the Student attests that the file may be used in the private workspace.

The server derives the persisted language from the role. The attestation is
stored as the bounded governance marker `student_attested_private_use`; the UI
and artifacts do not record a source body or rights statement.

The existing `Document`, parse record, layout blocks, `KnowledgeVersion`,
`KnowledgeSource` and `KnowledgeChunk` objects are reused. No new table,
parser, index, retrieval service or alignment pipeline is introduced.

## Source governance and scope

Both material roles remain:

- `scope_type=personal`;
- `visibility=private`;
- `authorization_status=allowed_for_private_use`;
- `license_status=restricted`;
- `allow_student_search=true`;
- `allow_derivative_cards=false`;
- `trust_level=student_uploaded`.

Role-specific `KnowledgeSource.source_role` values are
`english_course_material` and `chinese_reference_material`. Search admission
also requires an active source, eligible license/authorization, expected
language and the existing owner boundary.

The Student result records a sanitized evidence scope:

- `PERSONAL_PRIVATE` when Student-owned Chinese evidence is used;
- `PLATFORM_GOVERNED` only when an explicitly configured fallback is needed;
- `NONE` when no eligible source exists.

Production selection remains personal-first. Other Students' private sources
and private course sources are never added to `allowed_source_uids`.

## Parse-quality adapter

Parser location markers such as `[Page 1]` are provenance, not mathematical
content. They are removed before the existing formula-text heuristic runs.
All other historical formula signals remain unchanged.

The qualification adapter treats known layout/parser identity labels as
structural provenance, not risk. Unknown flags and all existing OCR, formula,
partial-text and governance risks remain fail closed. This maps clean
`native_text_ok` material into the qualification vocabulary without lowering
the frozen qualification threshold.

## Student flow

`My Workspace upload`
→ existing background parse/layout worker
→ private governed source and chunks
→ Student selects text in the uploaded English source
→ server validates source, chunk and offsets
→ existing multilingual retrieval searches the allowed Chinese scope
→ existing candidate extraction, pairing and qualification
→ private/non-official Student result
→ existing `PersonalLearningRecord`.

The production top-ranked bilingual pair remains authoritative. A lower-ranked
candidate is never substituted by this contract. Translation, glossary and
Ollama outputs remain generated hints and cannot enter the evidence scope.

## Privacy and lifecycle

Instructor and Reviewer roles cannot read Personal materials, queries or
notes. Another Student receives a non-disclosing not-found response. Deleting
a material continues to deactivate its source/chunks while preserving the
historical result as source-unavailable under the Task 13C lifecycle contract.

No Provider is required for the core evidence result. CI uses synthetic PDFs,
temporary databases and deterministic local scoring backends; the fixed-model
acceptance uses the pinned local multilingual E5 model in offline mode.
