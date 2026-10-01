# Vector Index Design

## Provider Abstractions

`EmbeddingProvider` supports:

- `none`: unavailable; no vectors are generated.
- `local_hash_embedding`: deterministic local vectors for tests and demos only.
- `openai_compatible`: future API-compatible embedding provider boundary.

`VectorIndexBackend` supports:

- `none`: unavailable.
- `local_json`: local JSONL index for demo-sized KB versions.

## Local JSON Index

Files are stored as:

```text
data/vector_indexes/kb_<knowledge_base_version_id>.jsonl
```

Each row stores chunk id, KB version id, embedding, and metadata. Search still rechecks metadata filters after cosine similarity.

## Production Boundary

`local_json` and `local_hash_embedding` are not production semantic retrieval. Future staging/production can add Qdrant, Chroma, Milvus, FAISS, or another backend behind the same interface.
