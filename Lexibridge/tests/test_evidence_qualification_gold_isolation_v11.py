import inspect

from services import bilingual_evidence_qualification as qualification


def test_v11_production_policy_contains_no_gold_alias_or_required_proposition_input():
    source = inspect.getsource(qualification)
    fields = qualification.BilingualEvidenceQualificationInput.__dataclass_fields__

    assert "gold_chinese_term" not in fields
    assert "accepted_chinese_aliases" not in fields
    assert "required_propositions" not in fields
    assert "benchmark_concept_id" not in fields
    assert "gold.json" not in source


def test_policy_has_no_provider_or_external_api_fallback():
    source = inspect.getsource(qualification).casefold()
    assert "deepseek" not in source
    assert "openai" not in source
    assert "requests." not in source
    assert "http://" not in source
    assert "https://" not in source
