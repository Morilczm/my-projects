from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_api_cannot_submit_readiness_or_disable_gates():
    routes = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "backend/routes").glob("*.py")
    ).lower()
    for forbidden in (
        "provider_readiness_decision",
        "disable_qualification_gate",
        "disable_privacy_gate",
        "disable_budget_gate",
    ):
        assert forbidden not in routes


def test_production_composition_wires_readiness_before_provider_execution():
    composition = (
        ROOT / "backend/services/document_alignment_processing_composition.py"
    ).read_text(encoding="utf-8")
    adapter = (
        ROOT / "backend/services/document_alignment_item_verification_adapter.py"
    ).read_text(encoding="utf-8")
    assert "evaluate_provider_readiness=provider_readiness.evaluate_formal_prepared_readiness" in composition
    assert adapter.index("evaluate_provider_readiness(") < adapter.index(
        "provider.verify_alignment("
    )
