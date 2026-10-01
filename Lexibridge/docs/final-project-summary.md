# LexiBridge AI Pilot v1.0 Candidate Summary

## Project Name

LexiBridge AI

## Background

Transnational education courses often use English lectures and materials while students rely on Chinese explanations. The main challenge is not simple word translation; it is aligning professional concepts across English and Chinese course knowledge.

## Original Problem

The early idea resembled a bilingual translation website. During iteration, the team found that direct translation cannot solve evidence traceability, course context, teacher workload, and terminology quality control.

## Project Shift

The project shifted from an AI translation tool to an AI retrieval, translation, and evidence alignment platform.

## Core Users

- English and Chinese course teachers.
- Students in transnational education programs.
- Local administrators and pilot owners.

## Core Capabilities

- Multi-format document parsing.
- Image text OCR.
- Formula OCR architecture and FormulaBlock storage.
- Course and personal knowledge bases.
- Evidence retrieval with hard filters.
- Bilingual terminology alignment.
- Formal asynchronous document-alignment runs with status polling and
  server-paginated items.
- Terminology card quality control.
- Student feedback and learning marks.
- Evaluation harness and retrieval regression.
- Pilot feedback loop and iteration backlog.

## Technical Overview

The local MVP uses Flask, SQLite, a single-page HTML/CSS/JS frontend, local jobs, structured services, an OpenAPI contract, and local release checks. Its formal teacher workflow uses governed `KnowledgeSource` identity, `DocumentAlignmentWorkflowRun`, `DocumentAlignmentWorkflowItem`, background processing, idempotent admission, run polling, and server-side item pagination. Legacy `AlignmentRun` data and routes remain for compatibility and controlled deprecation.

## Current Version Boundary

The system is the LexiBridge AI Pilot v1.0 Candidate, classified as a
Controlled Academic Pilot Release. It is not a production SaaS, public release,
commercial deployment, or production-ready system. Production would require
PostgreSQL and Alembic migration proof, object storage, a supervised production
queue and worker runtime, distributed lease validation, live-provider
governance, formal privacy operations, HTTPS, monitoring, and backup/restore
drills.

## Pilot Readiness

The repository includes demo data, runbooks, manuals, metrics, feedback templates, pilot report templates, and final presentation materials. Task 9C.5K re-verifies the Task 9C.5H teacher cutover through the real formal start/run/items APIs, duplicate-submit protection, terminal-state rendering, item pagination, and refresh recovery. The verified formal path has no legacy POST fallback and makes no external provider request.

Current readiness is `READY_WITH_CONDITIONS`. The candidate is suitable for a
controlled local pilot using authorized materials, deterministic/local provider
behavior, and the documented operational checks. Task 9C.5L finds no remaining
production frontend consumer of the legacy alignment POST, but the legacy
worker, compatibility tests, readiness probes, OpenAPI contract, and unknown
external clients keep it as an active compatibility surface. This candidate
does not authorize deprecation, HTTP 410, or removal.

## Next Plan

- Run a small real-course pilot with authorized materials.
- Expand teacher-reviewed evaluation sets.
- Replace local demo retrieval with evaluated production retrieval.
- Complete production database, object storage, and queue migration.
