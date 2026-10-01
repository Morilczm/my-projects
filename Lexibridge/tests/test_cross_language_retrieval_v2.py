import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/evaluations/cross_language_retrieval_v2.py"


class DeterministicFakeBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _runner():
    spec = importlib.util.spec_from_file_location("cross_language_retrieval_v2", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v2_runner_preserves_all_denominators_and_upstream_attribution(app_module):
    del app_module
    result = _runner().evaluate(DeterministicFakeBackend())
    assert len(result["rows"]) == 25
    assert result["metrics"]["retrieval_eligible"] == 18
    assert result["metrics"]["english_missing"] == 3
    assert result["metrics"]["english_ambiguous"] == 4
    excluded = [row for row in result["rows"] if not row["eligible"]]
    assert len(excluded) == 7
    assert sum(
        row["primary_attribution"] == "UPSTREAM_ENGLISH_EXTRACTION_MISSING"
        for row in excluded
    ) == 3
    assert sum(
        row["primary_attribution"] == "UPSTREAM_ENGLISH_BINDING_AMBIGUOUS"
        for row in excluded
    ) == 4
    assert result["real_provider_requests"] == 0
