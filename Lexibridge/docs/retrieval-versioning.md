# Retrieval Versioning

KnowledgeBaseVersion records:

- `index_backend`
- `index_version`
- `retrieval_version`
- `embedding_provider`
- `embedding_model`
- `embedding_dimension`
- `vector_index_status`

RetrievalRun records the query, KB version, retrieval version, index version, result count, and top score. TerminologyCard continues to store evidence snapshots and KB version ids.

Default retrieval should not be switched to vector/hybrid without a retrieval experiment and teacher/admin review.
