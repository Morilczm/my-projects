# AI / RAG Design Notes

## OCR Before AI

AI providers never receive raw image, PDF, PPTX, or DOCX files. The ingestion layer first creates structured `DocumentChunk` records and optional `FormulaBlock` records.

Only normal text chunks are sent to term extraction and alignment. Formula blocks are evidence metadata and are not used as `english_term` candidates.

## Text OCR Versus Formula OCR

Text OCR providers:

- `none`
- `mock`
- `tesseract`
- `paddle`
- `auto`

Formula OCR providers:

- `none`
- `mock`
- `mathpix`
- `local_latex`

Text OCR success means the platform may have readable Chinese/English text. It does not mean formulas were recognized. Formula OCR success requires a Formula OCR provider and produces `FormulaBlock.latex` / `FormulaBlock.plain_text`.

## Mixed PDF Parsing

For PDF pages, the parser:

1. extracts digital text,
2. scans image blocks on the same page,
3. renders image regions,
4. runs text OCR,
5. runs formula detection and Formula OCR state capture.

This prevents mixed pages from losing formula/image regions just because some selectable text exists.

## Alignment Risk

Chunks with low OCR confidence carry `ocr_low_confidence`. Formula OCR failures carry FormulaBlock statuses such as `needs_formula_ocr_engine` or `formula_ocr_failed`. Such evidence should not produce auto-approved cards.
