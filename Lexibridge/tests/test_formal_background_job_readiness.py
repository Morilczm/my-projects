import inspect

from scripts import pilot_readiness_check


EXPECTED_CONDITIONS = {
    "FORMAL_WORKFLOW_PROVIDER_SELECTION_POLICY_PRESENT",
    "FORMAL_ADMISSION_PROVIDER_SELECTION_FROZEN",
    "FORMAL_DEFAULT_DETERMINISTIC_PROVIDER_CONFIGURED",
    "FORMAL_DEFAULT_PROVIDER_POLICY_ALLOWED",
    "FORMAL_DEFAULT_PROVIDER_PREFLIGHT_PASSED",
    "FORMAL_ITEM_PREPARATION_NO_SILENT_PROVIDER_FALLBACK",
    "FORMAL_LEGACY_NULL_SELECTION_FAILS_CLOSED",
    "FORMAL_BACKGROUND_JOB_LEASE_FOUNDATION_PRESENT",
    "FORMAL_CHUNK_SCOPED_TERM_CANDIDATES_PRESENT",
    "FORMAL_WORKFLOW_ITEM_BOOTSTRAP_PRESENT",
    "FORMAL_BOOTSTRAP_LEASE_FENCING_PRESENT",
    "FORMAL_ITEM_VERIFICATION_ADAPTER_PRESENT",
    "FORMAL_ITEM_EXECUTION_MAPPING_USED",
    "FORMAL_PROVIDER_PREFLIGHT_ENFORCED",
    "FORMAL_VERIFICATION_EXECUTION_REUSE_PRESENT",
    "FORMAL_USAGE_EXECUTION_IDENTITY_ENFORCED",
    "FORMAL_AUDIT_EVENT_IDENTITY_ENFORCED",
    "FORMAL_APPROVED_CARD_PROTECTION_PRESENT",
    "FORMAL_EVIDENCE_PERSISTENCE_MINIMIZED",
    "POSTGRESQL_ITEM_ADAPTER_NOT_VERIFIED",
    "POSTGRESQL_BOOTSTRAP_TRANSACTION_NOT_VERIFIED",
    "FORMAL_DOCUMENT_PROCESSING_ORCHESTRATOR_PRESENT",
    "FORMAL_ITEM_PREPARATION_COMPOSITION_PRESENT",
    "FORMAL_ROOT_PROGRESS_RECALCULATION_PRESENT",
    "FORMAL_ROOT_FINALIZATION_PRESENT",
    "FORMAL_ROOT_AUDIT_IDEMPOTENCY_PRESENT",
    "FORMAL_PROCESSING_PARTIAL_FAILURE_PRESENT",
    "FORMAL_PROCESSING_RESUME_PRESENT",
    "FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_PRESENT",
    "FORMAL_DOCUMENT_ALIGNMENT_JOB_DISPATCH_PRESENT",
    "FORMAL_WORKER_RESULT_MAPPING_PRESENT",
    "FORMAL_WORKER_RETRY_MAPPING_PRESENT",
    "FORMAL_WORKER_STALE_RECOVERY_PRESENT",
    "FORMAL_ROOT_JOB_TERMINAL_CONSISTENCY_PRESENT",
    "FORMAL_JOB_NO_LEGACY_DISPATCH_PRESENT",
    "FORMAL_WORKFLOW_RETRY_BUDGET_POLICY_PRESENT",
    "FORMAL_ADMISSION_MAX_ATTEMPTS_FROZEN",
    "FORMAL_HTTP_RETRYABLE_REQUEUE_VERIFIED",
    "FORMAL_RETRY_NEXT_CLAIM_RECOVERY_VERIFIED",
    "FORMAL_RETRY_EXHAUSTION_ORDER_VERIFIED",
    "FORMAL_STALE_RECLAIM_DOES_NOT_CONSUM_RETRY_BUDGET",
    "FORMAL_WORKFLOW_RUN_QUERY_SERVICE_PRESENT",
    "FORMAL_WORKFLOW_ITEM_QUERY_SERVICE_PRESENT",
    "FORMAL_WORKFLOW_QUERY_PERMISSION_ENFORCED",
    "FORMAL_WORKFLOW_QUERY_STUDENT_DENIED",
    "FORMAL_WORKFLOW_QUERY_BACKGROUND_JOB_HIDDEN",
    "FORMAL_WORKFLOW_QUERY_SAFE_ERROR_PRESENT",
    "FORMAL_WORKFLOW_QUERY_PAGINATION_PRESENT",
    "FORMAL_WORKFLOW_QUERY_NO_WRITE_PRESENT",
    "FORMAL_WORKFLOW_START_ROUTE_PRESENT",
    "FORMAL_WORKFLOW_RUN_ROUTE_PRESENT",
    "FORMAL_WORKFLOW_ITEMS_ROUTE_PRESENT",
    "FORMAL_WORKFLOW_IDEMPOTENCY_HEADER_ENFORCED",
    "FORMAL_WORKFLOW_HTTP_PERMISSION_ENFORCED",
    "FORMAL_WORKFLOW_HTTP_STUDENT_DENIED",
    "FORMAL_WORKFLOW_HTTP_BACKGROUND_JOB_HIDDEN",
    "FORMAL_WORKFLOW_OPENAPI_PRESENT",
    "FORMAL_WORKFLOW_OPENAPI_RUNTIME_PARITY_PRESENT",
    "FORMAL_PRODUCTION_DEFAULT_CONTRACT_VERIFIED",
    "FORMAL_API_E2E_PRESENT",
    "FORMAL_API_HTTP_START_VERIFIED",
    "FORMAL_API_WORKER_EXECUTION_VERIFIED",
    "FORMAL_API_POLLING_VERIFIED",
    "FORMAL_API_ITEM_QUERY_VERIFIED",
    "FORMAL_API_SOURCE_SCOPED_IDEMPOTENCY_VERIFIED",
    "FORMAL_API_CONCURRENT_REPLAY_VERIFIED",
    "FORMAL_API_PARTIAL_FAILURE_VERIFIED",
    "FORMAL_API_ALL_BLOCKED_VERIFIED",
    "FORMAL_API_RETRYABLE_RECOVERY_VERIFIED",
    "FORMAL_API_STALE_RECOVERY_VERIFIED",
    "FORMAL_API_TERMINAL_RECOVERY_VERIFIED",
    "FORMAL_API_STUDENT_DENIAL_VERIFIED",
    "FORMAL_FRONTEND_CUTOVER_PRESENT",
    "FORMAL_FRONTEND_START_USES_FORMAL_API",
    "FORMAL_FRONTEND_RUN_POLLING_PRESENT",
    "FORMAL_FRONTEND_ITEMS_QUERY_PRESENT",
    "FORMAL_FRONTEND_ITEMS_PAGINATION_PRESENT",
    "FORMAL_FRONTEND_RELOAD_RESUME_PRESENT",
    "FORMAL_FRONTEND_DUPLICATE_START_PREVENTED",
    "FORMAL_FRONTEND_TEACHER_GATED",
    "FORMAL_FRONTEND_LEGACY_ALIGNMENT_NOT_CALLED",
    "FORMAL_FRONTEND_NO_LEGACY_FALLBACK",
    "LEGACY_ALIGNMENT_ROUTE_STILL_PRESENT",
    "FRONTEND_VISUAL_REDESIGN_NOT_COMPLETED",
    "HISTORICAL_RUN_LIST_NOT_IMPLEMENTED",
    "FULL_REVIEW_WORKBENCH_NOT_IMPLEMENTED",
    "POSTGRESQL_UI_FLOW_NOT_VERIFIED",
    "POSTGRESQL_API_E2E_NOT_VERIFIED",
    "POSTGRESQL_HTTP_FLOW_NOT_VERIFIED",
    "POSTGRESQL_QUERY_NOT_VERIFIED",
    "POSTGRESQL_PROCESSING_NOT_VERIFIED",
    "POSTGRESQL_LEASE_SEMANTICS_NOT_VERIFIED",
    "POSTGRESQL_WORKER_NOT_VERIFIED",
    "PRODUCTION_WORKER_RUNTIME_NOT_ESTABLISHED",
    "FORMAL_ITEM_EXECUTION_IDENTITY_SCHEMA_PRESENT",
    "FORMAL_VERIFICATION_EXECUTION_KEY_UNIQUENESS_PRESENT",
    "FORMAL_PREFLIGHT_EXECUTION_KEY_UNIQUENESS_PRESENT",
    "FORMAL_USAGE_EXECUTION_KEY_UNIQUENESS_PRESENT",
    "FORMAL_AUDIT_EVENT_IDENTITY_UNIQUENESS_PRESENT",
    "POSTGRESQL_IDEMPOTENCY_CONSTRAINTS_NOT_VERIFIED",
    "FORMAL_MIGRATION_FRAMEWORK_NOT_ESTABLISHED",
}


