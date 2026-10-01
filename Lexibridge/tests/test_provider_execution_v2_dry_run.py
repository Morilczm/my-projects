from scripts.evaluations import provider_execution_v2_dry_run


def test_v2_dry_run_recomputes_ready_population_and_keeps_25_rows():
    result = provider_execution_v2_dry_run.run_evaluation()
    assert len(result["rows"]) == 25
    assert result["summary"]["ready_denominator"] == 3
    assert result["summary"]["request_constructed"] == 3
    assert result["summary"]["fake_execution_success"] == 3
    assert result["summary"]["parse_success"] == 3
    assert result["summary"]["review_not_ready_executed"] == 0
    assert result["summary"]["false_execution_count"] == 0
    assert result["summary"]["real_provider_requests"] == 0
