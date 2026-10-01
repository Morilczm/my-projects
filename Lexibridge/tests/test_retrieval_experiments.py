from services.retrieval_experiments import evaluate_backend_cases, recommend_backend


def test_retrieval_experiment_metrics_and_recommendation():
    cases = [
        {"query": "Fourier Transform", "expected_chinese_evidence": "傅里叶变换用于将时域信号表示为频率分量。"},
        {"query": "No Evidence", "expect_no_evidence": True},
    ]

    def search_func(_backend, case):
        if case["query"] == "No Evidence":
            return []
        return [{"content_excerpt": "傅里叶变换用于将时域信号表示为频率分量。", "authorization_status": "allowed_for_course_use"}]

    metrics = evaluate_backend_cases(cases, "lexical", search_func)
    assert metrics["top1_accuracy"] == 0.5
    assert metrics["no_evidence_forced_match_rate"] == 0
    recommendation = recommend_backend({"lexical": metrics, "hybrid": dict(metrics, top1_accuracy=0.51)})
    assert "Do not promote" in recommendation or "Keep lexical" in recommendation
