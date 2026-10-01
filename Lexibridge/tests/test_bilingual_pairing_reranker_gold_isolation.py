from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RERANKER = ROOT / "backend/services/bilingual_pairing_reranker.py"
BACKEND = ROOT / "backend/services/local_bilingual_reranker.py"


def test_reranker_has_no_gold_alias_mapping_or_external_provider():
    text = RERANKER.read_text() + BACKEND.read_text()
    for forbidden in (
        "gold.json",
        "accepted_chinese_aliases",
        "required_propositions",
        "cross_corpus_v2",
        "DeepSeek",
        "OpenAI",
        "local_hash_embedding",
        "requests.",
    ):
        assert forbidden not in text


def test_reranker_does_not_import_retrieval_or_term_extraction():
    text = RERANKER.read_text()
    assert "rank_chinese_passages" not in text
    assert "identify_standard_chinese_terms" not in text
