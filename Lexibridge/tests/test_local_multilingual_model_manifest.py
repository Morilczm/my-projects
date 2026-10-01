import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evaluations/artifacts/12D0-local-model-backend-manifest.json"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_pins_model_identity_license_and_contract():
    payload = _manifest()
    assert payload["backend_id"] == "local_multilingual_e5_pytorch_cpu_v1"
    assert payload["model_id"] == "intfloat/multilingual-e5-small"
    assert payload["model_revision"] == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    assert payload["license"] == "MIT"
    assert payload["dimension"] == 384
    assert payload["maximum_input_tokens"] == 512
    assert payload["pooling"] == "mean"
    assert payload["normalization"] == "L2"
    assert payload["query_prefix"] == "query: "
    assert payload["passage_prefix"] == "passage: "
    assert payload["trust_remote_code"] is False


def test_manifest_is_offline_and_not_connected_to_production():
    payload = _manifest()
    assert payload["offline_load_required"] is True
    assert payload["silent_download_allowed"] is False
    assert payload["external_api_used"] is False
    assert payload["production_retrieval_connected"] is False
    assert payload["v2_quality_modified"] is False
    assert payload["ci_backend"] == "deterministic_fake"


def test_optional_dependencies_are_version_pinned():
    requirements = (
        ROOT / "backend/requirements-local-multilingual-retrieval.txt"
    ).read_text(encoding="utf-8")
    for dependency in (
        "sentence-transformers==3.4.1",
        "torch==2.5.1",
        "transformers==4.48.3",
        "numpy==2.0.2",
    ):
        assert dependency in requirements
    assert ">=" not in requirements
