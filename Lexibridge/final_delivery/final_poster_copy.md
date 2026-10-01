# Final Poster Copy

## Title

LexiBridge AI: Evidence-Based Bilingual Course Knowledge Alignment

## Subtitle

From AI Translation Website to AI Knowledge Alignment Platform for Transnational Education.

## Problem

Students read English course materials but often need Chinese professional knowledge support. Generic translation tools do not show course evidence or teacher-approved context.

## Insight

The real problem is not a single word translation. It is aligning English course concepts with Chinese disciplinary knowledge in a traceable and reviewable way.

## Project Evolution

The project started as a translation website. After midterm feedback and course reflection, it became a knowledge alignment platform with retrieval, evidence, QC, evaluation, and feedback.

## System Workflow

Upload course materials -> OCR and parsing -> KnowledgeBaseVersion -> Evidence Retrieval -> TerminologyCard -> Teacher QC -> Student Search -> Feedback -> Evaluation Regression.

## Key Features

- OCR and FormulaBlock support.
- Evidence retrieval with hard filters.
- Alignment status and confidence score.
- Teacher quality control.
- Student favorite/mastered/feedback.
- Evaluation Harness and retrieval regression.
- Pilot package and final delivery materials.

## Computational Thinking

Decomposition, abstraction, algorithmic thinking, evaluation, and iteration are reflected in modules such as KnowledgeChunk, TerminologyCard, BackgroundJob, EvaluationItem, and retrieval score fusion.

## Design Thinking

Empathize with students and teachers, define the issue as knowledge alignment, ideate three-role workflows, prototype a local MVP, and test with demo flow, evaluation metrics, and pilot feedback.

## Evaluation

Metrics include extraction precision/recall, evidence accuracy, alignment accuracy, false positive rate, auto-approval error rate, `no_evidence_forced_alignment_rate`, and retrieval experiment metrics.

## Pilot Plan

Start with 1 course, teacher-authorized materials, 5-30 students, teacher QC, student feedback, and a post-pilot report.

## Limitations

Local pilot-ready only. Not production-ready. Demo data is synthetic. Real course accuracy requires teacher review, authorization, and continued evaluation.

## Future Work

PostgreSQL, object storage, production queue, real provider configuration, formal privacy policy, real course gold set, and broader pilot feedback.
