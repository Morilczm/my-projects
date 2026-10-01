from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "backend/services/chinese_term_candidates.py"


def test_monolingual_identification_has_no_gold_alias_or_external_dependency():
    text = SERVICE.read_text()
    assert "gold.json" not in text
    assert "accepted_chinese_aliases" not in text
    assert "required_propositions" not in text
    assert "cross_corpus_v2" not in text
    assert "DeepSeek" not in text
    assert "requests." not in text


def test_fixture_terms_are_not_a_production_allowlist():
    text = SERVICE.read_text()
    for term in ("电场强度", "电势能", "角加速度", "角动量", "重量"):
        assert term not in text
