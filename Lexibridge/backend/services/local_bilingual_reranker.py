"""Offline-only fixed-revision BGE reranker adapter."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


BACKEND_ID = "local_bge_reranker_v2_m3_cpu_v1"
MODEL_ID = "BAAI/bge-reranker-v2-m3"
MODEL_REVISION = "79c481748842b7efa0a12db59915db91731f0b93"
MODEL_LICENSE = "Apache-2.0"
MODEL_ARCHITECTURE = "XLMRobertaForSequenceClassification"
MAX_PAIR_TOKENS = 512
MAX_ENGLISH_TOKENS = 192
MAX_CHINESE_TOKENS = 316

BILINGUAL_RERANKER_BACKEND_UNAVAILABLE = "BILINGUAL_RERANKER_BACKEND_UNAVAILABLE"
BILINGUAL_RERANKER_REVISION_MISMATCH = "BILINGUAL_RERANKER_REVISION_MISMATCH"
BILINGUAL_RERANKER_INPUT_INVALID = "BILINGUAL_RERANKER_INPUT_INVALID"
BILINGUAL_RERANKER_EXECUTION_FAILED = "BILINGUAL_RERANKER_EXECUTION_FAILED"

REQUIRED_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


class LocalBilingualRerankerError(RuntimeError):
    """Controlled local cross-encoder failure."""


@dataclass(frozen=True)
class RerankerReadiness:
    ready: bool
    reason_code: str
    backend_id: str = BACKEND_ID
    model_id: str = MODEL_ID
    model_revision: str = MODEL_REVISION


class _TransformersRuntime:
    def __init__(self, tokenizer: Any, model: Any):
        self.tokenizer = tokenizer
        self.model = model

    def score_pairs(
        self,
        pairs: list[tuple[str, str]],
        *,
        max_length: int,
    ) -> list[float]:
        import torch

        features = []
        for query, passage in pairs:
            query_tokens = self.tokenizer(
                query,
                add_special_tokens=False,
                truncation=True,
                max_length=MAX_ENGLISH_TOKENS,
            )["input_ids"]
            passage_tokens = self.tokenizer(
                passage,
                add_special_tokens=False,
                truncation=True,
                max_length=MAX_CHINESE_TOKENS,
            )["input_ids"]
            features.append(self.tokenizer.prepare_for_model(
                query_tokens,
                passage_tokens,
                add_special_tokens=True,
                truncation="only_second",
                max_length=max_length,
            ))
        inputs = self.tokenizer.pad(
            features,
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = self.model(**inputs, return_dict=True).logits
        return [float(value) for value in logits.view(-1).float().cpu().tolist()]


class LocalBilingualReranker:
    backend_id = BACKEND_ID
    model_id = MODEL_ID
    model_revision = MODEL_REVISION
    model_license = MODEL_LICENSE
    max_pair_tokens = MAX_PAIR_TOKENS

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
        if (
            self.model_cache_dir == self.repo_root
            or self.repo_root in self.model_cache_dir.parents
        ):
            raise LocalBilingualRerankerError(
                "Model cache must be outside the repository."
            )
        self._model_loader = model_loader
        self._runtime = None

    def _snapshot_dir(self) -> Path:
        return (
            self.model_cache_dir
            / "models--BAAI--bge-reranker-v2-m3"
            / "snapshots"
            / MODEL_REVISION
        )

    def readiness(self) -> RerankerReadiness:
        if self._model_loader is not None:
            return RerankerReadiness(True, "READY")
        snapshot = self._snapshot_dir()
        ready = snapshot.is_dir() and all(
            (snapshot / relative_path).is_file()
            for relative_path in REQUIRED_MODEL_FILES
        )
        return RerankerReadiness(
            ready,
            "READY" if ready else BILINGUAL_RERANKER_BACKEND_UNAVAILABLE,
        )

    def _default_loader(self) -> _TransformersRuntime:
        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:
            raise LocalBilingualRerankerError(
                BILINGUAL_RERANKER_BACKEND_UNAVAILABLE
            ) from exc
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                MODEL_ID,
                revision=MODEL_REVISION,
                cache_dir=str(self.model_cache_dir),
                local_files_only=True,
                trust_remote_code=False,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                MODEL_ID,
                revision=MODEL_REVISION,
                cache_dir=str(self.model_cache_dir),
                local_files_only=True,
                trust_remote_code=False,
                device_map=None,
            )
            model.to("cpu")
            model.eval()
        except Exception as exc:
            raise LocalBilingualRerankerError(
                BILINGUAL_RERANKER_BACKEND_UNAVAILABLE
            ) from exc
        return _TransformersRuntime(tokenizer, model)

    def _load(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        if not self.readiness().ready:
            raise LocalBilingualRerankerError(
                BILINGUAL_RERANKER_BACKEND_UNAVAILABLE
            )
        try:
            self._runtime = (
                self._model_loader(self.model_cache_dir)
                if self._model_loader is not None
                else self._default_loader()
            )
        except LocalBilingualRerankerError:
            raise
        except Exception as exc:
            raise LocalBilingualRerankerError(
                BILINGUAL_RERANKER_BACKEND_UNAVAILABLE
            ) from exc
        return self._runtime

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        bounded = list(pairs or [])
        if (
            not bounded
            or len(bounded) > 20
            or any(not str(left).strip() or not str(right).strip() for left, right in bounded)
        ):
            raise LocalBilingualRerankerError(BILINGUAL_RERANKER_INPUT_INVALID)
        try:
            scores = self._load().score_pairs(
                bounded,
                max_length=MAX_PAIR_TOKENS,
            )
        except LocalBilingualRerankerError:
            raise
        except Exception as exc:
            raise LocalBilingualRerankerError(
                BILINGUAL_RERANKER_EXECUTION_FAILED
            ) from exc
        if len(scores) != len(bounded):
            raise LocalBilingualRerankerError(BILINGUAL_RERANKER_EXECUTION_FAILED)
        return [round(float(score), 8) for score in scores]
