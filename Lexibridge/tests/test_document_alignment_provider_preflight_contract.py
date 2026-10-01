import pytest

from services import document_alignment_item_preparation as preparation
from services import provider_governance, provider_preflight
from services.formal_document_alignment_provider_selection import (
    resolve_default_formal_document_alignment_provider_selection,
)
from test_document_alignment_processing_orchestrator_integration import (
    _cleanup,
    _preparation_dependencies,
    _setup_governed_workflow,
)


@pytest.fixture(autouse=True)
def app_context(app_module):
    with app_module.app.app_context():
        app_module.AlignmentProviderPreflightRun.query.filter_by(
            execution_key="provider-selection-9c5f1-preflight"
        ).delete(synchronize_session=False)
        app_module.db.session.commit()
        yield
        _cleanup(app_module)
        app_module.AlignmentProviderPreflightRun.query.filter_by(
            execution_key="provider-selection-9c5f1-preflight"
        ).delete(synchronize_session=False)
        app_module.db.session.commit()


def test_historical_null_selection_fails_closed_before_provider_or_usage(app_module):
    run_uid, _ = _setup_governed_workflow(app_module, "null-selection", bootstrap=True)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    run.provider_preference = ""
    run.model_preference = ""
    run.prompt_version = ""
    app_module.db.session.commit()
    item = app_module.DocumentAlignmentWorkflowItem.query.one()
    mapping_count = app_module.DocumentAlignmentItemVerificationExecution.query.count()
    preflight_count = app_module.AlignmentProviderPreflightRun.query.count()
    verification_count = app_module.AlignmentVerificationRun.query.count()
    usage_count = app_module.AlignmentProviderUsageRecord.query.count()

    result = preparation.prepare_document_alignment_item(
        preparation.PrepareDocumentAlignmentItemCommand(
            workflow_run_uid=run_uid,
            workflow_item_uid=item.item_uid,
        ),
        _preparation_dependencies(app_module, app_module.db.session),
    )

    assert result.outcome == "provider_selection_missing"
    assert result.error_code == "DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_MISSING"
    assert "provider" in result.error_message.casefold()
    assert app_module.DocumentAlignmentItemVerificationExecution.query.count() == mapping_count
    assert app_module.AlignmentProviderPreflightRun.query.count() == preflight_count
    assert app_module.AlignmentVerificationRun.query.count() == verification_count
    assert app_module.AlignmentProviderUsageRecord.query.count() == usage_count
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    assert run.provider_preference == run.model_preference == run.prompt_version == ""


@pytest.mark.parametrize(
    "provider_name",
    ["deepseek-alignment-v1-disabled", "unknown-provider", "custom-provider"],
)
def test_unsafe_persisted_selection_fails_closed_before_evidence_or_provider(
    app_module,
    provider_name,
):
    run_uid, _ = _setup_governed_workflow(app_module, "unsafe-selection", bootstrap=True)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    run.provider_preference = provider_name
    run.model_preference = f"{provider_name}:v1"
    run.prompt_version = "alignment-v1"
    app_module.db.session.commit()
    item = app_module.DocumentAlignmentWorkflowItem.query.one()
    preflight_count = app_module.AlignmentProviderPreflightRun.query.count()
    usage_count = app_module.AlignmentProviderUsageRecord.query.count()

    result = preparation.prepare_document_alignment_item(
        preparation.PrepareDocumentAlignmentItemCommand(run_uid, item.item_uid),
        _preparation_dependencies(app_module, app_module.db.session),
    )

    assert result.outcome == "provider_selection_invalid"
    assert result.error_code == "DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_INVALID"
    assert app_module.AlignmentProviderPreflightRun.query.count() == preflight_count
    assert app_module.AlignmentProviderUsageRecord.query.count() == usage_count


@pytest.mark.parametrize(
    ("model_identity", "prompt_version"),
    [
        ("mock-rule-v1:other", "alignment-v1"),
        ("mock-rule-v1:v1", "alignment-verification-v1"),
    ],
)
def test_default_provider_identity_drift_fails_closed(
    app_module,
    model_identity,
    prompt_version,
):
    run_uid, _ = _setup_governed_workflow(app_module, "identity-drift", bootstrap=True)
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    run.provider_preference = "mock-rule-v1"
    run.model_preference = model_identity
    run.prompt_version = prompt_version
    app_module.db.session.commit()
    item = app_module.DocumentAlignmentWorkflowItem.query.one()

    result = preparation.prepare_document_alignment_item(
        preparation.PrepareDocumentAlignmentItemCommand(run_uid, item.item_uid),
        _preparation_dependencies(app_module, app_module.db.session),
    )

    assert result.outcome == "provider_selection_invalid"
    assert result.error_code == "DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_INVALID"


def test_admission_default_selection_passes_formal_policy_and_preflight(app_module):
    selection = resolve_default_formal_document_alignment_provider_selection()
    course = "Formal Provider Selection Course"

    gate = provider_governance.evaluate_provider_request(
        app_module.db.session,
        app_module.AlignmentProviderPolicy,
        app_module.AlignmentProviderUsageRecord,
        selection.provider_name,
        {
            "course": course,
            "english_term": "Fourier Transform",
            "chinese_term": "傅里叶变换",
        },
        actor_role="teacher",
        now_fn=app_module.current_time_text,
    )
    preflight_run, report = provider_preflight.run_provider_preflight(
        app_module.db.session,
        app_module.AlignmentProviderPreflightRun,
        app_module.AlignmentProviderPolicy,
        selection.provider_name,
        course=course,
        include_replay_dry_run=True,
        execution_key="provider-selection-9c5f1-preflight",
        now_fn=app_module.current_time_text,
        commit=True,
    )

    assert gate["allowed"] is True
    assert gate["requires_human_review"] is True
    assert report["overall_ready"] is True
    assert report["blocking_reasons"] == []
    assert report["external_calls_enabled"] is False
    assert preflight_run.provider_name == selection.provider_name
