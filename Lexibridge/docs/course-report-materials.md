# Course Report Materials

## Course Learning Reflected In The Project

LexiBridge AI demonstrates problem definition, computational thinking, design thinking, prototype iteration, evaluation, and reflection.

## Computational Thinking

### Decomposition

The system is decomposed into OCR, Formula OCR, document parsing, knowledge chunks, retrieval, alignment, quality control, evaluation, feedback, storage, and deployment readiness.

In report wording, decomposition means splitting the original broad translation problem into smaller verifiable modules: OCR, retrieval, alignment, evaluation, feedback, and deployment readiness.

### Abstraction

Key abstractions include `Document`, `DocumentChunk`, `FormulaBlock`, `KnowledgeSource`, `KnowledgeChunk`, `KnowledgeBaseVersion`, `TerminologyCard`, `EvaluationItem`, `RetrievalExperimentRun`, and `PilotFeedback`.

The main abstraction is that a terminology card is not just a translation string; it is a structured object with evidence, status, confidence, risk flags, and review history.

### Algorithmic Thinking

The project uses evidence scoring, metadata hard filters, state machines, confidence scoring, auto-approved gates, retrieval regression, and hybrid score fusion.

### Evaluation

Evaluation includes smoke sets, gold terms, no-evidence forced alignment checks, retrieval regression, demo flow, and pilot feedback conversion to EvaluationItem.

### Debugging And Iteration

The project evolved through PR-based improvements: OCR repair, evidence retrieval, alignment gates, evaluation harness, security, async jobs, UI workflows, demo data, deployment readiness, feedback loop, data migration, AI governance, KB versioning, and RAG retrieval enhancement.

## Design Thinking

### Empathize

Students in transnational education need to understand English professional terminology with Chinese conceptual support.

### Define

The core problem is not only translation quality. It is course-specific knowledge alignment with traceable evidence.

### Ideate

The design includes teacher workflows, student search, personal KB, quality control, feedback, and admin diagnostics.

### Prototype

The current prototype is a local Flask + SQLite + single-page application.

### Test

Testing uses evaluation, retrieval regression, demo flow, pilot package checks, and feedback loops.

## Project Direction Change

Before midterm, the project was closer to a translation website. After problem redefinition, it became a knowledge alignment platform. The reason was clear: generic translation lacks course context, teacher review must be reduced, and evidence traceability is essential.

## Report Paragraph Material

LexiBridge AI shows how computational thinking can turn an ambiguous education problem into modular system design. By separating OCR, retrieval, alignment, evaluation, and feedback, the project avoids treating AI output as a black box. Design thinking also shaped the project: student and teacher pain points led to a shift from simple translation to evidence-based knowledge alignment.
