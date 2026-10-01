# Final Presentation Materials Index

## Project Positioning

LexiBridge AI is an AI bilingual course knowledge alignment platform for transnational education, not a generic translation website.

## Pain Points

- Students struggle with English professional terminology.
- Teachers repeatedly prepare bilingual glossaries.
- Generic AI lacks course evidence and traceability.

## User Roles

- Teachers.
- Students.
- Admins.
- Pilot owner.

## Core Workflow

Course materials -> parsing/OCR -> KB version -> retrieval -> alignment -> terminology card -> QC -> student use -> feedback -> evaluation -> iteration.

## Technical Architecture

Modules include OCR, FormulaBlock, KnowledgeChunk, RetrievalBackend, TerminologyCard, AlignmentRun, EvaluationRun, PilotFeedback, IterationBacklog, and StorageService.

## Computational Thinking

- Decomposition: OCR, retrieval, alignment, evaluation, feedback.
- Abstraction: Document, FormulaBlock, KnowledgeChunk, TerminologyCard, EvaluationItem.
- Algorithmic thinking: scoring, state machines, gates, regression.
- Evaluation: smoke set, retrieval regression, demo flow.
- Iteration: PR-based improvement path.

## Design Thinking

- Empathize: bilingual terminology confusion.
- Define: course knowledge mismatch, not only translation error.
- Ideate: teacher/student/admin workflows.
- Prototype: Flask local MVP.
- Test: evaluation and pilot feedback.

## Project Evolution

The project moved from translation website to course knowledge alignment platform after recognizing teacher review cost, lack of course context, and need for evidence traceability.

## Materials

- `docs/final-project-summary.md`
- `docs/course-report-materials.md`
- `docs/poster-content-outline.md`
- `docs/presentation-script-outline.md`
- `docs/demo-test-report.md`
- `demo_data/`
- `pilot_package/`
