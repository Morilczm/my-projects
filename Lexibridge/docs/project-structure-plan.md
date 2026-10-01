# LexiBridge AI Project Structure Plan

## 1. Current Project Status

The project is currently a local prototype of the LexiBridge AI bilingual course knowledge alignment platform.

Current completed features:

- Teacher uploads course materials
- System parses documents, extracts candidate terms, retrieves bilingual evidence, and generates terminology cards
- Teacher handles Quality Control exceptions instead of reviewing every term
- Student views course terminology cards and personal workspace cards
- Student submits feedback
- Teacher resolves feedback-driven Quality Control items
- Student uses subscription quota for personal document parsing and AI alignment
- Admin manages users, courses, knowledge sources, plans, usage, billing, logs, and ingestion jobs
- Backend creates Document, DocumentChunk, KnowledgeSource, KnowledgeBaseVersion, KnowledgeChunk, and TerminologyCard records

## 2. Current Structure

Current basic structure:

LexiBridge-AI/
- backend/
  - app.py
  - requirements.txt
  - .venv/
- frontend/
  - index.html
- docs/
  - project-structure-plan.md

## 3. Current Problems

### 3.1 backend/app.py is too concentrated

The current app.py contains database models, file parsing, term extraction, feedback APIs, knowledge-base APIs, and Flask routes.

It can run now, but it should be modularized gradually before adding production RAG infrastructure, real SMTP, real payment, or cloud deployment.

### 3.2 frontend/index.html is too concentrated

The current index.html contains HTML, CSS, and JavaScript in one file.

It includes teacher-side logic, student-side logic, feedback logic, knowledge-base logic, export logic, and modal logic.

A small JavaScript syntax error may break the whole page.

### 3.3 Configuration is not separated

The project still has hard-coded configuration, such as API_BASE, database path, upload folder path, SECRET_KEY, and future AI API keys.

These should later be moved into config files or environment variables.

## 4. Target Structure

Future target structure:

LexiBridge-AI/
- README.md
- .gitignore
- .env.example
- backend/
  - app.py
  - config.py
  - models/
  - routes/
  - services/
  - utils/
- frontend/
  - index.html
  - css/
  - js/
- docs/
  - project-structure-plan.md
  - api.md
  - database.md
  - local-demo.md
  - roadmap.md
- scripts/
  - init_db.py
  - backup_db.py
  - rebuild_knowledge_index.py

## 5. Backend Refactoring Order

1. Extract configuration into config.py
2. Extract utility functions
3. Extract database models
4. Extract routes with Flask Blueprint
5. Extract AI and knowledge-base services

## 6. Frontend Refactoring Order

1. Extract API_BASE into js/config.js
2. Extract CSS into css/main.css
3. Extract common API functions into js/api.js
4. Split JavaScript by module
5. Keep the current single-page frontend for this local demo; revisit a framework only after the project scope changes

## 7. Current Restrictions

At this stage, do not:

- Move app.py
- Move index.html
- Split the main JavaScript
- Add real cloud deployment
- Delete existing files
- Introduce a frontend framework

## 8. Summary

The current project is scoped as a local, demonstrable evidence-alignment prototype.

The engineering principle is:

- Document first
- Configure second
- Refactor low-risk parts first
- Modularize gradually
- Never break a working system just to make the structure look professional
