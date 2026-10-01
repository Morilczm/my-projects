# Retrieval Regression Specification

## Case Sources

Regression cases can come from:

- `EvaluationItem`
- demo gold terms
- pilot feedback converted to evaluation items
- manual regression cases

## Checks

Each case may define:

- positive expected evidence
- negative evidence that must not appear
- no-evidence expectation

The regression runner checks top results, negative leakage, and no-evidence forced matches.

## Publish Gate

If regression fails, the KB version should not be automatically published. For non-published candidate versions, the Local MVP writes `quality_gate_status=fail` and stores the regression summary in the version manifest so the publish gate can block the version until it is fixed or explicitly rebuilt.
