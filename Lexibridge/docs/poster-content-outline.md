# Poster Content Outline

## Title

LexiBridge AI: Evidence-Based Bilingual Course Terminology Alignment

## Problem

Students in transnational education often read English course materials but need Chinese conceptual support. Generic translation tools lack course-specific evidence.

## User Pain Points

- Students cannot judge whether a translation is correct.
- Teachers repeatedly prepare terminology explanations.
- Course materials are split across English and Chinese sources.

## Project Evolution

Translation website -> course knowledge alignment platform.

## System Workflow

Upload materials -> parse/OCR -> build KB -> retrieve evidence -> align terms -> generate cards -> teacher QC -> student use -> feedback -> evaluation.

## Core Modules

OCR, FormulaBlock, KnowledgeBaseVersion, RetrievalBackend, TerminologyCard, AlignmentRun, EvaluationRun, PilotFeedback.

## Computational Thinking

Decomposition, abstraction, algorithmic scoring, state machines, evaluation, regression testing.

## Design Thinking

Empathize, define, ideate, prototype, test, iterate.

## Prototype Features

Teacher upload, student search, QC, evidence cards, feedback, evaluation, retrieval diagnostics.

## Evaluation Metrics

Extraction precision/recall, evidence accuracy, alignment accuracy, false positive rate, `no_evidence_forced_alignment_rate`, retrieval experiment metrics.

## Pilot Plan

Small pilot with 1-3 courses, 5-30 students, teacher-reviewed materials, feedback loop.

## Limitations

Local pilot-ready only, not production-ready; local demo vector retrieval is not production semantic search.

## Future Work

Production database, object storage, production queue, real provider configuration, larger teacher-reviewed gold set.
