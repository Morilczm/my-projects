# Task 12D.0 — Local Multilingual Retrieval Backend Qualification

Status: `LOCAL_MULTILINGUAL_RETRIEVAL_BACKEND_QUALIFIED`

## Executive conclusion

`intfloat/multilingual-e5-small` is qualified as a local, offline-only
multilingual representation backend through Sentence Transformers and PyTorch
CPU. The model is pinned to revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, uses the MIT license, and was
loaded successfully from a repository-external cache with network access
disabled.

This task does **not** connect the adapter to production retrieval. It does not
change Cross-Corpus V2 quality, Chinese terminology identification, pairing,
prompts, providers, or evidence thresholds. Real Provider requests were zero.

## Environment audit

- Host: macOS 26.5.2, Apple arm64.
- Project Python: 3.12.10.
- Backend virtualenv Python: 3.9.6.
- Package manager: pip with plain requirements files; the project had no lock
  file or optional dependency group mechanism.
- Available disk before installation: approximately 292 GiB.
- Hugging Face cache before qualification: absent.
- Before installation, NumPy, PyTorch, Transformers, Sentence Transformers,
  and ONNX Runtime were absent.
- Existing release safety rejected local databases, archives, virtual
  environments, caches, and secrets, but did not recognize model weights or
  arbitrary oversized files.

## Runtime path selection

### Selected: Sentence Transformers + PyTorch CPU

The selected path uses native safetensors and avoids model conversion. PyTorch
provides a macOS arm64 Python 3.9 wheel for the pinned version. The model is
small enough for a controlled local CPU runtime and its native contract is
directly represented by Sentence Transformers.

### Not selected: Sentence Transformers + ONNX Runtime CPU

The ONNX path is technically possible on macOS arm64, but requires additional
ONNX/Optimum dependencies and an explicit exported-file and pooling contract.
Sentence Transformers may export an ONNX graph when an appropriate graph is
not present, adding mutable preparation behavior. It offered no qualification
advantage for this task, so it was not installed or integrated.

Official references:

- [multilingual-e5-small model card](https://huggingface.co/intfloat/multilingual-e5-small)
- [Sentence Transformers installation](https://sbert.net/docs/installation.html)
- [Sentence Transformers ONNX behavior](https://sbert.net/docs/sentence_transformer/usage/efficiency.html)
- [PyTorch macOS support](https://docs.pytorch.org/get-started/locally/)

## Model contract

- Model ID: `intfloat/multilingual-e5-small`
- Revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- License: MIT
- Reported language coverage: 94 languages
- Embedding dimension: 384
- Maximum input length: 512 tokens
- Pooling: masked mean pooling
- Normalization: L2
- Query prefix: `query: `
- Passage prefix: `passage: `
- Query and passage encoder: shared
- Remote custom code: disabled and not required (`trust_remote_code=false`)
- Weight format selected: safetensors; PyTorch pickle weights were excluded
- Prepared cache size: approximately 470 MiB

The complete file SHA-256 inventory is stored in
`docs/evaluations/artifacts/12D0-local-model-backend-manifest.json`.

## Dependency contract

The optional entry file is
`backend/requirements-local-multilingual-retrieval.txt`. The complete resolved
graph is frozen separately in
`backend/requirements-local-multilingual-retrieval.lock.txt`. Neither file is
consumed by ordinary development or CI.

Primary versions:

- sentence-transformers 3.4.1
- torch 2.5.1
- transformers 4.48.3
- numpy 2.0.2
- scikit-learn 1.6.1
- scipy 1.13.1
- huggingface-hub 0.36.2
- tokenizers 0.21.4
- safetensors 0.7.0
- urllib3 1.26.20

Installation:

```text
backend/.venv-macos/bin/python -m pip install --only-binary=:all: \
  -r backend/requirements-local-multilingual-retrieval.lock.txt
```

Uninstallation verification is defined as removing the packages listed in the
optional lock from an isolated environment and confirming the default backend
test suite remains installable from `backend/requirements.txt`. The qualified
environment was retained so the real offline smoke test and project regression
suite could run.

## Backend interface and failure behavior

`backend/services/local_multilingual_embedding.py` provides:

- stable backend/model/revision identifiers;
- readiness with deterministic reason codes;
- `embed_queries(texts)`;
- `embed_passages(texts)`;
- L2-normalized output;
- cache keys containing model ID, revision, and content SHA-256.

Missing dependencies, missing snapshot files, corrupt loading, or encoding
failure produce
`LOCAL_MULTILINGUAL_EMBEDDING_BACKEND_UNAVAILABLE`. There is no fallback to
`local_hash_embedding`, lexical search, or an external API.

The adapter is not imported by `evidence_retrieval.py`,
`retrieval_backends.py`, or `bilingual_evidence_workflow.py`.
`production_retrieval_connected=false`.

## Explicit preparation and offline cache

Model preparation is an explicit management action:

```text
LEXIBRIDGE_MODEL_CACHE_DIR=<repository-external-cache> \
backend/.venv-macos/bin/python scripts/prepare_local_multilingual_model.py
```

The script fixes the model revision and downloads only the required
safetensors, tokenizer, pooling, and configuration files. Ordinary application
startup uses `local_files_only=true`, `trust_remote_code=false`, and CPU; it
cannot silently download.

The cache is outside the repository. `.gitignore` and release safety reject
model/cache directories, common model-weight extensions, and repository files
larger than 25 MB. Model files are not distributed with the project.

## Real local offline smoke test

After explicit preparation, the backend was loaded with Hugging Face and
Transformers offline modes enabled. The English query and three original
Chinese passages shared no complete technical term string.

- output dimension: 384
- relevant passage cosine score: 0.818914
- unrelated charge-flow passage: 0.769915
- unrelated position-rate passage: 0.804292
- relevant passage rank: 1
- repeated offline embedding output stable: true
- offline load verified: true
- external embedding API calls: 0
- real Provider requests: 0

This is a runtime qualification smoke test only. The score margin is modest,
and no Cross-Corpus V2 metric was calculated or changed.

## CI isolation

CI uses an injected deterministic fake encoder. It validates query/passage
prefixes, normalization, determinism, fail-closed behavior, cache isolation,
and the manifest without downloading or loading model weights.

## Release safety and boundaries

- Model and cache tracked: false.
- Production retrieval connected: false.
- V2 corpus, gold, hashes, and quality: unchanged.
- Production retrieval behavior: unchanged.
- External APIs and DeepSeek: not called.
- Accident database: not accessed by backend tests and unchanged.

Validation results:

- RED: collection failed because the independent backend module did not exist.
- Targeted qualification and related safety tests: 19 passed.
- Final focused release-safety suite: 16 passed.
- Full pytest: 1350 passed, 56 pre-existing warnings.
- `dev_check`: passed, including release safety, full pytest, temporary
  migration, and backend API smoke.
- Standalone release safety: passed.
- `git diff --check`: passed.

## Conditions for resuming Task 12D

Task 12D may resume only after this PR is merged and the target runtime has:

1. installed the frozen optional dependency graph;
2. explicitly prepared the pinned snapshot outside the repository;
3. verified all model file hashes;
4. passed offline readiness and the controlled smoke test;
5. retained fail-closed behavior when the snapshot is unavailable.

Task 12D must then separately remove the cross-language lexical gate for the
qualified semantic path, add bounded Chinese-only retrieval and deterministic
ranking, and evaluate V2. This task does not authorize those changes.
