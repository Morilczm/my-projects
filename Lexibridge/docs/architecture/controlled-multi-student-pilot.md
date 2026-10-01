# Controlled Multi-Student Pilot Contract

## Purpose

The controlled pilot measures whether the existing Student-first Personal
Workspace flow can be completed by multiple isolated identities without
adding telemetry to the product or creating a second alignment path. The
repository runner is a deterministic self-simulation harness; it is not a
substitute for independently consenting human participants.

## Reused production path

Each persona uses the same routes and services as a Student:

```text
explicit pilot consent
  -> Personal PDF upload (English + Chinese evidence)
  -> existing ingestion job / parser adapter
  -> governed KnowledgeSource + KnowledgeChunk
  -> authenticated reader and bounded text selection
  -> existing Student ConceptQuery
  -> existing cross-language retrieval and qualification
  -> existing PersonalLearningRecord
  -> notebook revisit
  -> pilot completion and bounded survey
```

The runner configures only the deterministic local embedding and reranker
backends already used by Browser E2E. It does not implement retrieval,
pairing, qualification, a new card store, or a new Provider transport.

## Participant and storage boundary

- Every simulated persona has a distinct Student account and Personal source
  ownership.
- The database and upload directory are created outside the repository and are
  deleted when the run exits.
- Pilot rows store only derived state, bounded duration, status, booleans and
  ratings. They do not store term text, source/chunk IDs, evidence, notes or
  raw query identifiers.
- The admin endpoint is aggregate-only and retains the existing small-cell
  suppression contract.
- A foreign persona's query completion is expected to return not-found; no
  content is disclosed.
- External API and real Provider requests are disabled and counted as zero.

## Evidence boundary

The runner uses tiny synthetic PDFs generated in memory. It proves that the
existing upload, parser, reader, ConceptQuery, learning-record and notebook
contracts compose across isolated accounts. It does not prove that real
students find the product understandable or useful.

## Quality gate

The study gate requires at least five completed sessions, completion of at
least 80%, median task duration no more than ten minutes, mean evidence
helpfulness and uncertainty understanding at least 4/5, and zero privacy or
network incidents. Self-simulated output is labelled separately from a real
participant result and cannot be reported as real-student evidence.
