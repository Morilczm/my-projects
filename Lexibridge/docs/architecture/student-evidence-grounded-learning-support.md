# Evidence-grounded Student Learning Support

## Scope

Task 13C.5 adds a student learning read model to the existing one-concept
result. It does not add a Provider call, a new alignment pipeline, a knowledge
generation service or a database object. The contract is
`student-learning-support@1.0.0`, embedded in
`student-alignment-result@1.2.0`.

The feature answers four student-facing questions with bounded existing data:

- what the selected concept means in the current English course context;
- why the machine recommendation was admitted, or why it remains unresolved;
- which alternative candidates have independent Chinese evidence;
- what can safely be said about nearby candidates without inventing a semantic
  distinction.

This is an evidence presentation contract, not a claim that a generated
pedagogical explanation has been validated.

## Reused production path

Before:

```text
StudentConceptQuery
  -> governed Task 12 alignment result
  -> generic status sentence + raw bounded evidence
  -> PersonalLearningRecord
```

After:

```text
StudentConceptQuery
  -> same governed Task 12 alignment result
  -> student-alignment-result@1.2.0
       -> bounded English context citation
       -> evidence-bound Chinese candidate read model
       -> qualification-status explanation
       -> evidence side-by-side comparison
  -> same Student Concept Result component
  -> same PersonalLearningRecord
```

Personal and Managed Course results use the same service, contract and page.
Every ordinary result remains `PRIVATE / NON_OFFICIAL / NOT_APPLICABLE`.

## Grounding contract

Only an existing Chinese candidate that is non-generated, marked
evidence-backed, has a stable candidate UID and binds to an allowed
`source_uid + chunk_uid` in the result's bounded Chinese evidence may enter the
learning-support candidate list. The adapter never looks up gold, aliases or
required propositions.

Evidence snippets are capped at 360 characters. At most four source/chunk
bindings enter the learning read model. The result contains no pair score,
reranker score, qualification score, raw reason code, Provider name, Prompt
version or raw payload.

`What It Means Here` is extractive bounded English context. `Why They Align`
describes the relationship between the existing evidence and the frozen
qualification outcome; it does not invent a new semantic claim. Alternatives
carry their own Chinese citation.

## Status behavior

- `READY` becomes `EVIDENCE_GROUNDED` only when bounded English evidence,
  the selected evidence-bound Chinese candidate and the existing recommendation
  are all present. Otherwise the learning layer is `GROUNDING_INCOMPLETE`.
- `REVIEW_REQUIRED` becomes `ALTERNATIVES_UNRESOLVED`; candidates remain
  tentative and viewable, with explicit uncertainty.
- `NOT_READY` becomes `NO_RELIABLE_ALIGNMENT`; it contains no candidate
  rationale or concept comparison.
- a deleted or inaccessible source becomes `SOURCE_UNAVAILABLE`; historical
  term/status and the private learning record remain, while bounded context,
  evidence, candidates and learning explanation are redacted.

Generated translation or glossary hints remain visually separate with
`generated=true` and `evidence_backed=false`. They never enter the evidence or
comparison collections.

## Concept differentiation boundary

When a selected candidate and an alternative both have allowed evidence, the
UI may place their bounded evidence side by side. The boundary conclusion is
fixed to `UNRESOLVED` unless a future governed contrast-evidence contract is
introduced. The current service deliberately says that the evidence is
insufficient to safely summarize the conceptual boundary. It does not infer
"why not the other candidate" from ranking scores.

## Provider and persistence decision

Provider usage is fixed to `false`. No Prompt, Provider transport, model,
retrieval, pairing, qualification or readiness setting changes. No migration
is required because learning support is a deterministic projection of the
persisted immutable alignment result.

## Quality boundary

The automated suite proves deterministic grounding, privacy, status behavior
and browser continuity. It does not prove that real students understand the
wording or that the evidence-side-by-side view improves learning. Those are
explicit gates for the next real-student pilot phase.
