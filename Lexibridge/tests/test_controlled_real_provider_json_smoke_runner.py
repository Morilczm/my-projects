import json

from scripts.evaluations import controlled_real_provider_json_smoke as smoke


def _authorized_env():
    return {
        smoke.EXTERNAL_ENABLED_ENV: "1",
        smoke.EVAL_ENABLED_ENV: "1",
        smoke.EVAL_ID_ENV: smoke.REQUIRED_EVALUATION_ID,
        smoke.CREDENTIAL_ENV: "fake-test-credential",
    }


def _ids():
    values = iter(("eval-fixed", "audit-fixed", "salt-fixed"))
    return lambda: next(values)


def test_json_smoke_defaults_to_zero_requests(tmp_path):
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=False,
        confirmation="",
        state_path=tmp_path / "state.json",
        transport_factory=lambda: smoke.FakeObservedTransport(),
        id_factory=_ids(),
    )
    assert result["execution_status"] == "REAL_PROVIDER_JSON_SMOKE_NOT_AUTHORIZED"
    assert result["real_provider_requests"] == 0


def test_json_smoke_fake_run_freezes_contract_and_new_request_identity(tmp_path):
    transport = smoke.FakeObservedTransport()
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: transport,
        id_factory=_ids(),
    )

    manifest = result["request_manifest"]
    assert result["execution_status"] == "REAL_PROVIDER_JSON_SMOKE_SUCCEEDED"
    assert result["real_provider_requests"] == 1
    assert result["parse_status"] == "parsed"
    assert result["schema_status"] == "valid"
    assert result["latency_ms"] is None
    assert result["latency_status"] == "provider_transport_latency_unavailable"
    assert result["parser_version"] == "alignment-parser-json-v2"
    assert result["selected_opaque_item_id"] == smoke.EXPECTED_SELECTED_OPAQUE_ITEM_ID
    assert manifest["evaluation_run_id"] == "12ICB-eval-fixed"
    assert manifest["audit_correlation_id"] == "12ICB-audit-audit-fixed"
    assert manifest["prompt_version"] == "alignment-json-v2"
    assert manifest["response_format"] == {"type": "json_object"}
    assert manifest["max_tokens"] == 1000
    assert manifest["retry_budget"] == 0
    assert manifest["request_budget"] == 1
    assert manifest["idempotency_key_hash"] != smoke.PREVIOUS_IDEMPOTENCY_KEY_HASH
    assert len(transport.calls) == 1


def test_selection_drift_blocks_before_transport(tmp_path, monkeypatch):
    selected = smoke.base_runner.select_single_ready_sample()
    monkeypatch.setattr(
        smoke.base_runner,
        "select_single_ready_sample",
        lambda: {**selected, "selected_opaque_item_id": "drifted"},
    )
    transport = smoke.FakeObservedTransport()

    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: transport,
        id_factory=_ids(),
    )

    assert result["execution_status"] == "REAL_PROVIDER_JSON_SMOKE_SELECTION_DRIFT"
    assert result["real_provider_requests"] == 0
    assert transport.calls == []


def test_timeout_is_one_attempt_with_no_retry(tmp_path):
    transport = smoke.FakeObservedTransport(mode="timeout")
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: transport,
        id_factory=_ids(),
    )

    assert result["execution_status"] == "REAL_PROVIDER_JSON_SMOKE_TIMEOUT"
    assert result["real_provider_requests"] == 1
    assert result["retry_count"] == 0
    assert len(transport.calls) == 1


def test_sanitized_artifacts_have_shape_metadata_without_bodies_or_credentials(tmp_path):
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: smoke.FakeObservedTransport(),
        id_factory=_ids(),
    )
    manifest, outcome = smoke.sanitized_artifacts(result)
    serialized = json.dumps([manifest, outcome], ensure_ascii=False)

    assert outcome["output_shape"]["content_present"] is True
    assert outcome["output_shape"]["looks_like_json_object"] is True
    assert outcome["model_compatibility"]["compatible"] is True
    assert "request_body" not in serialized
    assert "response_body" not in serialized
    assert "prompt_body" not in serialized
    assert "fake-test-credential" not in serialized
    assert "Authorization" not in serialized
    assert "/Users/" not in serialized


def test_fake_success_allows_post_response_gold_evaluation_only(tmp_path):
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: smoke.FakeObservedTransport(),
        id_factory=_ids(),
    )

    assert result["gold_used_in_request"] is False
    assert result["gold_used_post_response_evaluation"] is True
    assert result["offline_quality"]["canonical_term_correct"] is True
    assert result["offline_quality"]["evidence_citation_valid"] is True
    assert result["offline_quality"]["hallucinated_provenance_count"] == 0
