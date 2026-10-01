# Formula Image Detection And Recognition Routing Contract

Task 10C.P2 establishes a production parsing boundary for raster formula region
detection and recognition routing. It does not perform formula structure
recognition and does not call an external formula Provider.

## Scope

LexiBridge separates three layers:

- Ordinary text extraction and text OCR.
- Raster formula region detection.
- Formula structure recognition into LaTeX, MathML, or another structured form.

This contract closes the second layer and defines the routing boundary for the
third. A detected formula region is an auditable image region, not a recognized
mathematical expression.

## Data Contract

Formula regions are represented with the following safe fields:

- `formula_region_uid`
- `source_uid`
- `document_uid`
- `page_number`
- `bounding_box`
- `region_image_hash`
- `detection_method`
- `detection_confidence`
- `surrounding_text_refs`
- `source_page_ref`
- `recognizer_status`
- `recognizer_provider`
- `recognizer_model`
- `recognition_confidence`
- `latex_candidate`
- `mathml_candidate`
- `abstention_reason`
- `provenance`
- `created_at`

The persisted `FormulaBlock` row records region identity, page and bbox
provenance, a region image hash, the detection method, recognizer routing state,
and abstention metadata. It does not persist a full page image and does not
fabricate LaTeX.

## Detection

The PDF detector reuses the existing rendered/layout PDF stack and inspects
raster image blocks from page layout data. It rejects full-page scanned images,
plain text-only pages, and ordinary non-formula images through a conservative
symbol-density and connected-component heuristic.

Detected regions use:

```text
detection_method = pdf_raster_image_formula_heuristic
recognizer_status = FORMULA_RECOGNIZER_UNAVAILABLE
```

Formula detection is independent of ordinary text/OCR parsing. Detection failure
does not block ordinary text extraction, governed source creation, candidate
governance, or Formal Workflow admission.

## Recognition Routing

The recognizer boundary exposes:

- `provider_id`
- `model_id`
- health/status
- `recognize(region)`
- structured result
- timeout handling
- abstention
- malformed result handling
- confidence field, when a recognizer supplies one
- provenance
- future cost/request metadata placeholders

Current production recognizer behavior is intentionally unavailable:

```text
FORMULA_RECOGNIZER_UNAVAILABLE
```

The deterministic recognizer is test-only and must not be represented as a real
formula OCR Provider.

## Flow

```text
PDF page
-> native text or OCR text blocks
-> layout analysis
-> raster formula region detection
-> FormulaBlock region record
-> recognizer routing
-> unavailable or future structured formula proposal
```

Formula regions do not directly become Formal Items. Surrounding text may still
enter ordinary candidate governance, and formula regions may later support a
separate review or formula-aware Formal Workflow extension.

## Safety

- No external Provider request is made by this detector.
- Tesseract text OCR is not treated as formula recognition.
- The detector does not generate formula results from filenames or fixtures.
- Temporary cropped images are not persisted by the production path.
- The region hash is computed from the embedded raster image bytes.
- Raw page screenshots are not written into Git, audit docs, or public artifacts.

## Current Verification

Task 10C.P2 verifies:

- One independent raster formula region is detected in the synthetic formula
  fixture.
- Plain scanned text, born-digital text, and mixed-layout pages are not reported
  as formula image regions.
- Multiple formula images on one page are detected in unit coverage.
- Recognition unavailable status is explicit and fail-soft.
- Existing scanned-PDF text OCR and born-digital parsing regressions pass.

## Known Limits

- Formula structure recognition is not implemented.
- LaTeX and MathML candidates are empty unless a future recognizer supplies them.
- Integral bounds, matrices, complex fractions, handwriting, charts, and table
  reconstruction remain outside this closure.
- The heuristic is intentionally conservative and may miss formula-like raster
  images that do not look symbol-dense.
