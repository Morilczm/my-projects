"""Embedding provider abstraction for optional vector retrieval."""

from __future__ import annotations

import hashlib
import math
import os
import urllib.error
import urllib.request
import json


def _unit_vector(values):
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return values
    return [round(value / norm, 8) for value in values]


class EmbeddingProvider:
    trust_level = "unknown"

    def embed_texts(self, texts, model=None):
        raise NotImplementedError

    def is_available(self):
        return False

    def provider_name(self):
        return "none"

    def dimension(self):
        return 0


class NoneEmbeddingProvider(EmbeddingProvider):
    def embed_texts(self, texts, model=None):
        raise RuntimeError("Embedding provider is not configured.")

    def provider_name(self):
        return "none"


class LocalHashEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash embedding for tests and local demos only."""

    trust_level = "low_trust_embedding"

    def __init__(self, dimension=None):
        self._dimension = int(dimension or os.environ.get("EMBEDDING_DIMENSION") or os.environ.get("LOCAL_EMBEDDING_DIM") or 256)

    def is_available(self):
        return True

    def provider_name(self):
        return "local_hash_embedding"

    def dimension(self):
        return self._dimension

    def embed_texts(self, texts, model=None):
        vectors = []
        for text in texts:
            vector = [0.0] * self._dimension
            tokens = str(text or "").lower().split()
            if not tokens:
                vectors.append(vector)
                continue
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self._dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            vectors.append(_unit_vector(vector))
        return vectors


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """Minimal OpenAI-compatible embedding client boundary."""

    def __init__(self, api_key=None, base_url=None, model=None, timeout=None, dimension=None):
        self.api_key = api_key or os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("EMBEDDING_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
        self.model = model or os.environ.get("EMBEDDING_MODEL", "")
        self.timeout = int(timeout or os.environ.get("EMBEDDING_REQUEST_TIMEOUT_SECONDS", "45"))
        self._dimension = int(dimension or os.environ.get("EMBEDDING_DIMENSION") or 0)

    def is_available(self):
        return bool(self.api_key and self.base_url and self.model)

    def provider_name(self):
        return "openai_compatible"

    def dimension(self):
        return self._dimension

    def embed_texts(self, texts, model=None):
        if not self.is_available():
            raise RuntimeError("OpenAI-compatible embedding provider is not configured.")
        payload = json.dumps({"model": model or self.model, "input": texts}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("Embedding provider request failed.") from exc
        return [item.get("embedding", []) for item in data.get("data", [])]


def get_embedding_provider(name=None):
    provider = (name or os.environ.get("EMBEDDING_PROVIDER", "none")).strip().lower()
    if provider == "local_hash_embedding":
        return LocalHashEmbeddingProvider()
    if provider in {"openai_compatible", "deepseek_compatible", "custom"}:
        return OpenAICompatibleEmbeddingProvider()
    return NoneEmbeddingProvider()
