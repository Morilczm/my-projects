# Prompt Versioning

## Registry

`PromptTemplate` records every governed prompt:

- `prompt_key`
- `prompt_version`
- `task_type`
- `language`
- `template_text`
- `json_schema`
- `is_active`
- `is_default`
- author and notes metadata

Default prompts are registered with:

```bash
python scripts/register_default_prompts.py
```

The script is idempotent. It does not overwrite existing prompt text unless `--force` is used.

## Default Prompt Keys

- `term_extraction` version `v1`
- `term_alignment` version `v1`
- `feedback_classification` version `v1`

## Governance Rules

Prompt output must be JSON and must match the registered schema. `term_alignment_v1` only allows alignment statuses from the system enum, such as `exact_match`, `no_zh_evidence`, `domain_mismatch`, and `unverified_translation`.

Prompt changes must be treated like model changes:

1. Register the new prompt version.
2. Run evaluation on the smoke set.
3. Review false positives and no-evidence forced alignment.
4. Only then mark it as default.

## Rollback

Rollback is done by marking the older prompt as default again. The previous prompt remains in the registry so existing `AlignmentRun`, `EvaluationRun`, and `TerminologyCard` records remain traceable.
