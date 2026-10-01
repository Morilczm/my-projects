from services import controlled_provider_evaluation as cpe


def _item(context="Short synthetic context."):
    return cpe.build_evaluation_input({
        "evaluation_item_uid": "budget-item-001",
        "course_or_domain": "engineering math",
        "english_term": "gradient",
        "normalized_english_term": "gradient",
        "bounded_context": context,
        "context_source_type": "synthetic_fixture",
        "privacy_classification": "SYNTHETIC",
    })


def test_cost_preflight_blocks_before_transport_when_worst_case_exceeds_cap():
    transport = cpe.CountingTransport()
    result = cpe.run_controlled_provider_evaluation(
        [_item()],
        provider_name="loopback-provider",
        model_name="candidate-model",
        credential_loader=cpe.StaticCredentialLoader("runtime-only-test-value"),
        pricing=cpe.test_pricing_config(input_unit_price=1.0, output_unit_price=1.0),
        budget=cpe.test_budget_config(max_estimated_cost_per_item=0.000001, max_estimated_cost_per_batch=0.000001),
        transport=transport,
        execute_live=True,
        evaluation_test_mode=True,
        test_endpoint="http://127.0.0.1:1/v1/candidates",
        test_loopback_ports={1},
    )

    assert result.results[0].status == "COST_BLOCKED"
    assert result.results[0].safe_error_code == "cost_budget_exhausted"
    assert transport.request_count == 0


def test_credential_gate_runs_before_cost_gate_and_transport():
    transport = cpe.CountingTransport()
    result = cpe.run_controlled_provider_evaluation(
        [_item()],
        provider_name="loopback-provider",
        model_name="candidate-model",
        credential_loader=cpe.StaticCredentialLoader(""),
        pricing=cpe.test_pricing_config(input_unit_price=1.0, output_unit_price=1.0),
        budget=cpe.test_budget_config(max_estimated_cost_per_item=0.000001, max_estimated_cost_per_batch=0.000001),
        transport=transport,
        execute_live=True,
        evaluation_test_mode=True,
        test_endpoint="http://127.0.0.1:1/v1/candidates",
        test_loopback_ports={1},
    )

    assert result.results[0].status == "CREDENTIAL_UNAVAILABLE"
    assert result.results[0].safe_error_code == "credential_unavailable"
    assert transport.request_count == 0


def test_token_and_request_caps_are_enforced_before_network():
    large = _item("x" * 120)
    token_block = cpe.run_controlled_provider_evaluation(
        [large],
        provider_name="loopback-provider",
        model_name="candidate-model",
        credential_loader=cpe.StaticCredentialLoader("runtime-only-test-value"),
        pricing=cpe.test_pricing_config(),
        budget=cpe.test_budget_config(max_input_tokens=2),
        transport=cpe.CountingTransport(),
        execute_live=True,
        evaluation_test_mode=True,
        test_endpoint="http://127.0.0.1:1/v1/candidates",
        test_loopback_ports={1},
    )
    request_block = cpe.run_controlled_provider_evaluation(
        [_item(), _item()],
        provider_name="loopback-provider",
        model_name="candidate-model",
        credential_loader=cpe.StaticCredentialLoader("runtime-only-test-value"),
        pricing=cpe.test_pricing_config(),
        budget=cpe.test_budget_config(max_total_requests=1),
        transport=cpe.CountingTransport(),
        execute_live=True,
        evaluation_test_mode=True,
        test_endpoint="http://127.0.0.1:1/v1/candidates",
        test_loopback_ports={1},
    )

    assert token_block.results[0].safe_error_code == "input_token_cap_exceeded"
    assert request_block.results[0].status == "SUCCEEDED"
    assert request_block.results[1].safe_error_code == "request_budget_exhausted"


def test_retry_reserve_is_included_in_worst_case_cost():
    item = _item()
    budget = cpe.test_budget_config(max_requests_per_item=2, max_estimated_cost_per_item=0.0005)
    pricing = cpe.test_pricing_config(input_unit_price=0.01, output_unit_price=0.01)
    estimate = cpe.estimate_worst_case_cost(item, pricing, budget)

    assert estimate.retry_reserved_attempts == 2
    assert estimate.worst_case_cost > 0
