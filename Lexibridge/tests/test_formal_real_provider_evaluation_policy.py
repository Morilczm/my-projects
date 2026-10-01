import json
from pathlib import Path

import pytest

from services import alignment_providers, llm_provider_config
from services.formal_document_alignment_provider_selection import (
    FORMAL_DEFAULT_PROVIDER_NAME,
    FormalDocumentAlignmentProviderSelectionError,
    resolve_default_formal_document_alignment_provider_selection,
    resolve_formal_document_alignment_provider_selection,
)
from services.formal_real_provider_evaluation_policy import (
    EXPECTED_11E_CORPUS_SHA256,
    EXPECTED_11E_GOLD_SHA256,
    REQUIRED_EVALUATION_ID,
    REQUIRED_RUNNER_ID,
    evaluate_formal_real_provider_evaluation_gate,
)


SECRET = "LEXIBRIDGE_11F_SENTINEL_SECRET_DO_NOT_RETURN"


def _env(**overrides):
    values = {
        "LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVAL_ENABLED": "1",
        "LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVALUATION_ID": REQUIRED_EVALUATION_ID,
        "LEXIBRIDGE_EXTERNAL_LLM_ENABLED": "1",
        "DEEPSEEK_API_KEY": SECRET,
    }
    values.update(overrides)
    return values


def _decision(tmp_path, **overrides):
    payload = {
        "env": _env(),
        "database_url": f"sqlite:///{tmp_path / 'evaluation.sqlite'}",
        "corpus_sha256": EXPECTED_11E_CORPUS_SHA256,
        "gold_sha256": EXPECTED_11E_GOLD_SHA256,
        "provider_name": llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME,
        "model_identity": "deepseek-chat",
        "runner_id": REQUIRED_RUNNER_ID,
        "request_budget": 35,
        "synthetic_only": True,
    }
    payload.update(overrides)
    return evaluate_formal_real_provider_evaluation_gate(**payload)


def test_default_formal_selection_stays_mock_and_external_still_fails_closed():
    selection = resolve_default_formal_document_alignment_provider_selection()

    assert selection.provider_name == FORMAL_DEFAULT_PROVIDER_NAME == "mock-rule-v1"
    with pytest.raises(FormalDocumentAlignmentProviderSelectionError):
        resolve_formal_document_alignment_provider_selection(
            alignment_providers.DISABLED_EXTERNAL_PROVIDER_NAME
        )


def test_complete_11f_evaluation_gate_allows_formal_deepseek_provider_without_leaking_secret(tmp_path):
    decision = _decision(tmp_path)

    assert decision.allowed is True
    assert decision.safe_error_code == ""
    assert decision.provider_name == llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
    assert decision.model_identity == "deepseek-chat"
    serialized = json.dumps(decision.to_safe_dict(), sort_keys=True)
    assert SECRET not in serialized
    assert "DEEPSEEK_API_KEY" in serialized
    assert "authorization" not in serialized.lower()
    assert "bearer" not in serialized.lower()


def test_disabled_deepseek_provider_fails_closed_even_with_complete_gate(tmp_path):
    decision = _decision(
        tmp_path,
        provider_name=alignment_providers.DISABLED_EXTERNAL_PROVIDER_NAME,
    )

    assert decision.allowed is False
    assert decision.safe_error_code == "FORMAL_REAL_PROVIDER_EVAL_PROVIDER_NOT_ENABLED"
    assert decision.gate_checks["provider_config_enabled"] is False
    assert decision.gate_checks["provider_executable"] is False


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"env": _env(LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVAL_ENABLED="")}, "FORMAL_REAL_PROVIDER_EVAL_GATE_DISABLED"),
        ({"env": _env(LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVALUATION_ID="other")}, "FORMAL_REAL_PROVIDER_EVAL_ID_INVALID"),
        ({"runner_id": "ordinary-api"}, "FORMAL_REAL_PROVIDER_EVAL_RUNNER_INVALID"),
        ({"corpus_sha256": "bad"}, "FORMAL_REAL_PROVIDER_EVAL_CORPUS_HASH_INVALID"),
        ({"gold_sha256": "bad"}, "FORMAL_REAL_PROVIDER_EVAL_GOLD_HASH_INVALID"),
        ({"provider_name": "unknown-provider"}, "FORMAL_REAL_PROVIDER_EVAL_PROVIDER_UNKNOWN"),
        ({"model_identity": "other-model"}, "FORMAL_REAL_PROVIDER_EVAL_MODEL_NOT_ALLOWED"),
        ({"request_budget": 36}, "FORMAL_REAL_PROVIDER_EVAL_BUDGET_INVALID"),
        ({"env": _env(DEEPSEEK_API_KEY="")}, "FORMAL_REAL_PROVIDER_EVAL_CREDENTIAL_MISSING"),
    ],
)
def test_incomplete_or_unsafe_evaluation_gate_fails_closed(tmp_path, overrides, error_code):
    decision = _decision(tmp_path, **overrides)

    assert decision.allowed is False
    assert decision.safe_error_code == error_code


def test_repository_or_default_database_url_fails_closed(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    repo_db_url = f"sqlite:///{repo_root / 'backend' / 'lexibridge.db'}"

    decision = _decision(tmp_path, database_url=repo_db_url)

    assert decision.allowed is False
    assert decision.safe_error_code == "FORMAL_REAL_PROVIDER_EVAL_DATABASE_NOT_ISOLATED"
