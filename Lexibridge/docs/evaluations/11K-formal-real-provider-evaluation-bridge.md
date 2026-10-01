# Task 11K Formal Real-Provider Evaluation Bridge

## Status

`FORMAL_REAL_PROVIDER_EVALUATION_BRIDGE_CLOSED`

Task 11K made no real Provider request. The bridge was developed and verified
with policy decisions and offline transports only.

## Root cause

The real-provider evaluation policy successfully validated the explicit gate,
evaluation identity, runner identity, frozen hashes, isolated database,
request budget, provider/model allowlists, feature enablement, and credential
presence. Its decision ended at the caller.

The Formal Workflow then applied two independent production-only checks:

1. `resolve_formal_document_alignment_provider_selection` accepted only
   `mock-rule-v1`.
2. `_persisted_provider_selection` accepted only mock, fake, or replay
   providers and rejected any provider advertising external calls.

No trusted evaluation decision was passed to workflow admission, processing
composition, or item preparation. The provider factory and
`DeepSeekHTTPTransport` were therefore unreachable even after the outer gate
allowed evaluation.

## Original call chain

`evaluation gate -> decision returned to caller`

Separately:

`Formal admission -> mock-only selection -> persisted selection ->
item preparation local/replay-only check -> provider factory -> transport`

The evaluation context was lost immediately after the policy gate. Selection
and preparation consequently behaved as two independent, inconsistent
allowlists.

## Fixed call chain

`evaluation gate -> sealed capability -> Formal admission selection ->
persisted selection -> item preparation -> provider factory -> transport`

Admission and processing receive the same in-memory capability object. No
database schema or request payload field was added.

## Trust boundary

The policy-issued capability is a frozen decision bound to:

- evaluation ID and runner ID;
- provider ID and model;
- frozen corpus and gold hashes;
- bounded request budget;
- synthetic-only status;
- repository-external database isolation.

The policy module marks an allowed decision with a private module-owned seal.
Selection and preparation require that seal and re-check all bound identities.
A caller-created decision, arbitrary boolean, JSON field, query parameter, or
header cannot satisfy the bridge.

The ordinary application does not pass an evaluation capability. Its default
remains `mock-rule-v1`; external providers remain rejected by ordinary Formal
selection and item preparation. DeepSeek is not a production default.

## Test-first evidence

RED, before production changes:

- `2 passed, 9 failed`
- failures showed the missing synthetic-only policy binding, evaluation
  selection context, and preparation propagation interfaces.

GREEN:

- bridge contract: `11 passed`
- required DeepSeek config/transport, policy, bridge, and metrics set:
  `41 passed`
- focused Formal selection, preparation, admission, processing, and adapter
  regression set: `48 passed` after preserving the existing replay path
- real Provider requests: `0`

## Safety

- No Prompt, retrieval, candidate extraction, transport protocol, frontend,
  parser/OCR, schema, migration, seed, card state machine, or release-safety
  rule changed.
- Real Provider requests: `0`
- Private data egress: `0`
- Secret exposure: `0`
- Accident database SHA-256, size, mtime, and absent WAL/SHM state matched the
  frozen values after testing.
- Release safety: passed.
