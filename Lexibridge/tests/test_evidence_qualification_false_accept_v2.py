import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/evaluations/bilingual_evidence_qualification_safety_v2.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("task_12g1_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_keeps_all_25_and_reports_false_accept_safety_denominators():
    runner = _load_runner()
    result = runner.evaluate(runner.DeterministicSafetyFixture())
    assert len(result["rows"]) == 25
    assert result["metrics"]["all_25"] == 25
    assert result["metrics"]["evidence_qualification_eligible"] == 11
    assert result["metrics"]["baseline_false_qualification_count"] == 6
    assert "outside_eligible" in result["metrics"]


def test_runner_uses_gold_only_for_evaluation_labels_not_policy_inputs():
    runner = _load_runner()
    result = runner.evaluate(runner.DeterministicSafetyFixture())
    assert result["production_policy_uses_gold"] is False
    assert result["external_api_requests"] == 0
    assert result["real_provider_requests"] == 0
