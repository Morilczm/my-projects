from pathlib import Path

from scripts import check_release_safety


ROOT = Path(__file__).resolve().parents[1]


def test_release_safety_rejects_model_weights_and_cache_paths():
    weight = check_release_safety.ScanItem("models/model.safetensors", ("models", "model.safetensors"))
    cache = check_release_safety.ScanItem("model_cache/config.json", ("model_cache", "config.json"))
    oversized = check_release_safety.ScanItem(
        "opaque.bin",
        ("opaque.bin",),
        size_bytes=check_release_safety.MAX_RELEASE_FILE_BYTES + 1,
    )
    assert any("model" in issue for issue in check_release_safety.check_path(weight))
    assert any("cache" in issue for issue in check_release_safety.check_path(cache))
    assert any("oversized" in issue for issue in check_release_safety.check_path(oversized))


def test_gitignore_covers_model_and_huggingface_caches():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for marker in ("model_cache/", "models/", ".cache/huggingface/", "*.safetensors", "*.onnx"):
        assert marker in text


def test_backend_is_only_imported_by_explicit_cross_language_production_path():
    for path in (
        ROOT / "backend/services/evidence_retrieval.py",
        ROOT / "backend/services/retrieval_backends.py",
    ):
        assert "local_multilingual_embedding" not in path.read_text(encoding="utf-8")
    workflow = (
        ROOT / "backend/services/bilingual_evidence_workflow.py"
    ).read_text(encoding="utf-8")
    assert "LocalMultilingualEmbeddingBackend" in workflow
    assert 'CROSS_LANGUAGE_BACKEND_NAME = "local-multilingual-e5-small"' in workflow


def test_backend_source_does_not_read_gold_or_call_external_apis():
    source = (ROOT / "backend/services/local_multilingual_embedding.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "gold.json",
        "accepted_alias",
        "urllib.request",
        "requests.",
        "http://",
        "https://",
        "local_hash_embedding",
    )
    assert not any(item in source for item in forbidden)
