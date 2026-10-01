"""Qualified local multilingual embedding boundary used by explicit retrieval.

The adapter is deliberately offline-only. Model preparation remains a separate,
explicit operation; application code cannot trigger a download or fall back to
another embedding implementation.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


BACKEND_ID = "local_multilingual_e5_pytorch_cpu_v1"
MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL_DIMENSION = 384
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
BACKEND_UNAVAILABLE = "LOCAL_MULTILINGUAL_EMBEDDING_BACKEND_UNAVAILABLE"
REQUIRED_MODEL_FILES = (
    "1_Pooling/config.json",
    "config.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


class LocalMultilingualEmbeddingError(RuntimeError):
    """Controlled, deterministic local-backend failure."""


@dataclass(frozen=True)
class BackendReadiness:
    ready: bool
    reason_code: str
    backend_id: str = BACKEND_ID
    model_id: str = MODEL_ID
    model_revision: str = MODEL_REVISION


def cache_key(model_id: str, model_revision: str, content: str) -> str:
    content_hash = hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()
    seed = f"{model_id}\0{model_revision}\0{content_hash}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _normalized_rows(values: Any) -> list[list[float]]:
    rows = values.tolist() if hasattr(values, "tolist") else list(values)
    normalized = []
    for row in rows:
        floats = [float(value) for value in row]
        norm = math.sqrt(sum(value * value for value in floats))
        normalized.append(
            [round(value / norm, 8) for value in floats]
            if norm > 0
            else floats
        )
    return normalized


class LocalMultilingualEmbeddingBackend:
    backend_id = BACKEND_ID
    model_id = MODEL_ID
    model_revision = MODEL_REVISION
    dimension = MODEL_DIMENSION

    def __init__(
        self,
        *,
        model_cache_dir: str | Path,
        model_loader: Callable[[Path], Any] | None = None,
        repo_root: str | Path | None = None,
    ):
        self.model_cache_dir = Path(model_cache_dir).expanduser().resolve()
        self.repo_root = (
            Path(repo_root).expanduser().resolve()
            if repo_root
            else Path(__file__).resolve().parents[2]
        )
        if self.model_cache_dir == self.repo_root or self.repo_root in self.model_cache_dir.parents:
            raise LocalMultilingualEmbeddingError(
                "Model cache must be outside the repository."
            )
        self._model_loader = model_loader
        self._model = None

    def _snapshot_dir(self) -> Path:
        return (
            self.model_cache_dir
            / "models--intfloat--multilingual-e5-small"
            / "snapshots"
            / MODEL_REVISION
        )

    def readiness(self) -> BackendReadiness:
        if self._model_loader is not None:
            return BackendReadiness(True, "READY")
        snapshot = self._snapshot_dir()
        if not snapshot.is_dir() or any(
            not (snapshot / relative_path).is_file()
            for relative_path in REQUIRED_MODEL_FILES
        ):
            return BackendReadiness(False, BACKEND_UNAVAILABLE)
        return BackendReadiness(True, "READY")

    def _default_loader(self) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise LocalMultilingualEmbeddingError(BACKEND_UNAVAILABLE) from exc
        try:
            return SentenceTransformer(
                MODEL_ID,
                revision=MODEL_REVISION,
                cache_folder=str(self.model_cache_dir),
                local_files_only=True,
                trust_remote_code=False,
                device="cpu",
            )
        except Exception as exc:
            raise LocalMultilingualEmbeddingError(BACKEND_UNAVAILABLE) from exc

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.readiness().ready:
            raise LocalMultilingualEmbeddingError(BACKEND_UNAVAILABLE)
        try:
            self._model = (
                self._model_loader(self.model_cache_dir)
                if self._model_loader is not None
                else self._default_loader()
            )
        except LocalMultilingualEmbeddingError:
            raise
        except Exception as exc:
            raise LocalMultilingualEmbeddingError(BACKEND_UNAVAILABLE) from exc
        return self._model

    def _embed(self, texts: Iterable[str], prefix: str) -> list[list[float]]:
        prefixed = [f"{prefix}{str(text or '').strip()}" for text in texts]
        if not prefixed:
            return []
        model = self._load()
        try:
            vectors = model.encode(
                prefixed,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise LocalMultilingualEmbeddingError(BACKEND_UNAVAILABLE) from exc
        return _normalized_rows(vectors)

    def embed_queries(self, texts: Iterable[str]) -> list[list[float]]:
        return self._embed(texts, QUERY_PREFIX)

    def embed_passages(self, texts: Iterable[str]) -> list[list[float]]:
        return self._embed(texts, PASSAGE_PREFIX)
