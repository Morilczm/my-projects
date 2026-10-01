import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/evaluations/bilingual_pairing_reranker_v2.py"


def test_v2_runner_exists_and_preserves_all_denominators():
    spec = importlib.util.spec_from_file_location("reranker_v2", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ALL_25_DENOMINATOR == 25
    assert module.REAL_PROVIDER_REQUESTS == 0


class FakeBiEncoder:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeReranker:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def score_pairs(self, pairs):
        return [0.5 for _ in pairs]


def test_v2_runner_preserves_upstream_denominators(app_module):
    del app_module
    spec = importlib.util.spec_from_file_location("reranker_v2_eval", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.evaluate(FakeBiEncoder(), FakeReranker())
    metrics = result["metrics"]
    assert metrics["coverage"] == 25
    assert metrics["retrieval_eligible"] == 18
    assert metrics["identification_eligible"] <= 18
    assert metrics["pairing_eligible"] <= metrics["identification_eligible"]
    assert result["real_provider_requests"] == 0
    assert result["external_api_requests"] == 0
