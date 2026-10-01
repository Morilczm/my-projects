from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = (
    ROOT / "backend/services/bilingual_evidence_qualification.py",
    ROOT / "backend/services/bilingual_evidence_workflow.py",
)


def test_qualification_does_not_read_gold_aliases_or_required_propositions():
    forbidden = ("gold.json", "accepted_chinese_aliases", "required_propositions")
    for path in PRODUCTION:
        text = path.read_text()
        assert all(token not in text for token in forbidden)


def test_qualification_has_no_provider_or_external_api_dependency():
    text = (ROOT / "backend/services/bilingual_evidence_qualification.py").read_text()
    assert "deepseek" not in text.casefold()
    assert "openai" not in text.casefold()
    assert "requests." not in text
