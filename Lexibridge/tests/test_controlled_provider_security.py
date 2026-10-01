from services import controlled_provider_evaluation as cpe


def test_credential_repr_safe_error_and_artifact_redact_sentinel():
    sentinel = cpe.test_sentinel_value()
    credential = cpe.Credential(sentinel)
    item = cpe.build_evaluation_input({
        "evaluation_item_uid": "security-item-001",
        "course_or_domain": "synthetic",
        "english_term": "string interning",
        "normalized_english_term": "string interning",
        "bounded_context": "String interning reuses equal immutable strings.",
        "context_source_type": "synthetic_fixture",
        "privacy_classification": "SYNTHETIC",
    })
    result = cpe.build_error_result(
        item=item,
        status="TRANSPORT_FAILED",
        safe_error_code="provider_auth_failed",
        safe_error_message=f"Bad credential {sentinel}",
        provider_name="loopback-provider",
        model_name="candidate-model",
        prompt_version=cpe.PROMPT_VERSION,
    )

    assert sentinel not in repr(credential)
    assert sentinel not in result.safe_error_message


def test_request_builder_excludes_private_identifiers_and_paths():
    item = cpe.build_evaluation_input({
        "evaluation_item_uid": "security-item-002",
        "course_or_domain": "synthetic",
        "english_term": "contextual inquiry",
        "normalized_english_term": "contextual inquiry",
        "bounded_context": "Contextual inquiry studies users in context.",
        "context_source_type": "synthetic_fixture",
        "privacy_classification": "SYNTHETIC",
    })
    payload = cpe.build_provider_request_payload(item, provider_name="loopback-provider", model_name="candidate-model")
    text = str(payload)

    assert payload["input"]["english_term"] == "contextual inquiry"
    assert "source_uid" not in text
    assert "/" + "Users/" not in text
    assert "cookie" not in text.lower()


def test_proxy_environment_is_not_trusted(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    transport = cpe.SafeEvaluationHTTPTransport()

    assert transport.trust_env is False
