from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_readiness_policy_does_not_read_gold_or_aliases():
    source = (ROOT / "backend/services/provider_readiness.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "gold.json" not in lowered
    assert "required_propositions" not in lowered
    assert "accepted_chinese_aliases" not in lowered
