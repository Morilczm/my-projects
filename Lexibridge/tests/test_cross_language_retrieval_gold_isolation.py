from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = (
    ROOT / "backend/services/cross_language_retrieval.py",
    ROOT / "backend/services/bilingual_evidence_workflow.py",
)


def test_production_retrieval_has_no_gold_or_alias_mapping_dependency():
    for path in PRODUCTION_FILES:
        text = path.read_text()
        assert "gold.json" not in text
        assert "required_propositions" not in text
        assert "accepted_chinese_aliases" not in text
        assert "cross_corpus_v2" not in text


def test_model_and_backend_are_fixed_outside_the_request_dto():
    workflow = PRODUCTION_FILES[1].read_text()
    assert 'CROSS_LANGUAGE_BACKEND_NAME = "local-multilingual-e5-small"' in workflow
    assert "model_path" not in workflow
    assert "local_hash_embedding" not in workflow
    assert "DeepSeek" not in workflow
