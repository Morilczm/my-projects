# Privacy And Risk Notice

本文件说明试点中的隐私边界、AI/OCR 风险、术语对齐风险和非生产部署限制。

## Data Collected During A Pilot

The system may store user accounts, course membership, uploaded file metadata, parsed text chunks, terminology cards, feedback, job records, evaluation metrics, usage records, and redacted logs.

## Purpose

Data is used to build a course terminology knowledge base, align bilingual terminology, support student learning, collect feedback, and evaluate system quality.

## Personal Materials

Student personal uploads are private to the student account and must not be added to the course public knowledge base without explicit future authorization.

## Logging

Logs should store ids, counts, provider names, status, errors, and short redacted previews. Logs should not store passwords, full tokens, full secrets, full student files, full OCR text, full AI prompts, or full AI responses.

## AI Provider Risk

If a live AI provider is used, prompts may leave the local machine depending on provider configuration. This must be reviewed before using real student or sensitive course data.

## OCR And Formula OCR Risk

OCR can misread scanned text. Formula OCR can fail or be unavailable. Low-confidence OCR and missing formula evidence should be treated as risk signals.

## Terminology Risk

LexiBridge AI 的术语卡片需要结合 evidence、status、risk_note 和教师审核状态使用。系统输出不应被视为不可更改的标准答案。

The system does not guarantee every term is fully correct and does not replace teacher judgment.

## Feedback Flow

Student feedback is reviewed by teachers or admins. Feedback can move a card back into QC, create an evaluation item, or create backlog work. Feedback does not directly approve or edit cards.

## Deployment Risk

The current project is a local pilot-ready system, not production deployment.
