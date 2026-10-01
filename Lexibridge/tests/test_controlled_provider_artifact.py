import json

from services import controlled_provider_evaluation as cpe


def test_artifact_writer_omits_prompt_context_secret_and_paths(tmp_path):
    sentinel = cpe.test_sentinel_value()
    item = cpe.build_evaluation_input({
        "evaluation_item_uid": "artifact-item-001",
        "course_or_domain": "synthetic",
        "english_term": "virtual machine",
        "normalized_english_term": "virtual machine",
        "bounded_context": "A bounded context that must not be stored in full.",
        "context_source_type": "synthetic_fixture",
        "privacy_classification": "SYNTHETIC",
    })
    failed = cpe.build_error_result(
        item=item,
        status="TRANSPORT_FAILED",
        safe_error_code="safe_unknown_transport_error",
        safe_error_message=f"Authorization: Bearer {sentinel} at " + "/" + "Users/example/key",
        provider_name="loopback-provider",
        model_name="candidate-model",
        prompt_version=cpe.PROMPT_VERSION,
    )
    run = cpe.ControlledProviderEvaluationRun(
        evaluation_id="eval-artifact",
        provider_name="loopback-provider",
        model_name="candidate-model",
        prompt_version=cpe.PROMPT_VERSION,
        output_schema_version=cpe.OUTPUT_SCHEMA_VERSION,
        pricing_config_version="test-pricing-v1",
        results=[failed],
        actual_external_provider_requests=0,
        private_course_provider_requests=0,
    )
    output = tmp_path / "artifact.json"

    cpe.write_evaluation_artifact(run, output, git_commit="abc123")
    payload = output.read_text(encoding="utf-8")
    data = json.loads(payload)

    assert data["evaluation_id"] == "eval-artifact"
    assert data["item_counts"]["total"] == 1
    assert data["results"][0]["bounded_context_stored"] is False
    assert sentinel not in payload
    assert "/Users/" not in payload
    assert "Authorization" not in payload
