from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_api_cannot_submit_execution_success_or_disable_gates():
    routes = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "backend/routes").glob("*.py")
    ).lower()
    for forbidden in (
        "provider_execution_success",
        "disable_readiness_gate",
        "disable_privacy_gate",
        "disable_budget_gate",
    ):
        assert forbidden not in routes


def test_execution_service_does_not_reference_gold_or_real_credentials():
    source = (ROOT / "backend/services/provider_execution.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "gold.json" not in lowered
    assert "accepted_chinese_aliases" not in lowered
    assert "deepseek_api_key" not in lowered
    assert "openai_api_key" not in lowered
