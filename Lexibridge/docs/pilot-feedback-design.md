# Pilot Feedback Design

LexiBridge AI uses pilot feedback as a controlled improvement loop, not as an automatic approval path.

## Workflow

```text
Student/teacher reports an issue
-> PilotFeedback is created
-> severity/type are normalized
-> classification/root_cause are assigned by rules
-> high-risk feedback moves the linked TerminologyCard to QC
-> teacher/admin triages and resolves
-> selected feedback becomes EvaluationItem or IterationBacklogItem
-> evaluation regression and pilot report summarize the next iteration
```

## Feedback Types

```text
translation_error
evidence_error
concept_explanation_error
missing_term
wrong_term_extraction
ocr_error
formula_ocr_error
ui_confusion
permission_issue
performance_issue
export_issue
other
```

## Severity

```text
low       UI or wording issue
medium    affects understanding but not major correctness
high      clear term, evidence, or explanation error
critical  privacy/security, severe misguidance, or crash
```

## Status

```text
submitted
triaged
in_review
needs_more_evidence
resolved
rejected
converted_to_backlog
converted_to_evaluation_item
closed
```

## Privacy

Reports and exports use anonymized student labels. Pilot reports must not include full student emails, tokens, API keys, uploaded personal document text, or full OCR/AI prompt text.
