from dataclasses import replace
from pathlib import Path

import pytest

from services import alignment_prompting, alignment_providers
from services import document_alignment_item_preparation as preparation
from services import llm_provider_config
from services.formal_document_alignment_provider_selection import (
    FormalDocumentAlignmentProviderSelectionError,
    resolve_default_formal_document_alignment_provider_selection,
    resolve_formal_document_alignment_provider_selection,
)
from services.formal_real_provider_evaluation_policy import (
    EXPECTED_11E_CORPUS_SHA256,
    EXPECTED_11E_GOLD_SHA256,
    REQUIRED_EVALUATION_ID,
    REQUIRED_RUNNER_ID,
    FormalRealProviderEvaluationDecision,
    evaluate_formal_real_provider_evaluation_gate,
)
from test_document_alignment_processing_orchestrator_integration import (
    _cleanup,
    _preparation_dependencies,
    _setup_governed_workflow,
)


PROVIDER = llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
MODEL = "deepseek-chat"
FAKE_KEY = "LEXIBRIDGE_11K_OFFLINE_FAKE_KEY"


def _decision(tmp_path, **overrides):
    env = {
        "LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVAL_ENABLED": "1",
        "LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVALUATION_ID": REQUIRED_EVALUATION_ID,
        "LEXIBRIDGE_EXTERNAL_LLM_ENABLED": "1",
        "DEEPSEEK_API_KEY": FAKE_KEY,
    }
    payload = {
        "env": env,
        "database_url": f"sqlite:///{tmp_path / 'evaluation.sqlite'}",
        "corpus_sha256": EXPECTED_11E_CORPUS_SHA256,
        "gold_sha256": EXPECTED_11E_GOLD_SHA256,
        "provider_name": PROVIDER,
        "model_identity": MODEL,
        "runner_id": REQUIRED_RUNNER_ID,
        "request_budget": 35,
        "synthetic_only": True,
    }
    payload.update(overrides)
    return evaluate_formal_real_provider_evaluation_gate(**payload)


def test_external_provider_stays_closed_without_verified_context():
    with pytest.raises(FormalDocumentAlignmentProviderSelectionError):
        resolve_formal_document_alignment_provider_selection(PROVIDER)
    assert resolve_default_formal_document_alignment_provider_selection().provider_name == "mock-rule-v1"


@pytest.mark.parametrize(
    "override",
    [
        {"runner_id": "ordinary-api"},
        {"corpus_sha256": "wrong"},
        {"gold_sha256": "wrong"},
        {"database_url": f"sqlite:///{Path.cwd() / 'backend' / 'lexibridge.db'}"},
        {"provider_name": "deepseek-alignment-v1-disabled"},
        {"model_identity": "other-model"},
        {"synthetic_only": False},
    ],
)
def test_invalid_gate_decisions_cannot_select_external_provider(tmp_path, override):
    decision = _decision(tmp_path, **override)
    assert decision.allowed is False
    with pytest.raises(FormalDocumentAlignmentProviderSelectionError):
        resolve_formal_document_alignment_provider_selection(
            PROVIDER,
            evaluation_context=decision,
        )


def test_only_policy_issued_context_selects_external_provider(tmp_path):
    decision = _decision(tmp_path)
    assert decision.allowed is True
    selection = resolve_formal_document_alignment_provider_selection(
        PROVIDER,
        evaluation_context=decision,
    )
    assert selection.provider_name == PROVIDER
    assert selection.model_identity == MODEL

    forged = FormalRealProviderEvaluationDecision(
        allowed=True,
        provider_name=PROVIDER,
        model_identity=MODEL,
        request_budget=35,
    )
    with pytest.raises(FormalDocumentAlignmentProviderSelectionError):
        resolve_formal_document_alignment_provider_selection(
            PROVIDER,
            evaluation_context=forged,
        )
    with pytest.raises(TypeError):
        resolve_formal_document_alignment_provider_selection(
            PROVIDER,
            allow_external_provider=True,
        )


def test_same_verified_context_reaches_item_preparation(app_module, tmp_path):
    with app_module.app.app_context():
        run_uid, _ = _setup_governed_workflow(app_module, "11k-bridge", bootstrap=True)
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        run.provider_preference = PROVIDER
        run.model_preference = MODEL
        run.prompt_version = alignment_prompting.STRUCTURED_PROMPT_VERSION
        app_module.db.session.commit()
        item = app_module.DocumentAlignmentWorkflowItem.query.one()
        decision = _decision(tmp_path)
        dependencies = replace(
            _preparation_dependencies(app_module, app_module.db.session),
            evaluation_context=decision,
        )

        result = preparation.prepare_document_alignment_item(
            preparation.PrepareDocumentAlignmentItemCommand(run_uid, item.item_uid),
            dependencies,
        )

        assert result.outcome == preparation.PREPARATION_OUTCOME_PREPARED
        assert result.prepared_input.provider_name == PROVIDER
        assert result.prepared_input.model_identity == MODEL
        _cleanup(app_module)


def test_provider_factory_uses_offline_transport_without_real_network(monkeypatch):
    calls = {"real_network": 0}

    class OfflineTransport:
        def generate(self, prompt, config, options):
            calls["real_network"] += 0
            raise AssertionError("offline bridge contract stops before a real request")

    provider = alignment_providers.GuardedLLMAlignmentProvider(
        PROVIDER,
        transport=OfflineTransport(),
    )
    assert provider.provider_name == PROVIDER
    assert provider.transport.__class__.__name__ == "OfflineTransport"
    assert calls["real_network"] == 0
