# Schema Audit Report

Schema Audit Result: WARN
Tables checked: 40

## Issues
- [info] `alignment_run`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.
- [warn] `auth_token`: Legacy token column exists. Recommendation: Keep token_hash for production and avoid exporting raw token values.
- [warn] `background_job`: Missing explicit composite index recommendations in Local MVP schema. Recommendation: Add Alembic indexes for status/priority and course_id+normalized_english_term.
- [info] `courseware_upload`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.
- [warn] `document`: Legacy local path fields remain: saved_filename. Recommendation: Prefer storage_key + StorageObject; keep legacy fields read-only for compatibility.
- [info] `document`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.
- [warn] `formula_block`: Legacy local path fields remain: image_path. Recommendation: Prefer storage_key + StorageObject; keep legacy fields read-only for compatibility.
- [info] `ingestion_job`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.
- [info] `student_term_record`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.
- [info] `subscription_plan`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.
- [info] `term`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.
- [warn] `terminology_card`: Missing explicit composite index recommendations in Local MVP schema. Recommendation: Add Alembic indexes for status/priority and course_id+normalized_english_term.
- [info] `user_subscription`: created_at not present. Recommendation: Add created_at in future Alembic migration if lifecycle tracking is needed.

## Recommendations
- Introduce Flask-Migrate/Alembic before staging PostgreSQL.
- Add composite indexes for course/term lookup and job queues.
- Keep SQLite compatibility for local pilot usage.
- Migrate file_path/saved_filename/image_path to storage_key-backed records.
