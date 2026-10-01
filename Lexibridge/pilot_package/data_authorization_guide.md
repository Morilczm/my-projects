# Data Authorization Guide

## Materials Suitable For Upload

- Teacher-created slides and notes.
- Teacher-permitted course handouts.
- Open-license materials.
- Public-domain references.
- Self-authored demo materials.
- Student personal materials for private use.

## Materials Requiring Caution

- Full published textbooks.
- Third-party platform downloads.
- Files containing student personal information.
- Unreleased exams or answer keys.
- Materials with unclear copyright or license status.

## Source Metadata

`source_type` describes origin, such as `lecture_notes`, `textbook_excerpt`, `teacher_upload`, `student_personal_upload`, `open_reference`, `platform_seed`, or `demo_seed`.

`license_type` describes use basis, such as `teacher_provided`, `open_license`, `public_domain`, `demo_synthetic`, `restricted`, or `unknown`.

`authorization_status` controls evidence use:

- `allowed_for_course_use`: can be used in course KB.
- `allowed_for_private_use`: private use only.
- `metadata_only`: record metadata but avoid full evidence use.
- `restricted_no_derivative`: must not generate public course terminology evidence.
- `unknown`: requires review and lowers source quality.

`source_quality` influences evidence scoring. Unknown or deprecated sources should not create strong evidence.

## Data Use Boundary

Teacher course materials are used only for the selected course KB. Student personal materials are used only for that student personal KB. Restricted sources cannot generate public course cards. Demo synthetic data is for demonstration and does not represent real licensed course materials.

Before a real pilot, the teacher or course owner must confirm material use permission.
