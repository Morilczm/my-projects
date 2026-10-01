# Indexing and Rebuild Plan

## Incremental Indexing

`index_document_into_kb_version(document_id, kb_version_id)` reads `DocumentChunk`, creates `KnowledgeSource`, computes normalized text and `content_hash`, marks duplicates, and writes versioned `KnowledgeChunk` records.

Rules:

- Personal documents cannot enter course KB.
- Course chunks require matching `course_id`.
- Formula blocks remain separate evidence and are linked by metadata, not converted into ordinary terms.
- Duplicate chunks are retained for traceability but marked inactive.

## Full Rebuild

`scripts/rebuild_knowledge_index.py` supports:

```bash
python scripts/rebuild_knowledge_index.py --course-id 1 --dry-run
python scripts/rebuild_knowledge_index.py --course-id 1 --apply
```

Dry-run reports source document count. Apply creates a candidate version, indexes active documents, runs health checks, and leaves publishing as a separate explicit step.

## Failure Handling

Failed rebuilds do not affect the current published version. Candidate versions remain `draft`/`failed` until a teacher/admin reviews health and regression results.
