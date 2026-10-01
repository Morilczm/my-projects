import inspect
import socket
from pathlib import Path

from services import (
    alignment_verification,
    alignment_verification_execution,
    audit_records,
    bilingual_evidence_workflow,
    chinese_term_candidates,
    concept_card_drafts,
    document_alignment_workflow_application,
    document_alignment_workflow_contract,
    evidence_retrieval,
    provider_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "backend" / "app.py"
ADR_PATH = ROOT / "docs" / "adr" / "ADR-formal-document-alignment-workflow.md"
BOUNDARY_PATH = ROOT / "docs" / "formal_document_alignment_workflow_boundary.md"


def _default(function, parameter):
    return inspect.signature(function).parameters[parameter].default


def _docs():
    return (
        ADR_PATH.read_text(encoding="utf-8"),
        BOUNDARY_PATH.read_text(encoding="utf-8"),
    )


def test_admission_models_job_payload_and_item_key_are_established(app_module):
    assert callable(document_alignment_workflow_application.start_document_alignment_workflow)
    assert hasattr(app_module, "DocumentAlignmentWorkflowRun")
    assert hasattr(app_module, "DocumentAlignmentWorkflowItem")
    assert document_alignment_workflow_contract.DOCUMENT_ALIGNMENT_ITEM_KEY_VERSION == "item-key-v1"

    job_builder = inspect.getsource(document_alignment_workflow_application._build_background_job)
    assert '"workflow_run_uid"' in job_builder
    assert '"workflow_version"' in job_builder
    for forbidden in (
        '"document_text"',
        '"chunks"',
        '"evidence"',
        '"prompt"',
        '"credential"',
        '"provider_url"',
    ):
        assert forbidden not in job_builder


def test_current_term_extraction_is_legacy_text_level_and_has_no_chunk_scope(app_module):
    signature = inspect.signature(app_module.extract_terms_from_text)
    assert tuple(signature.parameters) == ("text",)

    with app_module.app.app_context():
        candidates = app_module.extract_terms_from_text(
            "Fourier Transform converts a time-domain signal into a frequency-domain representation."
        )

    assert candidates
    assert {"english_term", "context", "confidence", "status"} <= set(candidates[0])
    assert "source_chunk_ids" not in candidates[0]
    assert "source_chunk_refs" not in candidates[0]
    assert "normalized_term" not in candidates[0]


def test_processing_collaborators_are_locatable_and_read_only_stages_do_not_commit():
    assert callable(evidence_retrieval.search_evidence)
    assert callable(bilingual_evidence_workflow.retrieve_bilingual_evidence)
    assert callable(chinese_term_candidates.generate_chinese_term_candidates)
    assert callable(concept_card_drafts.create_concept_card_draft_from_evidence)
    assert callable(provider_preflight.run_provider_preflight)
    assert callable(alignment_verification_execution.execute_alignment_verification)
    assert callable(alignment_verification.apply_verification_result_to_card)

    read_only_sources = "\n".join(
        inspect.getsource(module)
        for module in (
            evidence_retrieval,
            bilingual_evidence_workflow,
            chinese_term_candidates,
        )
    )
    assert "session.commit(" not in read_only_sources
    assert "session.rollback(" not in read_only_sources


def test_current_transaction_owners_are_explicit_and_verification_omits_preflight():
    assert _default(concept_card_drafts.create_concept_card_draft_from_evidence, "commit") is True
    assert _default(provider_preflight.run_provider_preflight, "commit") is True
    assert _default(alignment_verification.verify_alignment, "commit") is True
    assert _default(alignment_verification.apply_verification_result_to_card, "commit") is True
    assert _default(audit_records.create_audit_record, "commit") is True

    execution_source = inspect.getsource(alignment_verification_execution.execute_alignment_verification)
    assert "session.commit()" in execution_source
    assert "session.rollback()" in execution_source
    assert "evaluate_provider_request" in execution_source
    assert "run_provider_preflight" not in execution_source
    assert "commit=True" in execution_source


def test_background_job_formal_path_has_attempt_fenced_lease_contract(app_module):
    columns = {column.name for column in app_module.BackgroundJob.__table__.columns}
    assert {"locked_by", "locked_at", "attempt_count", "max_attempts"} <= columns
    assert {
        "job_uid",
        "execution_attempt",
        "lease_token",
        "lease_expires_at",
        "heartbeat_at",
    } <= columns

    claim_source = inspect.getsource(app_module.claim_next_background_job)
    assert ".first()" in claim_source
    assert "status.in_([\"queued\", \"retrying\"])" in claim_source
    assert "FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE" in claim_source
    assert "db.session.commit()" in claim_source

    from services import formal_background_job_execution

    formal_claim = inspect.getsource(formal_background_job_execution.claim_next_formal_background_job)
    assert "rowcount" in formal_claim
    assert "update(" in formal_claim


def test_formal_job_has_dedicated_worker_dispatch_and_formal_routes(app_module):
    app_source = APP_PATH.read_text(encoding="utf-8")
    job_type = document_alignment_workflow_contract.FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE

    assert job_type not in app_module.JOB_TYPES
    assert f'job.job_type == "{job_type}"' not in app_source
    assert "run_formal_worker_once" in app_source
    assert "process_document_alignment_workflow" in app_source

    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert "/api/document-alignment-runs" in rules
    assert "/api/document-alignment-runs/<run_uid>" in rules
    assert "/api/document-alignment-runs/<run_uid>/items" in rules
    assert not (ROOT / "backend" / "services" / "document_alignment_workflow_processing.py").exists()


def test_current_formal_boundaries_do_not_auto_approve_or_write_legacy_records():
    admission_source = inspect.getsource(document_alignment_workflow_application)
    draft_source = inspect.getsource(concept_card_drafts)
    verification_source = inspect.getsource(alignment_verification)

    for legacy_write in ("AlignmentRun(", "TerminologyCard(", "UsageRecord(", "AICallLog("):
        assert legacy_write not in admission_source
    assert "cannot create approved ConceptAlignmentCard" in draft_source
    assert 'output["can_auto_approve"] = False' in verification_source


def test_characterized_local_candidate_and_key_paths_do_not_use_network(monkeypatch, app_module):
    def forbid_network(*_args, **_kwargs):
        raise AssertionError("processing boundary characterization attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbid_network)

    with app_module.app.app_context():
        candidates = app_module.extract_terms_from_text(
            "Laplace Transform represents a signal in the complex-frequency domain."
        )

    assert candidates
    assert document_alignment_workflow_contract.build_document_alignment_item_key(
        normalized_term="laplace transform",
        source_chunk_ids=("chunk-2", "chunk-1"),
    ).startswith("item-key-v1:")


def test_frontend_uses_formal_alignment_while_legacy_contract_remains_documented():
    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    formal_module = (ROOT / "frontend" / "js" / "formal-workflow.js").read_text(encoding="utf-8")
    openapi = (ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8")

    assert "startFormalAlignmentForDocument" in frontend
    assert 'api("/api/alignment/run"' not in frontend
    assert "/api/document-alignment-runs" in formal_module
    assert "/api/alignment/run" not in formal_module
    assert "/api/alignment/run" in openapi
    assert "/api/document-alignment-runs" in openapi


def test_processing_boundary_docs_freeze_contracts_state_machines_and_transactions():
    adr, boundary = _docs()
    combined = adr + "\n" + boundary

    required_terms = (
        "PROCESSING_BOUNDARY_CHARACTERIZED",
        "FORMAL_DOCUMENT_ALIGNMENT_PROCESSING_ORCHESTRATOR_ESTABLISHED",
        "FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_ESTABLISHED",
        "FORMAL_DOCUMENT_ALIGNMENT_ROUTES_AND_OPENAPI_ESTABLISHED",
        "FORMAL_DOCUMENT_ALIGNMENT_API_END_TO_END_VERIFIED",
        "FRONTEND_NOT_MIGRATED",
        "ProcessDocumentAlignmentWorkflowCommand",
        "ProcessDocumentAlignmentWorkflowResult",
        "ItemBootstrapCollaborator",
        "EvidenceAndCandidateCollaborator",
        "DraftAndVerificationCollaborator",
        "WorkflowFinalizationCollaborator",
        "candidate_term",
        "normalized_term",
        "source_chunk_ids",
        "item-key-v1",
        "DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES",
        "DOCUMENT_ALIGNMENT_ITEM_LIMIT_EXCEEDED",
        "UNKNOWN transaction owner: 0",
        "NO_LEGACY_AND_FORMAL_DUAL_WRITE",
        "BACKGROUND_JOB_AS_TRANSPORT_ONLY",
        "WORKER_CLAIM_AND_LEASE_CONTRACT_REQUIRED_FIRST",
    )
    for term in required_terms:
        assert term in combined
    assert "FORMAL_API_E2E_NOT_COMPLETED" not in combined

    for transition in (
        "queued -> validating",
        "validating -> processing",
        "processing -> ready_for_review",
        "processing -> completed_with_warnings",
        "candidate -> evidence_ready",
        "evidence_ready -> draft_created",
        "draft_created -> verification_completed",
        "verification_completed -> needs_review",
    ):
        assert transition in combined

    assert "TBD" not in combined
    assert "TODO" not in combined


def test_processing_boundary_docs_freeze_safe_errors_retry_usage_and_query_contract():
    _, boundary = _docs()

    error_codes = (
        "DOCUMENT_ALIGNMENT_RUN_NOT_FOUND",
        "DOCUMENT_ALIGNMENT_JOB_NOT_FOUND",
        "DOCUMENT_ALIGNMENT_JOB_MISMATCH",
        "DOCUMENT_ALIGNMENT_WORKFLOW_VERSION_MISMATCH",
        "DOCUMENT_ALIGNMENT_INVALID_RUN_STATE",
        "DOCUMENT_ALIGNMENT_WORKER_CLAIM_CONFLICT",
        "DOCUMENT_ALIGNMENT_SOURCE_CHANGED",
        "DOCUMENT_ALIGNMENT_PARSE_BLOCKED",
        "DOCUMENT_ALIGNMENT_NO_TERM_CANDIDATES",
        "DOCUMENT_ALIGNMENT_ITEM_LIMIT_EXCEEDED",
        "DOCUMENT_ALIGNMENT_PERSISTENCE_FAILED",
        "DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED",
        "DOCUMENT_ALIGNMENT_CHUNK_NOT_AVAILABLE",
        "DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT",
        "DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE",
        "DOCUMENT_ALIGNMENT_DRAFT_CONFLICT",
        "DOCUMENT_ALIGNMENT_APPROVED_CARD_PROTECTED",
        "DOCUMENT_ALIGNMENT_PROVIDER_POLICY_BLOCKED",
        "DOCUMENT_ALIGNMENT_PROVIDER_PREFLIGHT_BLOCKED",
        "DOCUMENT_ALIGNMENT_VERIFICATION_FAILED",
        "DOCUMENT_ALIGNMENT_VERIFICATION_PARSE_FAILED",
        "DOCUMENT_ALIGNMENT_ATTACH_BLOCKED",
        "DOCUMENT_ALIGNMENT_ITEM_PERSISTENCE_FAILED",
    )
    for code in error_codes:
        assert code in boundary

    for term in (
        "single worker",
        "atomic claim",
        "stale-running",
        "needs_review item",
        "blocked non-retryable item",
        "verification_completed item",
        "actual provider execution",
        "document_alignment_started",
        "document_alignment_items_created",
        "document_alignment_ready_for_review",
        "document_alignment_completed_with_warnings",
        "document_alignment_blocked",
        "document_alignment_failed",
        "pagination",
        "course permission",
        "BackgroundJob is not business status truth",
    ):
        assert term in boundary


def test_processing_boundary_has_exactly_one_primary_conclusion():
    adr, boundary = _docs()
    combined = adr + "\n" + boundary
    conclusions = (
        "GO_FORMAL_PROCESSING_ORCHESTRATOR_SERVICE",
        "SPLIT_VERIFICATION_TRANSACTION_ADAPTER_FIRST",
        "WORKER_CLAIM_AND_LEASE_CONTRACT_REQUIRED_FIRST",
        "SPLIT_TERM_EXTRACTION_AND_ITEM_PERSISTENCE_FIRST",
        "FORMAL_PROCESSING_BOUNDARY_UNCLEAR",
    )
    declared = [value for value in conclusions if f"Primary conclusion: `{value}`" in combined]

    assert declared == ["WORKER_CLAIM_AND_LEASE_CONTRACT_REQUIRED_FIRST"]
