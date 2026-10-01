# Model Registry

## Purpose

`AIModelRegistry` stores governed model metadata and links model selection to evaluation results. This prevents an untested live model from silently producing auto-approved terminology cards.

## Fields

Important fields include:

- `provider_name`
- `model_name`
- `model_version`
- `provider_mode`
- model capabilities
- token limits
- token cost estimates
- `is_enabled`
- `is_default_for_provider`
- `last_evaluation_run_id`
- `last_evaluation_score`
- `known_risks_json`

## Auto-Approval Eligibility

`can_use_model_for_auto_approval(provider_name, model_name, prompt_version)` requires:

- provider mode is `live`
- model is enabled
- prompt is active
- a recent evaluation run exists
- `no_evidence_forced_alignment_rate == 0`
- `alignment_accuracy` meets the configured threshold
- `auto_approval_error_rate` is under the configured threshold

If any gate fails, the model may still support drafting candidates, but generated cards must remain in QC or evidence-needed states.

## Switching Models

Before changing a default model:

1. Register the model.
2. Run the evaluation harness.
3. Compare metrics to the previous model.
4. Record risks in `known_risks_json`.
5. Update default only after review.
