# Scanned PDF OCR Production Path

Task 10C.P1 establishes the local scanned-PDF text OCR path for clear synthetic
English, Simplified Chinese, and bilingual scans. This is a text OCR closure, not
formula OCR, handwriting recognition, table reconstruction, or semantic quality
verification.

## Architecture

The production path is:

```text
PDF upload
-> native PDF text inspection
-> scanned page detection
-> page rendering to controlled temporary images
-> local Tesseract CLI OCR
-> TSV word/line parsing
-> DocumentParseBlock with page and bbox provenance
-> parse quality admission
-> governed source/chunks
-> candidate governance
-> Formal WorkflowRun and Formal Items
```

Born-digital PDFs keep the native text path. Mixed PDFs retain reliable native
text and only OCR pages that have no native text layer.

## Tesseract Discovery

Production code does not depend on Homebrew, a Windows installer path, or a
fixed installation directory. Discovery order is:

1. `LEXIBRIDGE_TESSERACT_CMD`, which must contain only the executable path.
2. `shutil.which("tesseract")`.
3. If neither produces a runnable executable, OCR fails closed as unavailable.

`LEXIBRIDGE_TESSDATA_PREFIX` is optional and should only be used when the
operator-installed Tesseract cannot find its language data through its own
default mechanism.

## Language Contract

Supported OCR language modes are allowlisted:

- English: `eng`
- Simplified Chinese: `chi_sim`
- Bilingual/mixed: `eng+chi_sim`
- Orientation/script data health: `osd`

The adapter does not accept arbitrary language strings or extra Tesseract
arguments from users or HTTP requests.

## Subprocess Safety

Tesseract is invoked with a subprocess argument list and `shell=False`.
The adapter sets a timeout, captures stdout/stderr, rejects nonzero exits, caps
output size, redacts local paths and sentinel-shaped secrets from safe errors,
and does not log full OCR text as an error payload.

## Provenance

The adapter requests TSV output and parses:

- page number
- Tesseract block, paragraph, line, and word numbers
- bounding box
- word confidence
- language configuration
- provider name
- engine-version-present marker
- rendering DPI marker

The persisted `DocumentParseBlock.source_locator` includes page and bbox
information such as `page:1;ocr:1.1.2;bbox:...`. `DocumentChunk` and governed
`KnowledgeChunk` preserve those locators for downstream Formal Items.

Confidence values use Tesseract's own TSV confidence semantics. Missing or
negative confidence is stored as null rather than converted into a fabricated
probability.

## Quality Admission

Clean OCR output is classified as `ocr_text_ok`. It is eligible for governed
source creation and Formal workflow admission while preserving OCR flags such as
`ocr_required`, `ocr_completed`, `ocr_tsv_provenance`, `ocr_provider_tesseract`,
and `ocr_language_*`.

Low-confidence OCR remains `ocr_low_confidence`. Empty OCR, missing engines,
missing language data, rendering failures, oversized pages, timeouts, and
unreadable PDFs fail closed and must not fabricate text.

## Resource Limits

The PDF OCR path enforces:

- maximum OCR pages per PDF
- maximum rendered pixels per page
- maximum total rendered pixels per PDF
- bounded render DPI
- temporary directory lifecycle
- subprocess timeout
- Tesseract stdout/stderr limits

Temporary page images are created outside the repository and cleaned after OCR.

## Current Verification

Current-host runtime:

- Platform: macOS
- Engine: Tesseract `5.5.3`
- Languages verified: `eng`, `chi_sim`, `osd`
- Health CLI: `scripts/check_local_ocr_health.py`
- OCR acceptance: `scripts/run_scanned_pdf_ocr_acceptance.py`

Acceptance results on synthetic fixtures:

| Fixture | OCR Status | Recall | Governed Source | Formal Items |
|---|---|---:|---:|---:|
| born-digital-text | native text, OCR not executed | English 10/10 | yes | 33 |
| scanned-english | `ocr_text_ok` | English 10/10 | yes | 18 |
| scanned-chinese | `ocr_text_ok` | Chinese 10/10 | yes | 6 |
| scanned-bilingual | `ocr_text_ok` | English 5/5, Chinese 5/5 | yes | 10 |
| mixed-layout | native text, OCR not required | English 5/5 | yes | 0 |

External Provider requests, private-course Provider requests, and main database
mutation are all zero in the OCR acceptance artifact.

Windows code contract is covered for path handling, executable discovery, and
safe subprocess construction. Windows runtime is not yet verified; that requires
running health, smoke, and scanned-PDF production E2E on a real Windows 10/11
host.

## Installation Notes

macOS operators may install Tesseract through a trusted package manager or
managed runtime, then verify:

```bash
command -v tesseract
tesseract --version
tesseract --list-langs
```

Windows operators should install a trusted Tesseract Windows build, provide
`eng.traineddata`, `chi_sim.traineddata`, and `osd.traineddata`, then verify in
PowerShell:

```powershell
Get-Command tesseract
where.exe tesseract
tesseract --version
tesseract --list-langs
```

If the executable is not on `PATH`, set `LEXIBRIDGE_TESSERACT_CMD` in the server
process environment. Do not put local absolute paths into Git, `.env.example`,
browser storage, API payloads, or audit artifacts.

## Known Limits

- Formula image recognition remains `FORMULA_IMAGE_RECOGNITION_NOT_CLOSED`.
- Tesseract text OCR is not LaTeX or formula structure recognition.
- Handwriting, low-quality camera scans, skewed pages, complex tables, chart
  extraction, and mathematical layout recovery remain separate tasks.
- Real Provider semantic quality remains unverified and is not affected by this
  OCR closure.
