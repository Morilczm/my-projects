"""Vector index abstraction and local JSON backend."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path


def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    score = sum(float(left[i]) * float(right[i]) for i in range(size))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left[:size]))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right[:size]))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return round(score / (left_norm * right_norm), 6)


class VectorIndexBackend:
    backend_name = "none"

    def upsert(self, kb_version_id, items):
        return {"status": "error", "error_code": "VECTOR_INDEX_UNAVAILABLE"}

    def search(self, kb_version_id, query_vector, filters, top_k):
        return []

    def delete_version(self, kb_version_id):
        return {"status": "success", "deleted": 0}

    def healthcheck(self, kb_version_id=None):
        return {"status": "unavailable", "backend": self.backend_name}


class NoneVectorIndexBackend(VectorIndexBackend):
    backend_name = "none"


class LocalJsonVectorIndexBackend(VectorIndexBackend):
    backend_name = "local_json"

    def __init__(self, index_dir=None):
        self.index_dir = Path(index_dir or os.environ.get("VECTOR_INDEX_DIR", "data/vector_indexes"))

    def _path(self, kb_version_id):
        return self.index_dir / f"kb_{int(kb_version_id)}.jsonl"

    def upsert(self, kb_version_id, items):
        self.index_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(kb_version_id)
        with path.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        return {"status": "success", "backend": self.backend_name, "kb_version_id": int(kb_version_id), "upserted": len(items), "path": str(path)}

    def _iter_records(self, kb_version_id):
        path = self._path(kb_version_id)
        if not path.exists():
            return []
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _metadata_matches(self, metadata, filters):
        for key in ["course_id", "scope_type", "owner_user_id", "language", "knowledge_base_type", "visibility"]:
            expected = filters.get(key)
            if expected in {None, ""}:
                continue
            actual = metadata.get(key)
            if key == "language" and expected == "zh":
                if actual not in {"zh", "bilingual"}:
                    return False
                continue
            if key == "language" and expected == "en":
                if actual not in {"en", "bilingual"}:
                    return False
                continue
            if str(actual) != str(expected):
                return False
        return True

    def search(self, kb_version_id, query_vector, filters, top_k):
        scored = []
        for record in self._iter_records(kb_version_id):
            metadata = record.get("metadata") or {}
            if not self._metadata_matches(metadata, filters or {}):
                continue
            score = cosine_similarity(query_vector, record.get("embedding") or [])
            scored.append({
                "chunk_id": record.get("chunk_id"),
                "kb_version_id": record.get("kb_version_id"),
                "vector_score": max(0.0, score),
                "metadata": metadata,
            })
        scored.sort(key=lambda item: item["vector_score"], reverse=True)
        return scored[:top_k]

    def delete_version(self, kb_version_id):
        path = self._path(kb_version_id)
        if path.exists():
            path.unlink()
            return {"status": "success", "deleted": 1}
        return {"status": "success", "deleted": 0}

    def healthcheck(self, kb_version_id=None):
        paths = [self._path(kb_version_id)] if kb_version_id else sorted(self.index_dir.glob("kb_*.jsonl")) if self.index_dir.exists() else []
        vector_count = 0
        dimensions = set()
        for path in paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    vector = record.get("embedding") or []
                    vector_count += 1
                    if vector:
                        dimensions.add(len(vector))
        return {
            "status": "ok" if vector_count else "empty",
            "backend": self.backend_name,
            "kb_version_id": kb_version_id,
            "vector_count": vector_count,
            "dimensions": sorted(dimensions),
            "index_dir": str(self.index_dir),
        }


def get_vector_index_backend(name=None):
    backend = (name or os.environ.get("VECTOR_INDEX_BACKEND", "none")).strip().lower()
    if backend == "local_json":
        return LocalJsonVectorIndexBackend()
    return NoneVectorIndexBackend()
