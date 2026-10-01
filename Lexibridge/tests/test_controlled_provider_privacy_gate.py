from services import controlled_provider_evaluation as cpe


def _item(privacy="SYNTHETIC", context="Bounded synthetic context."):
    return {
        "evaluation_item_uid": "privacy-item-001",
        "course_or_domain": "computer science",
        "english_term": "time complexity",
        "normalized_english_term": "time complexity",
        "bounded_context": context,
        "context_source_type": "synthetic_fixture",
        "privacy_classification": privacy,
    }


def test_local_only_private_input_fails_before_credential_or_transport():
    input_item = cpe.build_evaluation_input(_item("LOCAL_ONLY_PRIVATE"))
    probe = cpe.CountingTransport()

    result = cpe.run_controlled_provider_evaluation(
        [input_item],
        provider_name="loopback-provider",
        model_name="candidate-model",
        credential_loader=cpe.StaticCredentialLoader("runtime-only-test-value"),
        pricing=cpe.test_pricing_config(),
        budget=cpe.test_budget_config(),
        transport=probe,
        execute_live=True,
        evaluation_test_mode=True,
    )

    assert result.results[0].status == "PRIVACY_BLOCKED"
    assert result.private_course_provider_requests == 0
    assert probe.request_count == 0


def test_unknown_or_missing_privacy_classification_is_rejected():
    for privacy in ("UNKNOWN", "", None):
        payload = _item(privacy)
        if privacy is None:
            payload.pop("privacy_classification")
        outcome = cpe.validate_evaluation_input(payload)
        assert outcome.ok is False
        assert outcome.error_code == "privacy_classification_invalid"


def test_private_paths_and_unbounded_context_fail_request_minimization():
    local_path = "/" + "Users/example/private.pdf"
    path_outcome = cpe.validate_evaluation_input(_item("SYNTHETIC", f"Read {local_path}"))
    long_context = "x" * (cpe.MAX_BOUNDED_CONTEXT_CHARS + 1)
    length_outcome = cpe.validate_evaluation_input(_item("SYNTHETIC", long_context))

    assert path_outcome.ok is False
    assert path_outcome.error_code == "request_not_minimized"
    assert length_outcome.ok is False
    assert length_outcome.error_code == "request_not_minimized"
