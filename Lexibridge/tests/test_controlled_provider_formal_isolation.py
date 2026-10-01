from services import controlled_provider_evaluation as cpe
from services import formal_document_alignment_provider_selection as formal_selection
from test_pilot_readiness_verdict import load_readiness_module


def test_formal_provider_contract_remains_mock_only():
    selection = formal_selection.resolve_default_formal_document_alignment_provider_selection()
    assert selection.provider_name == "mock-rule-v1"
    assert selection.model_identity == "mock-rule-v1:v1"
    assert selection.prompt_version == "alignment-v1"
    assert cpe.PROMPT_VERSION != "alignment-v1"


def test_evaluation_dry_run_does_not_create_formal_records(app_module):
    with app_module.app.app_context():
        before_runs = app_module.DocumentAlignmentWorkflowRun.query.count()
        before_items = app_module.DocumentAlignmentWorkflowItem.query.count()
        before_cards = app_module.ConceptAlignmentCard.query.count()

        item = cpe.build_evaluation_input({
            "evaluation_item_uid": "isolation-item-001",
            "course_or_domain": "synthetic",
            "english_term": "prototype testing",
            "normalized_english_term": "prototype testing",
            "bounded_context": "Prototype testing checks an artifact with users.",
            "context_source_type": "synthetic_fixture",
            "privacy_classification": "SYNTHETIC",
        })
        run = cpe.run_controlled_provider_evaluation(
            [item],
            provider_name="loopback-provider",
            model_name="candidate-model",
            dry_run=True,
        )

        assert run.results[0].status == "SUCCEEDED"
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == before_runs
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == before_items
        assert app_module.ConceptAlignmentCard.query.count() == before_cards


def test_readiness_contains_controlled_provider_contract_conditions():
    module = load_readiness_module()
    conditions = set(module.default_conditions("small-pilot"))

    assert "CONTROLLED_PROVIDER_EVALUATION_CONTRACT_PRESENT" in conditions
    assert "CONTROLLED_PROVIDER_FAKE_HTTP_E2E_VERIFIED" in conditions
    assert "REAL_PROVIDER_NOT_EXECUTED" in conditions
    assert "FORMAL_WORKFLOW_PROVIDER_UNCHANGED" in conditions
    assert "PRIVATE_COURSE_EXTERNAL_SEND_BLOCKED" in conditions
