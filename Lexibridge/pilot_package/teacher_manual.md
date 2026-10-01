# Teacher Manual

## Main Teacher Tasks

- Create or select a course.
- Upload English course materials.
- Upload Chinese reference materials.
- Check background job status.
- Trigger AlignmentRun.
- Review terminology cards.
- Handle Quality Control.
- Process student feedback.
- Export course terminology.
- Review KnowledgeBaseVersion and EvaluationRun records.

## Uploading Materials

English materials should include English lecture slides, course notes, assignment concept summaries, or teacher-prepared excerpts. Upload them with:

```text
language=en
knowledge_base_type=en_course_kb
source_type=lecture_notes or teacher_upload
```

Chinese materials should include authorized Chinese course notes, teacher summaries, bilingual glossaries, or reference excerpts. Upload them with:

```text
language=zh
knowledge_base_type=zh_course_kb
source_type=teacher_upload or uploaded_reference
```

Use `bilingual` only when the same file clearly contains both languages. Use `unknown` only when the file cannot be categorized and then check parsing results carefully.

OCR is needed for scanned PDFs and image files. Formula OCR is needed only when formulas are image-based and formula evidence matters. If Formula OCR is not configured, formula regions can be detected and saved, but LaTeX may not be produced.

Upload does not immediately guarantee terminology cards. The system must parse the file, create chunks, build or update the knowledge base, retrieve evidence, and run alignment.

## Job Status

After upload, check:

- `queued`: waiting.
- `running`: parser or alignment is active.
- `completed`: outputs are available.
- `failed`: inspect `error_message`.
- `canceled`: manually stopped.

Do not run QC until parsing and alignment jobs have completed.

## Quality Control Statuses

`auto_approved`: system passed all gates. Review samples during pilot; do not assume all are perfect.

`pending_quality_control`: teacher review required. Read evidence before approving.

`needs_more_evidence`: English or Chinese evidence is missing or weak. Upload more material or mark unresolved.

`conflict_detected`: multiple translations or evidence conflicts. Compare sources and choose carefully.

`domain_mismatch`: evidence may come from the wrong discipline. Do not approve until corrected.

`ocr_low_confidence`: OCR text may be noisy. Check source page or upload a better file.

`formula_evidence_missing`: formula region exists but formula OCR is unavailable or failed. Use caution for formula-dependent concepts.

`no_en_evidence`: English evidence missing. Upload or correct English source material.

`no_zh_evidence`: Chinese evidence missing. Upload or correct Chinese reference material.

`unverified_translation`: translation exists but evidence is insufficient. Treat as a suggestion.

## Evidence Judgment Checklist

- Does English evidence contain the term or concept?
- Does Chinese evidence explain the same concept?
- Are the concept boundaries equal, broader, or narrower?
- Is the source from the correct course and discipline?
- Is there OCR noise?
- Is formula evidence needed and available?
- Does the AI explanation match the course context?

## Feedback Handling

Student feedback does not directly modify a card. Review feedback, check linked evidence, then resolve, reject, convert to EvaluationItem, or convert to Backlog.

## Teacher Risks

- Do not upload unclear copyrighted full textbooks.
- Do not upload student privacy files to course public KB.
- Do not treat pending cards as final terms.
- Do not ignore `risk_note`.
- Mock/local AI output is not verified live AI output.
