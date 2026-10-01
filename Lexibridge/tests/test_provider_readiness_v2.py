from scripts.evaluations import provider_readiness_v2


def test_v2_runner_keeps_all_25_and_recomputes_denominators():
    result = provider_readiness_v2.run_evaluation(use_fake_provider_config=True)
    assert len(result["rows"]) == 25
    assert result["summary"]["qualification_qualified"] == 3
    assert result["summary"]["provider_readiness_eligible"] <= 3
    assert result["summary"]["false_ready"] == 0
    assert result["summary"]["real_provider_requests"] == 0
