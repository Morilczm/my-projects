# Reranker Design

The reranker receives only candidates that have already passed metadata hard filters.

Current provider:

- `none`: no reranking.
- `local_heuristic`: reranks by exact/alias match, lexical overlap, source quality, and prior retrieval score.

The local heuristic reranker does not call an external model and does not override evidence gates. Future cross-encoder or API-compatible rerankers should preserve this boundary.
