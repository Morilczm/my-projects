# RAG Retrieval Architecture

LexiBridge AI now treats retrieval as a pluggable service layer. The default remains `lexical`, and optional vector, hybrid, and rerank modes are gated behind configuration and evaluation.

## Backends

- `lexical`: current metadata hard filter plus local lexical evidence scoring.
- `vector`: embedding lookup against a version-scoped vector index, followed by the same evidence gate.
- `hybrid`: lexical and vector candidates are fused with explicit lexical and vector scores.
- `hybrid_rerank`: hybrid candidates are reranked by a reranker provider.

## Hard Filter First

All backends receive only candidates that already passed course/scope/owner/language/KB type/version/source governance filters. Vector search and reranking never restore filtered-out chunks.

## No Fallback Policy

If no evidence passes thresholds, the API returns an empty list. Vector service failure does not create fabricated evidence; vector/hybrid modes either return empty/skipped results or use lexical-only behavior depending on the caller.

## Score Breakdown

Evidence results expose `lexical_score`, `vector_score`, `hybrid_score`, `rerank_score`, `evidence_score`, `retrieval_backend`, `retrieval_version`, and `index_version`.

## Scope Isolation

Course KB, personal KB, and global KB remain isolated. Personal chunks require owner match; restricted sources cannot become public strong evidence.
