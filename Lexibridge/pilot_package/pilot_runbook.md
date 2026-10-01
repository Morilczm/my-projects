# Pilot Runbook

## Pilot Goal

本试点用于验证 LexiBridge AI 是否能在中外合作办学课程中提升学生对英文专业术语的理解效率，降低教师整理术语表的重复劳动，并检验 AI 检索、翻译与证据对齐机制的可靠性。

The pilot validates whether LexiBridge AI improves bilingual terminology understanding with traceable evidence and manageable teacher review effort.

## Recommended Scope

- Courses: 1-3.
- English materials per course: 1-3 files.
- Chinese reference materials per course: 1-3 files.
- Students: 5-30.
- Teachers: 1-3.
- Duration: 1-2 weeks.
- Avoid full-school rollout during the first trial.

## Phase 0: Before The Pilot

Owner: pilot lead and admin.

Inputs: course list, teacher accounts, student accounts, authorized material inventory, privacy notice, backup plan.

Steps:

1. Run migration, tests, release check, and environment checks.
2. Confirm OCR, Formula OCR, and AI provider status.
3. Create trial courses and accounts.
4. Confirm material authorization with teachers.
5. Run `scripts/check_pilot_package.py`.
6. Back up local data before importing real materials.

Outputs: ready course shell, account list, authorization record, pre-pilot checklist.

Risks: unclear material authorization, wrong environment, default test accounts used for real students.

Acceptance: all pre-pilot checklist items are reviewed and unresolved risks are recorded.

## Phase 1: Material Import And KB Build

Owner: teacher with admin support.

Inputs: English course notes, Chinese references, formula/image samples if relevant.

Steps:

1. Upload English materials as `en_course_kb`.
2. Upload Chinese materials as `zh_course_kb`.
3. Check document parsing jobs.
4. Check OCR and FormulaBlock warnings.
5. Create or rebuild KnowledgeBaseVersion.
6. Run knowledge health check.

Outputs: parsed DocumentChunks, FormulaBlocks, active KnowledgeSource records, candidate KB version.

Risks: OCR unavailable, formula OCR unavailable, low Chinese KB coverage, restricted source used incorrectly.

Acceptance: KB version has chunks, source authorization is reviewed, and health status is not FAIL.

## Phase 2: Alignment And Teacher QC

Owner: teacher.

Inputs: published or candidate KB version and parsed materials.

Steps:

1. Trigger AlignmentRun.
2. Review AlignmentRun statistics.
3. Open Quality Control.
4. Filter `needs_more_evidence`, `domain_mismatch`, `ocr_low_confidence`, and `formula_evidence_missing`.
5. Approve only cards with convincing evidence.
6. Reject or mark needs-more-evidence when evidence is weak.

Outputs: reviewed terminology cards, QC notes, revised cards.

Risks: approving pending cards without evidence, ignoring risk notes, treating mock/local AI as verified.

Acceptance: teacher can explain why selected cards are approved or not approved.

## Phase 3: Student Trial

Owner: students with teacher support.

Inputs: visible course cards and student manual.

Steps:

1. Students join or select the course.
2. Search core English terms.
3. Read Chinese term, explanation, evidence, status, and risk note.
4. Favorite and mark mastery.
5. Submit feedback for wrong translation, wrong evidence, missing term, or unclear explanation.
6. Optionally upload personal study material to private KB.

Outputs: usage records, feedback, learning marks.

Risks: students using unverified cards as final answers, personal files uploaded to course KB by mistake.

Acceptance: students can find core terms and understand which cards are verified or risky.

## Phase 4: Feedback And Regression

Owner: teacher and admin.

Inputs: PilotFeedback, QC queue, EvaluationSet.

Steps:

1. Triage high-severity feedback.
2. Resolve or reject feedback with notes.
3. Convert important feedback to EvaluationItem.
4. Convert product/data issues to IterationBacklogItem.
5. Run evaluation and retrieval regression.

Outputs: corrected cards, regression cases, backlog items.

Risks: feedback is collected but not turned into test cases or backlog.

Acceptance: important feedback is traceable to a card, evaluation item, or backlog item.

## Phase 5: Review And Next Iteration

Owner: pilot lead.

Inputs: pilot metrics, pilot report, evaluation results, backlog.

Steps:

1. Generate pilot report.
2. Compare actual metrics with pilot success criteria.
3. Identify top data gaps, retrieval issues, OCR issues, and UI issues.
4. Prioritize P0/P1/P2/P3 backlog.
5. Decide next trial scope.

Outputs: final pilot report, next iteration plan.

Risks: overclaiming success based on demo metrics.

Acceptance: report includes failures and limitations, not only positive results.

## Success Standards

- Students can search and understand core English terminology.
- Teachers can judge terminology cards using evidence, score breakdown, and risk status.
- No-evidence forced alignment rate is 0.
- Student personal documents do not enter public course KB.
- Feedback can move cards back into QC and generate evaluation/backlog items.
