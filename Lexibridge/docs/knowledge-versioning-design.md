# Knowledge Base Versioning Design

## Lifecycle

`KnowledgeBaseVersion.status` supports:

- `draft`: candidate version under construction.
- `indexing`: indexing in progress.
- `ready`: indexed and eligible for health/regression gates.
- `published`: default retrieval version for its scope.
- `archived`: retained for traceability but not default retrieval.
- `failed`: indexing or health gate failed.
- `rolled_back`: superseded by rollback flow.

Only one course/personal/global version should be `published` for the same scope at a time.

## Scope

- `course`: requires `course_id`.
- `personal`: requires `owner_user_id`, remains private.
- `global`: admin-managed shared knowledge.

## Evidence Traceability

`TerminologyCard` now records KB version, retrieval run, index version, and evidence content hashes. Evidence snapshots remain stored on the card so later KB updates do not erase the original judgment context.

## Publish and Rollback

Publishing requires `ready` status, non-zero chunks, and a passing health check. Publishing archives the previously published version for that scope. Rollback republishes an older non-failed version and archives the current one.
