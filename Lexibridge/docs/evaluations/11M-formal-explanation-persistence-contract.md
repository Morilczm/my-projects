# Task 11M Formal Explanation Persistence Contract Closure

## Status

`FORMAL_EXPLANATION_PERSISTENCE_CONTRACT_CLOSED`

Real Provider requests during Task 11M: `0`.

## Presence trace

The previous real preflight retained only sanitized summaries. It established
that the Provider response parsed successfully and that the normalized result
contained a nonempty explanation; the exact real explanation length was not
retained and was not reconstructed. The offline schema-equivalent regression
uses a 125-character explanation.

| Boundary | Field | Type | Present/nonempty | Sanitized length | File/function |
| --- | --- | --- | --- | ---: | --- |
| Transport parsed response | `explanation` | `dict` | true/true | nonzero; exact real length not retained | `alignment_providers.py`, `DeepSeekAlignmentProvider.verify_alignment` |
| Provider parser | `explanation` | `dict` | true/true | bounded to 2000 | `alignment_output_parser.py`, `normalize_alignment_output` |
| Normalized provider result | `explanation` | `dict` | true/true | 125 in offline proof | `alignment_providers.py`, provider `verify_alignment` |
| Safe persistence mapping before fix | absent | `dict` | false/false | 0 | `alignment_verification.py`, `build_safe_alignment_verification_persistence` |
| Verification ORM output payload before fix | absent | JSON text | false/false | 0 | `alignment_verification.py`, `create_safe_alignment_verification_run` |
| New-session reload before fix | absent | `AlignmentVerificationRun` | false/false | 0 | ORM reload of `output_payload` |
| Verification serializer before fix | absent | `dict` | false/false | 0 | `alignment_verification.py`, `serialize_alignment_verification_run` |
| Safe persistence mapping after fix | `explanation` | `dict` | true/true | 125 in offline proof | `build_safe_alignment_verification_persistence` |
| New-session reload after fix | `output_payload.explanation` | JSON text | true/true | 125 | `AlignmentVerificationRun` reload |
| Verification serializer after fix | `explanation` | `dict` | true/true | 125 | `serialize_alignment_verification_run` |

The ConceptAlignmentCard schema already contains `english_explanation`,
`chinese_explanation`, and `alignment_reason`. The Formal verification contract
is attach-only: Provider verification text belongs to the persisted
`AlignmentVerificationRun.output_payload`, rather than overwriting the draft
card's authored explanation fields. No schema, migration, duplicate storage, or
state-machine change is required.

## Root cause and correction

The earliest true-to-false boundary was
`build_safe_alignment_verification_persistence`. The provider parser had
already produced a bounded nonempty explanation, but the safe-output whitelist
did not copy it. This is a `FORMAL_RESULT_MAPPING_DEFECT` under the existing
top-level `WORKFLOW_OR_PERSISTENCE_DEFECT`.

The minimal correction:

- copies the already-sanitized explanation into the bounded safe output;
- rejects an empty explanation for a successful/needs-review verification;
- permits controlled failed verification records to persist without inventing
  an explanation;
- projects the persisted explanation from the verification serializer;
- does not store a raw Provider response or full request.

## Test-first evidence

- RED: `2 failed, 2 passed`; failures were the missing persisted key and an
  empty successful explanation being accepted.
- GREEN: `4 passed`.
- Required Formal, Provider, persistence, reload, card, and API-boundary
  regression: `105 passed`.
- The test commits, removes the session, reloads
  `AlignmentVerificationRun`, and compares the persisted and serialized
  explanation with the normalized result.
- Real Provider requests: `0`.
- Ordinary production Provider admission remains unchanged.
- Accident database SHA-256, size, mtime, and absent WAL/SHM state remained
  unchanged.
- Release safety: passed.
