import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/evaluations/bilingual_semantic_pairing_v2.py"


class DeterministicFakeBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    dimension = 2

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _runner():
    spec = importlib.util.spec_from_file_location("bilingual_semantic_pairing_v2", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v2_runner_preserves_all_denominators_and_upstream_attribution(app_module):
    del app_module
    result = _runner().evaluate(DeterministicFakeBackend())
    metrics = result["metrics"]
    assert len(result["rows"]) == 25
    assert metrics["retrieval_eligible"] == 18
    assert metrics["identification_eligible"] <= 18
    assert metrics["pairing_eligible"] <= metrics["identification_eligible"]
    assert sum(
        row["primary_attribution"] == "UPSTREAM_ENGLISH_EXTRACTION_MISSING"
        for row in result["rows"]
    ) == 3
    assert sum(
        row["primary_attribution"] == "UPSTREAM_ENGLISH_BINDING_AMBIGUOUS"
        for row in result["rows"]
    ) == 4
    assert result["real_provider_requests"] == 0
    assert result["external_api_requests"] == 0


def test_v2_runner_has_no_gold_driven_pairing_input(app_module):
    del app_module
    source = RUNNER.read_text()
    pair_call = source[source.index("pairs = rank_bilingual_pairs"):source.index(
        "correct_pair = next"
    )]
    assert "chinese_term" not in pair_call
    assert "accepted_chinese_aliases" not in pair_call
    assert "required_propositions" not in pair_call


def test_v2_runner_keeps_confusion_upstream_failures_out_of_pairing(app_module):
    del app_module
    result = _runner().evaluate(DeterministicFakeBackend())
    groups = {item["group"]: item for item in result["confusion_groups"]}
    assert groups["momentum / angular momentum"]["primary_attribution"] == (
        "UPSTREAM_ENGLISH_BINDING_AMBIGUOUS"
    )
    assert not groups["momentum / angular momentum"]["upstream_eligible"]
