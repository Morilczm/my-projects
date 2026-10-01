# Source Governance

## Fields

`KnowledgeSource` records:

- `source_type`
- `license_type`
- `authorization_status`
- `status`
- `source_quality`
- introduced/removed version IDs

## Authorization

`restricted_no_derivative` sources cannot generate public course card evidence. `student_personal_upload` sources remain private and cannot be merged into course public KB.

## Lifecycle

- `active`: eligible for retrieval.
- `deprecated`: can appear as weak evidence only.
- `removed` / `archived`: excluded from new retrieval.
- `pending_review`: should be reviewed before publication.

## Source Quality

Source quality contributes to evidence score. Unknown authorization and deprecated sources lower evidence strength.
