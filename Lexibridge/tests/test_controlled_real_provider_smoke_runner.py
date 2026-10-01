import json
from pathlib import Path

import pytest

from scripts.evaluations import controlled_real_provider_smoke as smoke


def _authorized_env():
    return {
        smoke.EXTERNAL_ENABLED_ENV: "1",
        smoke.EVAL_ENABLED_ENV: "1",
        smoke.EVAL_ID_ENV: smoke.REQUIRED_EVALUATION_ID,
        smoke.CREDENTIAL_ENV: "fake-test-credential",
    }


def test_runner_defaults_to_zero_requests(tmp_path):
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=False,
        confirmation="",
        state_path=tmp_path / "state.json",
        transport_factory=lambda: smoke.FakeObservedTransport(),
    )
    assert result["real_provider_requests"] == 0
    assert result["status"] == "REAL_PROVIDER_SMOKE_NOT_AUTHORIZED"


def test_missing_cli_confirmation_and_credential_make_zero_requests(tmp_path):
    cases = (
        (_authorized_env(), True, ""),
        ({**_authorized_env(), smoke.CREDENTIAL_ENV: ""}, True, smoke.CONFIRMATION),
    )
    for env, execute, confirmation in cases:
        transport = smoke.FakeObservedTransport()
        result = smoke.run(
            env=env,
            execute_single_real_request=execute,
            confirmation=confirmation,
            state_path=tmp_path / f"{len(transport.calls)}-state.json",
            transport_factory=lambda: transport,
        )
        assert result["real_provider_requests"] == 0
        assert transport.calls == []


def test_single_ready_item_uses_fixed_budget_and_production_parser(tmp_path):
    transport = smoke.FakeObservedTransport()
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: transport,
    )
    assert result["real_provider_requests"] == 1
    assert result["retry_count"] == 0
    assert result["parse_status"] == "parsed"
    assert result["schema_status"] == "valid"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["max_retries"] == 0
    assert call["prompt_version"] == smoke.PROMPT_VERSION
    assert call["selected_ready_count"] == 1


def test_state_marker_prevents_second_execution_and_conflicting_payload(tmp_path):
    state = tmp_path / "state.json"
    first_transport = smoke.FakeObservedTransport()
    first = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=state,
        transport_factory=lambda: first_transport,
    )
    second_transport = smoke.FakeObservedTransport()
    second = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=state,
        transport_factory=lambda: second_transport,
    )
    assert first["real_provider_requests"] == 1
    assert second["real_provider_requests"] == 0
    assert second["idempotency_outcome"] == "already_attempted"
    assert second_transport.calls == []


def test_selection_and_request_builder_do_not_read_gold(monkeypatch, tmp_path):
    original = Path.read_text

    def guarded_read(path, *args, **kwargs):
        if Path(path).name == "gold.json":
            raise AssertionError("gold must not be read before response evaluation")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: smoke.FakeObservedTransport(),
    )
    assert result["real_provider_requests"] == 1
    assert result["gold_used_in_request"] is False


def test_review_and_not_ready_rows_never_enter_selected_request():
    selected = smoke.select_single_ready_sample()
    assert selected["readiness_decision"] == "READY"
    assert selected["ready_population"] == 3
    assert selected["selected_item_count"] == 1


def test_sanitized_artifacts_exclude_bodies_credentials_and_paths(tmp_path):
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: smoke.FakeObservedTransport(),
    )
    manifest, outcome = smoke.sanitized_artifacts(result)
    serialized = json.dumps([manifest, outcome], ensure_ascii=False)
    assert "Authorization" not in serialized
    assert "fake-test-credential" not in serialized
    assert "/Users/" not in serialized
    assert "request_body" not in serialized
    assert "response_body" not in serialized


def test_failed_transport_is_never_retried(tmp_path):
    transport = smoke.FakeObservedTransport(mode="timeout")
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: transport,
    )
    assert result["real_provider_requests"] == 1
    assert result["retry_count"] == 0
    assert len(transport.calls) == 1


def test_non_json_success_response_maps_to_parse_failure_without_retry(tmp_path):
    transport = smoke.FakeObservedTransport(mode="non_json")
    result = smoke.run(
        env=_authorized_env(),
        execute_single_real_request=True,
        confirmation=smoke.CONFIRMATION,
        state_path=tmp_path / "state.json",
        transport_factory=lambda: transport,
    )
    assert result["status"] == "REAL_PROVIDER_SMOKE_PARSE_FAILED"
    assert result["parse_status"] == "failed_closed"
    assert result["real_provider_requests"] == 1
    assert result["retry_count"] == 0
    assert len(transport.calls) == 1


def test_cli_requires_repository_external_state_path(tmp_path):
    with pytest.raises(ValueError, match="repository-external"):
        smoke.run(
            env=_authorized_env(),
            execute_single_real_request=True,
            confirmation=smoke.CONFIRMATION,
            state_path=smoke.ROOT / "unsafe-state.json",
            transport_factory=lambda: smoke.FakeObservedTransport(),
        )
