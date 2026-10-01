# Task 11L Evidence-Qualified Provider Preflight

## Status

`EVIDENCE_QUALIFIED_PROVIDER_PREFLIGHT_CLOSED`

Real Provider requests during Task 11L: `0`.

## Momentum failure chain

The frozen system concept supplied the English query `momentum`. Chinese
candidate extraction returned three system candidates; the top candidate was
the system-generated phrase beginning with angular momentum. Chinese retrieval
returned one candidate. English retrieval returned no candidate, although the
frozen English mechanics source and active chunks containing momentum existed.

Formal item preparation applies the existing predicate:

`source-scoped English refs >= 1 AND Chinese refs >= 1`

For momentum the actual counts were `0` and `1`. Candidate extraction therefore
completed, filtering did not remove a retrieved English hit (there was no
English hit), and the earliest failure was English retrieval. Primary
attribution remains `ENGLISH_RETRIEVAL_DEFECT`, not
`CANDIDATE_EXTRACTION_DEFECT`.

Only chunk/source identifiers and scores were inspected; full source text was
not recorded.

## Provider-free readiness

The scan used frozen ingestion, the production candidate/retrieval services,
the workflow source scope, and the existing Formal preparation sufficiency
predicate. The evaluation scanner calls injected
`prepare_document_alignment_item` results and contains no copied threshold.
No verification collaborator or Provider was invoked.

| Concept | Preparation | Ready | Candidates | EN refs | ZH refs | Rejection |
| --- | --- | --- | ---: | ---: | ---: | --- |
| physics-01 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-02 | evidence_insufficient | false | 2 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-03 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-04 | evidence_insufficient | false | 2 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-05 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-06 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-07 | evidence_insufficient | false | 3 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-08 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-09 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-10 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-11 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-12 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-13 | evidence_insufficient | false | 2 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-14 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-15 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-16 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-17 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-18 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-19 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-20 | evidence_insufficient | false | 1 | 0 | 1 | DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT |
| physics-21 | prepared | true | 1 | 5 | 1 | - |
| physics-22 | prepared | true | 1 | 5 | 1 | - |
| physics-23 | prepared | true | 1 | 5 | 1 | - |
| physics-24 | prepared | true | 1 | 4 | 1 | - |
| physics-25 | prepared | true | 1 | 1 | 1 | - |

- Formal provider ready: `5/25`
- Formal provider not ready: `20/25`
- Gold-scored valid-evidence subset: `6/25`

Formal readiness is an operational transport-admission predicate. Gold valid
evidence is a scoring metric. They intentionally remain separate.

## Semantics

Previously, fixed momentum insufficiency stopped the whole evaluation before
testing the Provider. The deterministic selector now picks the first ready
concept in frozen order: `physics-21`, with reason
`first_provider_ready_in_frozen_order`. It accepts no gold object, aliases,
propositions, or scores.

During the batch, not-ready items become `upstream_not_ready`,
`provider_called=false`, retain their earliest upstream attribution, remain in
the all-25 denominator, and do not stop later items. A successful preflight
result is reused for its concept. Only explicit systemic Provider/capability or
budget failures stop continuation.

## Test-first evidence and safety

- RED: `5 failed`, all due to missing readiness/selector/continuation APIs.
- GREEN: `5 passed`.
- Required combined regression: `46 passed`.
- Related Formal/API group: `30 passed, 1 order-dependent job-mismatch
  failure`; the affected ordinary route integration passed alone (`1 passed`).
- Real Provider requests: `0`.
- Ordinary application paths do not expose the selector or evaluation
  capability and retain `mock-rule-v1`.
- No retrieval, candidate extraction, ranking, threshold, Prompt, transport,
  schema, state machine, or API behavior changed.
- Release safety: passed.
- Accident database SHA-256, size, mtime, and absent WAL/SHM state were
  unchanged.

## R3 preflight follow-up

The first real preflight exposed two additional verification-stage gates after
Formal preparation: the item verification adapter admitted only offline
provider types, and provider preflight treated enabled external calls as
unconditionally unsafe. Both now use the same sealed evaluation context already
validated by the 11K bridge. Without that context, their original denial
behavior is unchanged.

The deterministic `physics-21` preflight then reached
`DeepSeekHTTPTransport` and received one successfully parsed response. Term
pair, confidence, and evidence references were persisted, but the explanation
was absent from the persisted verification output. This is a downstream
`WORKFLOW_OR_PERSISTENCE_DEFECT`, not an evidence-readiness or Provider
failure. Because explanation persistence is a required systemic preflight
check, the 25-item run was not started.