def test_small_pilot_readiness_exposes_formal_job_ownership_conditions():
    conditions = set(pilot_readiness_check.default_conditions("small-pilot"))
    assert EXPECTED_CONDITIONS <= conditions
    assert "FORMAL_API_BROWSER_SESSION_VERIFIED" not in conditions
    assert "FORMAL_FRONTEND_UI_E2E_VERIFIED" not in conditions
    assert "FORMAL_FRONTEND_RESUME_E2E_VERIFIED" not in conditions
    assert "FRONTEND_NOT_MIGRATED" not in conditions


def test_readiness_runs_explicit_formal_job_ownership_gate():
    source = inspect.getsource(pilot_readiness_check.main)
    assert "formal background job execution ownership" in source
    assert "tests/test_formal_background_job_execution.py" in source
    assert "tests/test_formal_background_job_concurrency.py" in source
    assert "formal document alignment item bootstrap" in source
    assert "tests/test_document_alignment_term_candidates.py" in source
    assert "tests/test_document_alignment_item_bootstrap.py" in source
    assert "tests/test_document_alignment_item_bootstrap_integration.py" in source
    assert "formal item execution idempotency schema" in source
    assert "tests/test_formal_item_verification_execution_models.py" in source
    assert "tests/test_formal_item_idempotency_constraints.py" in source
    assert "tests/test_formal_item_execution_schema_upgrade.py" in source
    assert "formal item verification transaction adapter" in source
    assert "tests/test_document_alignment_item_verification_adapter.py" in source
    assert "tests/test_document_alignment_item_verification_adapter_integration.py" in source
    assert "tests/test_document_alignment_item_verification_idempotency.py" in source
    assert "tests/test_document_alignment_item_verification_security.py" in source
    assert "tests/test_document_alignment_item_verification_fault_recovery.py" in source
    assert "formal document alignment processing orchestrator" in source
    assert "tests/test_document_alignment_processing_orchestrator.py" in source
    assert "tests/test_document_alignment_processing_orchestrator_integration.py" in source
    assert "tests/test_document_alignment_processing_partial_failure.py" in source
    assert "tests/test_document_alignment_processing_resume.py" in source
    assert "tests/test_document_alignment_processing_concurrency.py" in source
    assert "tests/test_document_alignment_processing_security.py" in source
    assert "tests/test_document_alignment_processing_fault_recovery.py" in source
    assert "formal document alignment worker handler" in source
    assert "tests/test_document_alignment_worker_handler.py" in source
    assert "tests/test_document_alignment_worker_result_mapping.py" in source
    assert "tests/test_document_alignment_worker_integration.py" in source
    assert "tests/test_document_alignment_worker_retry_recovery.py" in source
    assert "tests/test_document_alignment_worker_concurrency.py" in source
    assert "tests/test_document_alignment_worker_legacy_compatibility.py" in source
    assert "tests/test_document_alignment_worker_security.py" in source
    assert "formal document alignment query services" in source
    assert "tests/test_document_alignment_workflow_query_permissions.py" in source
    assert "tests/test_document_alignment_workflow_run_query.py" in source
    assert "tests/test_document_alignment_workflow_item_query.py" in source
    assert "tests/test_document_alignment_workflow_query_integration.py" in source
    assert "tests/test_document_alignment_workflow_query_performance.py" in source
    assert "tests/test_document_alignment_workflow_query_security.py" in source
    assert "formal document alignment routes and OpenAPI" in source
    assert "tests/test_document_alignment_workflow_routes.py" in source
    assert "tests/test_document_alignment_workflow_start_route.py" in source
    assert "tests/test_document_alignment_workflow_get_route.py" in source
    assert "tests/test_document_alignment_workflow_items_route.py" in source
    assert "tests/test_document_alignment_workflow_route_error_mapping.py" in source
    assert "tests/test_document_alignment_workflow_openapi.py" in source
    assert "tests/test_document_alignment_workflow_route_security.py" in source
    assert "tests/test_document_alignment_workflow_route_integration.py" in source
    assert "formal document alignment provider selection" in source
    assert "tests/test_formal_document_alignment_provider_selection.py" in source
    assert "tests/test_document_alignment_admission_provider_selection.py" in source
    assert "tests/test_document_alignment_provider_preflight_contract.py" in source
    assert "tests/test_document_alignment_http_default_provider_flow.py" in source
    assert "formal document alignment retry budget" in source
    assert "tests/test_formal_document_alignment_retry_budget_contract.py" in source
    assert "tests/test_document_alignment_admission_retry_budget.py" in source
    assert "tests/test_document_alignment_http_retry_recovery_contract.py" in source
    assert "tests/test_document_alignment_retry_exhaustion_contract.py" in source
    assert "tests/test_document_alignment_retry_crash_semantics.py" in source
    assert "formal document alignment API end to end" in source
    assert "tests/test_document_alignment_production_contract_convergence.py" in source
    assert "tests/test_document_alignment_formal_api_e2e.py" in source
    assert "tests/test_document_alignment_formal_api_idempotency.py" in source
    assert "tests/test_document_alignment_formal_api_recovery.py" in source
    assert "formal document alignment browser API e2e" in source
    assert "scripts/run_formal_document_alignment_browser_e2e.py" in source
    assert 'conditions.append("FORMAL_API_BROWSER_SESSION_VERIFIED")' in source
    assert "formal workflow frontend cutover" in source
    assert "scripts/run_formal_workflow_frontend_e2e.py" in source
    assert "formal workflow frontend resume" in source
    assert "scripts/run_formal_workflow_frontend_resume_e2e.py" in source
    assert 'conditions.append("FORMAL_FRONTEND_UI_E2E_VERIFIED")' in source
    assert 'conditions.append("FORMAL_FRONTEND_RESUME_E2E_VERIFIED")' in source


def test_readiness_no_longer_reports_query_service_as_missing():
    for profile in ("local-demo", "small-pilot"):
        assert "FORMAL_QUERY_SERVICE_NOT_IMPLEMENTED" not in pilot_readiness_check.default_conditions(profile)
        assert "FORMAL_ROUTES_NOT_IMPLEMENTED" not in pilot_readiness_check.default_conditions(profile)
        assert "FORMAL_API_E2E_NOT_COMPLETED" not in pilot_readiness_check.default_conditions(profile)
