import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from services.document_alignment_workflow_contract import (
    DOCUMENT_ALIGNMENT_ITEM_VERIFICATION_EXECUTION_STATUSES,
    ITEM_VERIFICATION_EXECUTION_STATUS_PREPARED,
)


def _uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _execution(app_module, **overrides):
    values = {
        "execution_key": _uid("item-verification-execution-v1"),
        "workflow_run_uid": _uid("workflow-run"),
        "workflow_item_uid": _uid("workflow-item"),
        "workflow_item_key": _uid("item-key-v1"),
        "execution_version": "item-verification-execution-v1",
        "workflow_version": "formal-document-alignment-v1",
        "provider_name": "replay-llm-v1",
        "model_identity": "replay-model-v1",
        "retrieval_version": "retrieval-v1",
        "prompt_version": "prompt-v1",
        "parser_version": "parser-v1",
        "output_schema_version": "alignment-output-v1",
        "safe_input_fingerprint": "a" * 64,
    }
    values.update(overrides)
    return app_module.DocumentAlignmentItemVerificationExecution(**values)


@pytest.fixture()
def clean_execution_table(app_module):
    with app_module.app.app_context():
        app_module.db.session.rollback()
        app_module.DocumentAlignmentItemVerificationExecution.query.delete()
        app_module.db.session.commit()
    yield
    with app_module.app.app_context():
        app_module.db.session.rollback()
        app_module.DocumentAlignmentItemVerificationExecution.query.delete()
        app_module.db.session.commit()


def test_execution_model_table_required_fields_defaults_and_status_contract(
    app_module,
    clean_execution_table,
):
    model = app_module.DocumentAlignmentItemVerificationExecution
    assert model.__tablename__ == "document_alignment_item_verification_executions"
    required = {
        "execution_key",
        "workflow_run_uid",
        "workflow_item_uid",
        "workflow_item_key",
        "execution_version",
        "workflow_version",
        "provider_name",
        "model_identity",
        "retrieval_version",
        "prompt_version",
        "parser_version",
        "output_schema_version",
        "safe_input_fingerprint",
        "execution_status",
        "created_at",
        "updated_at",
    }
    assert required <= set(model.__table__.columns.keys())
    assert all(model.__table__.columns[name].nullable is False for name in required)
    assert DOCUMENT_ALIGNMENT_ITEM_VERIFICATION_EXECUTION_STATUSES == frozenset(
        {
            "prepared",
            "draft_ready",
            "preflight_passed",
            "preflight_blocked",
            "provider_started",
            "provider_completed",
            "verification_persisted",
            "attach_pending",
            "attached",
            "needs_review",
            "blocked",
            "failed",
        }
    )
    assert {"approved", "published", "student_visible"}.isdisjoint(
        DOCUMENT_ALIGNMENT_ITEM_VERIFICATION_EXECUTION_STATUSES
    )

    with app_module.app.app_context():
        execution = _execution(app_module)
        app_module.db.session.add(execution)
        app_module.db.session.commit()
        assert execution.execution_status == ITEM_VERIFICATION_EXECUTION_STATUS_PREPARED
        assert execution.created_at
        assert execution.updated_at


def test_execution_model_has_safe_recovery_fields_and_no_sensitive_payload_columns(app_module):
    columns = set(app_module.DocumentAlignmentItemVerificationExecution.__table__.columns.keys())
    assert {
        "draft_card_uid",
        "preflight_run_uid",
        "verification_run_uid",
        "safe_output_fingerprint",
        "provider_started_at",
        "provider_completed_at",
        "attached_at",
        "safe_error_code",
        "safe_error_message",
    } <= columns
    forbidden = {
        "raw_document",
        "document_text",
        "chunk_text",
        "evidence_body",
        "raw_evidence",
        "prompt",
        "prompt_body",
        "provider_output",
        "raw_provider_output",
        "credential",
        "api_key",
        "authorization",
        "cookie",
        "lease_token",
        "worker_id",
        "request_id",
        "metadata_json",
    }
    assert forbidden.isdisjoint(columns)


def test_execution_model_unique_and_reference_constraints(app_module, clean_execution_table):
    with app_module.app.app_context():
        first = _execution(
            app_module,
            execution_key="item-verification-execution-v1:" + "1" * 64,
            draft_card_uid="shared-approved-card",
            preflight_run_uid="preflight-one",
            verification_run_uid="verification-one",
        )
        app_module.db.session.add(first)
        app_module.db.session.commit()

        for duplicate_field in ("execution_key", "preflight_run_uid", "verification_run_uid"):
            duplicate = _execution(
                app_module,
                draft_card_uid="shared-approved-card",
                **{duplicate_field: getattr(first, duplicate_field)},
            )
            app_module.db.session.add(duplicate)
            with pytest.raises(IntegrityError):
                app_module.db.session.commit()
            app_module.db.session.rollback()

        nullable_a = _execution(app_module, draft_card_uid="shared-approved-card")
        nullable_b = _execution(app_module, draft_card_uid="shared-approved-card")
        app_module.db.session.add_all([nullable_a, nullable_b])
        app_module.db.session.commit()
        assert nullable_a.preflight_run_uid is None
        assert nullable_b.verification_run_uid is None


def test_execution_model_validation_rejects_invalid_status_required_values_and_secret_errors(
    app_module,
    clean_execution_table,
):
    with pytest.raises(ValueError):
        _execution(app_module, execution_status="approved")
    with pytest.raises(ValueError):
        _execution(app_module, execution_key="")
    with pytest.raises(ValueError):
        _execution(app_module, safe_input_fingerprint="not-a-sha256")
    with pytest.raises(ValueError):
        _execution(app_module, safe_output_fingerprint="not-a-sha256")
    with pytest.raises(ValueError):
        _execution(app_module, safe_error_message="LEXIBRIDGE_SENTINEL_SECRET_9C5B1")


def test_execution_model_indexes_are_named_and_stable(app_module):
    indexes = {
        index.name: (index.unique, tuple(column.name for column in index.columns))
        for index in app_module.DocumentAlignmentItemVerificationExecution.__table__.indexes
    }
    assert indexes["uq_document_alignment_item_verification_execution_key"] == (
        True,
        ("execution_key",),
    )
    assert indexes["uq_document_alignment_item_verification_preflight_uid"] == (
        True,
        ("preflight_run_uid",),
    )
    assert indexes["uq_document_alignment_item_verification_run_uid"] == (
        True,
        ("verification_run_uid",),
    )
    assert indexes["ix_document_alignment_item_verification_item_status"] == (
        False,
        ("workflow_item_uid", "execution_status"),
    )
