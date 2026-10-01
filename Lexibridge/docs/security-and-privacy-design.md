# Security And Privacy Design

This document describes the Local MVP security boundaries. It is not a production threat model, but it defines the regression checks required before a course-demo release.

## Authentication

Core APIs require:

```text
Authorization: Bearer <token>
```

Tokens are stored hashed when possible, have expiry, and are revoked on logout. Missing tokens return `AUTH_REQUIRED`; expired tokens return `TOKEN_EXPIRED`.

Passwords are stored with Werkzeug password hashing. Plaintext passwords must never be persisted.

## Roles

Supported roles:

- `student`
- `teacher`
- `admin`

Role boundaries:

- Student: joined course cards, own personal workspace, own usage/subscription.
- Teacher: own courses, course uploads, course QC, course feedback/evaluation sets.
- Admin: global management, system logs, usage, billing, evaluation and audit views.

Regression tests:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_auth.py tests/test_permissions.py
```

## Personal Knowledge Privacy

Student personal uploads are stored with:

```text
scope_type=personal
knowledge_base_type=student_personal_kb
visibility=private
owner_user_id=<student id>
```

Privacy rules:

- Student A can search Student A personal chunks.
- Student B cannot search Student A personal chunks.
- Teachers cannot search student personal chunks by default.
- Personal cards do not enter the course public terminology list.
- Admin access to another user's private resources writes `PersonalAccessAudit`.
- `owner_user_id` request parameters cannot be used by non-admin users to override ownership.

Regression tests:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_personal_privacy.py
```

## Course Scope

Course documents and evidence require course membership or course management permission:

- Students must be course members to read course cards/documents.
- Teachers can manage courses where they are `teacher_id` or a course teacher member.
- Teachers cannot search or manage another teacher's course.
- Admin can access all course data.

## Upload Security

Allowed upload extensions:

```text
pdf, docx, pptx, txt, md, png, jpg, jpeg
```

Rejected examples:

```text
exe, bat, sh, js, html, php, docm, xlsm, zip
```

Controls:

- Flask `MAX_CONTENT_LENGTH` enforces size limit.
- Saved filenames are randomized and sanitized with `secure_filename`.
- Extension and file signature are checked.
- Path traversal filenames are not written outside the upload directory.
- Failed upload/parsing does not create terminology cards.
- OCR and Formula OCR unavailable cases return structured 422 errors, not 500.
- Upload logs avoid full document text.

Regression tests:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_upload_security.py
```

## Background Job Privacy

Long-running workflows are represented by `BackgroundJob` and `BackgroundJobEvent`.

Visibility rules:

- Student can view/cancel/retry only jobs they created or jobs whose `owner_user_id` is their account.
- Teacher can view/cancel/retry jobs they created and jobs attached to courses they manage.
- Admin can view/cancel/retry all jobs.

Personal document ingestion jobs keep `scope_type=personal` and `owner_user_id`, so job status APIs do not expose another student's private upload status or filenames to students/teachers.

Regression tests:

```bash
backend/.venv-macos/bin/python -m pytest tests/test_jobs.py tests/test_job_api.py tests/test_worker.py
```

## OCR And Formula OCR Safety

`OCR_PROVIDER=none` and `OCR_PROVIDER=mock` do not fabricate text. `FORMULA_OCR_PROVIDER=none` and `FORMULA_OCR_PROVIDER=mock` do not fabricate LaTeX.

Formula recognition results are saved as `FormulaBlock`; formulas are not used as `english_term` candidates.

## Secret Handling

Secrets belong in `.env`, not in source files or release packages. The release checker scans for:

- `.env`
- database files
- upload directories
- cache directories
- virtual environments
- Mac metadata
- personal local paths
- `sk-...` style API keys

Run:

```bash
bash scripts/package_release.sh
```
