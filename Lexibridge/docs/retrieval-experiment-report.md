# Retrieval Experiment Report

Retrieval experiments compare:

- `lexical`
- `vector`
- `hybrid`
- `hybrid_rerank`

Metrics:

- `top1_accuracy`
- `top3_accuracy`
- `top5_accuracy`
- `negative_match_error_rate`
- `no_evidence_forced_match_rate`
- `mean_reciprocal_rank`
- `average_latency_ms`
- `empty_result_rate`
- `restricted_source_violation_count`
- `personal_leakage_count`

Promotion is not automatic. A backend can only be recommended if it improves top1 accuracy, does not increase negative matches, keeps no-evidence forced matches at zero, and has no privacy/source-governance violations.
