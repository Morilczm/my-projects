import pytest

from services.bilingual_semantic_pairing import (
    BILINGUAL_PAIRING_REPRESENTATION_INVALID,
    BilingualPairingError,
    EnglishPairingInput,
    rank_bilingual_pairs,
)
from services.local_multilingual_embedding import BACKEND_UNAVAILABLE


def _english():
    return EnglishPairingInput(
        "en-1", "mass", "mass", "measure of inertia", "physics",
        {"source_uid": "en-source", "chunk_uid": "en-chunk"},
    )


def _candidate():
    return [{
        "candidate_uid": "zh-1",
        "chinese_term": "质量",
        "normalized_text": "质量",
        "evidence_snippet": "质量是衡量惯性大小的物理量。",
        "source_uid": "zh-source",
        "chunk_uid": "zh-chunk",
        "rank": 1,
        "retrieval_rank": 1,
        "score": 0.8,
        "provenance": {"source_uid": "zh-source", "chunk_uid": "zh-chunk"},
    }]


class UnavailableBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": False, "reason_code": BACKEND_UNAVAILABLE})()


class WrongDimensionBackend(UnavailableBackend):
    dimension = 3

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        return [[1.0, 0.0]]

    def embed_passages(self, texts):
        return [[1.0, 0.0, 0.0]]


def test_backend_unavailable_has_no_fallback():
    with pytest.raises(BilingualPairingError, match=BACKEND_UNAVAILABLE):
        rank_bilingual_pairs(_english(), _candidate(), UnavailableBackend())


def test_dimension_mismatch_fails_closed():
    with pytest.raises(BilingualPairingError, match=BILINGUAL_PAIRING_REPRESENTATION_INVALID):
        rank_bilingual_pairs(_english(), _candidate(), WrongDimensionBackend())
