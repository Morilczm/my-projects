from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAIRER = ROOT / "backend/services/bilingual_semantic_pairing.py"


def test_pairer_has_no_gold_alias_mapping_or_external_provider():
    text = PAIRER.read_text()
    for forbidden in (
        "gold.json", "accepted_chinese_aliases", "required_propositions",
        "cross_corpus_v2", "DeepSeek", "OpenAI", "local_hash_embedding",
        "requests.",
    ):
        assert forbidden not in text


def test_pairer_does_not_import_retrieval_or_term_extraction():
    text = PAIRER.read_text()
    assert "rank_chinese_passages" not in text
    assert "identify_standard_chinese_terms" not in text
