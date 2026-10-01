# Student PDF Reading and Direct Concept Selection

## Product boundary

The PDF reader is an input surface for a one-concept query. It is not the
student's final learning output and it does not replace the concept learning
card. The product sequence is:

```text
authorized English PDF
  -> student directly selects one term or bounded phrase on the PDF page
  -> governed source/page/block/chunk/span mapping
  -> existing ConceptQuery and Task 12 alignment chain
  -> student-facing concept learning card
  -> private PersonalLearningRecord
```

The current phase closes the direct-selection input contract. The next ordered
interface phase owns the card presentation and must not move alignment logic
into the reader.

## Shared workspace flow

`PERSONAL` and `MANAGED_COURSE` use the same reader, selection mapper,
ConceptQuery DTO, alignment service, result serializer and private notebook.
Workspace scope changes ownership/membership checks and labels only.

```text
Personal Document / Managed Course Document
  -> DocumentParseRecord
  -> governed KnowledgeSource and KnowledgeChunk
  -> Student material access check
  -> authenticated original-PDF response
  -> browser-local Blob URL
  -> self-hosted PDF.js canvas + text layer
  -> exact governed chunk/span mapping
  -> server revalidation
  -> existing alignment result
```

No parser, embedding, retrieval, pairing, qualification, readiness, Provider,
card, or review workflow is duplicated.

## PDF.js runtime contract

The frontend vendors `pdfjs-dist@6.2.108` under `frontend/vendor/pdfjs` with
its Apache-2.0 license, runtime modules, character maps, standard fonts and
WASM resources. `manifest.json` pins the package version and SHA-256 hashes.
The browser loads every PDF.js asset from the LexiBridge origin; no CDN or
external runtime request is allowed.

The reader:

- obtains the original PDF through the existing authenticated Student file
  route;
- stores the response only as a browser-local Blob URL;
- renders the selected page to a canvas;
- renders PDF.js `TextLayer` for native pointer/text selection;
- keeps page navigation, the canvas and the selectable layer synchronized;
- revokes the Blob URL and destroys the PDF.js document on source change or
  logout;
- disables XFA and dynamic evaluation support;
- exposes no credential in a URL, DOM node, artifact or PDF.js module.

## Reader API

`student-material-reader@1.0.0` remains the server contract:

- `GET /api/student/concept-materials/{source_uid}/reader?page={page}`
- `GET /api/student/concept-materials/{source_uid}/file`

The JSON response provides one page of governed selectable items. Each item
contains the chunk UID, page, parse-block UID, heading path, block type,
content hash and chunk-relative span. Storage paths and full document bodies
are not serialized.

The file endpoint is Student-only and repeats the same exact owner or active
course-member check. It returns only an active accessible PDF with private,
no-store, nosniff and same-origin controls.

## Direct-selection mapping

The visual PDF text layer is never trusted as evidence by itself. A selection
is admitted only when normalized PDF.js text maps to exactly one selectable
governed reader item. The mapper returns:

- `chunk_uid`;
- exact text as stored in the governed chunk;
- chunk-relative `selection_start` and `selection_end`;
- page and block identity for local audit.

Whitespace and case differences introduced by PDF text extraction are
normalized while preserving an offset map back to the governed source text.
When a PDF text layer omits layout whitespace between adjacent text nodes, a
compact comparison is allowed only if it still yields exactly one governed
span; the returned text and offsets always come from that governed span.
Repeated text is resolved only when its page occurrence order uniquely matches
the governed occurrence. Missing, overlong, outside-layer or ambiguous
selections fail closed with stable client reason codes. The client never
searches another page, top-k result or alternative chunk to manufacture a
mapping.

The existing ConceptQuery request remains unchanged:

```json
{
  "workspace_scope": "PERSONAL | MANAGED_COURSE",
  "source_uid": "opaque source UID",
  "chunk_uid": "opaque chunk UID",
  "selected_text": "bounded English concept",
  "selection_start": 0,
  "selection_end": 15
}
```

The server retrieves the authorized chunk again, verifies exact text and
offsets, reconstructs bounded context and persists source/page/block/span
provenance. Client mapping therefore cannot bypass server authorization or
evidence validation.

## Safe fallback

The governed parsed-text fallback is shown only when the original PDF is
unavailable or PDF.js cannot render a usable page. It is never displayed next
to a working PDF text layer. The fallback uses the same one-page reader DTO and
submits the same ConceptQuery contract. Missing provenance remains
non-selectable.

This fallback preserves access to evidence; it does not convert OCR output,
translation hints or arbitrary browser text into source evidence.

## Access and privacy

- Personal source: exact Student ownership and active private source.
- Managed Course source: active `CourseMember` and course-bound source.
- Other Student: not-found semantics.
- Instructor, Reviewer and Admin: denied by the Student-only route.
- Deleted/inactive source or unavailable file: no PDF response.
- Complete source text, Blob URLs, credentials and local paths are excluded
  from logs and artifacts.

Reading and selecting requires no LLM Provider. The core evidence result
remains available without a Provider. Automated acceptance uses temporary
databases and synthetic PDFs with zero application external API requests, zero
real Provider requests and no real credential reads.

## Reuse and migration decision

Reused objects are `Document`, `DocumentParseRecord`, `KnowledgeSource`,
`KnowledgeChunk`, `CourseMember`, `StudentConceptQuery` and
`PersonalLearningRecord`. No schema migration is required.

The old flat `/chunks` compatibility endpoint remains unchanged but is not
used by the student reader. The former iframe plus separate parsed-text column
has been removed from the product UI. API deprecation remains a separate task.
