from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_contract_constants_match_adr_and_models(app_module):
    from services import document_alignment_workflow_contract as contract

    assert contract.WORKFLOW_NAME == "FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION"
    assert contract.CANONICAL_INPUT == "GOVERNED_KNOWLEDGE_SOURCE"
    assert contract.EXECUTION_MODEL == "ASYNC_JOB_ORCHESTRATION"
    assert contract.DATA_POLICY == "NO_LEGACY_AND_FORMAL_DUAL_WRITE"
    assert "queued" in contract.DOCUMENT_ALIGNMENT_WORKFLOW_STATUSES
    assert "ready_for_review" in contract.DOCUMENT_ALIGNMENT_WORKFLOW_STATUSES
    assert "approved" not in contract.DOCUMENT_ALIGNMENT_WORKFLOW_STATUSES
    assert "published" not in contract.DOCUMENT_ALIGNMENT_WORKFLOW_STATUSES
    assert "student_visible" not in contract.DOCUMENT_ALIGNMENT_WORKFLOW_STATUSES
    assert "source_validation" in contract.DOCUMENT_ALIGNMENT_WORKFLOW_STAGES
    assert "verification" in contract.DOCUMENT_ALIGNMENT_WORKFLOW_STAGES
    assert "needs_review" in contract.DOCUMENT_ALIGNMENT_ITEM_STATUSES
    assert "approved" not in contract.DOCUMENT_ALIGNMENT_ITEM_STATUSES
    assert "published" not in contract.DOCUMENT_ALIGNMENT_ITEM_STATUSES

    assert app_module.DocumentAlignmentWorkflowRun.DEFAULT_STATUS == contract.ROOT_STATUS_QUEUED
    assert app_module.DocumentAlignmentWorkflowItem.DEFAULT_STATUS == contract.ITEM_STATUS_CANDIDATE


def test_root_model_fields_express_formal_contract(app_module):
    columns = {column.name for column in app_module.DocumentAlignmentWorkflowRun.__table__.columns}

    assert {
        "run_uid",
        "source_uid",
        "parse_uid",
        "source_version",
        "course",
        "chapter",
        "requested_by",
        "request_id",
        "idempotency_key",
        "idempotency_fingerprint",
        "workflow_version",
        "retrieval_version",
        "prompt_version",
        "provider_policy_version",
        "status",
        "stage",
        "total_items",
        "successful_items",
        "ready_for_review_items",
        "blocked_items",
        "failed_items",
        "warning_count",
        "error_code",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
        "updated_at",
    } <= columns
    assert "request_id" in columns
    assert "idempotency_key" in columns
    assert "idempotency_fingerprint" in columns
    assert "raw_exception" not in columns
    assert "raw_prompt" not in columns
    assert "raw_provider_output" not in columns
    assert "credential" not in columns


def test_item_model_fields_express_formal_contract(app_module):
    columns = {column.name for column in app_module.DocumentAlignmentWorkflowItem.__table__.columns}

    assert {
        "item_uid",
        "workflow_run_id",
        "item_key",
        "candidate_term",
        "normalized_term",
        "source_chunk_refs",
        "chinese_candidate_summary",
        "english_evidence_refs",
        "chinese_evidence_refs",
        "draft_card_uid",
        "verification_run_uid",
        "status",
        "stage",
        "risk_labels",
        "confidence_score",
        "confidence_summary",
        "recommendation",
        "warning_count",
        "error_code",
        "error_message",
        "retry_count",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    } <= columns
    assert "alignment_run_id" not in columns
    assert "terminology_card_id" not in columns
    assert "usage_record_id" not in columns
    assert "ai_call_log_id" not in columns
    assert "raw_evidence" not in columns
    assert "raw_prompt" not in columns
    assert "raw_provider_output" not in columns
    assert "credential" not in columns


def test_constraints_indexes_and_background_job_boundary(app_module):
    run_table = app_module.DocumentAlignmentWorkflowRun.__table__
    item_table = app_module.DocumentAlignmentWorkflowItem.__table__
    run_constraint_names = {constraint.name for constraint in run_table.constraints if constraint.name}
    item_constraint_names = {constraint.name for constraint in item_table.constraints if constraint.name}
    run_index_names = {index.name for index in run_table.indexes}
    item_index_names = {index.name for index in item_table.indexes}

    assert "uq_document_alignment_workflow_idempotency" in run_constraint_names
    assert "uq_document_alignment_workflow_item_key" in item_constraint_names
    assert "ix_document_alignment_workflow_source_status" in run_index_names
    assert "ix_document_alignment_workflow_requested_created" in run_index_names
    assert "ix_document_alignment_workflow_item_run_status" in item_index_names
    assert "ix_document_alignment_workflow_item_draft_card" in item_index_names
    assert "ix_document_alignment_workflow_item_verification" in item_index_names

    background_columns = {column.name for column in app_module.BackgroundJob.__table__.columns}
    assert "run_uid" not in background_columns
    assert "source_uid" not in background_columns
    assert "parse_uid" not in background_columns
    assert "idempotency_key" not in background_columns
    assert "stage" not in background_columns
    assert "successful_items" not in background_columns


def test_formal_workflow_docs_record_models_and_pilot_migration_limits():
    adr = (ROOT / "docs" / "adr" / "ADR-formal-document-alignment-workflow.md").read_text(encoding="utf-8")
    boundary = (ROOT / "docs" / "formal_document_alignment_workflow_boundary.md").read_text(encoding="utf-8")
    combined = adr + "\n" + boundary

    for term in [
            "ACCEPTED_FOR_SMALL_PILOT",
            "FORMAL_WORKFLOW_MODELS_ESTABLISHED",
            "WORKFLOW_ADMISSION_SERVICE_ESTABLISHED",
            "FORMAL_DOCUMENT_ALIGNMENT_PROCESSING_ORCHESTRATOR_ESTABLISHED",
            "FORMAL_DOCUMENT_ALIGNMENT_ROUTES_AND_OPENAPI_ESTABLISHED",
            "FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_ESTABLISHED",
        "FRONTEND_NOT_MIGRATED",
        "PILOT_CREATE_ALL_ONLY",
        "FORMAL_MIGRATION_REQUIRED_BEFORE_PRODUCTION",
        "DocumentAlignmentWorkflowRun",
        "DocumentAlignmentWorkflowItem",
        "BACKGROUND_JOB_AS_TRANSPORT_ONLY",
        "NO_LEGACY_AND_FORMAL_DUAL_WRITE",
    ]:
        assert term in combined
