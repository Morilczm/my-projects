from pathlib import Path
import uuid

from services import (
    alignment_verification_execution,
    bilingual_evidence_workflow,
    chinese_term_candidates,
    concept_card_drafts,
    evidence_retrieval,
)
from services.legacy_alignment_provider_classification import (
    LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED,
    classify_legacy_alignment_provider,
)


ROOT = Path(__file__).resolve().parents[1]


def test_governed_knowledge_source_parse_and_chunk_chain_exists(app_module):
    with app_module.app.app_context():
        suffix = uuid.uuid4().hex[:10]
        parse_uid = f"formal-workflow-boundary-parse-{suffix}"
        source_uid = f"formal-workflow-boundary-source-{suffix}"
        chunk_uid = f"formal-workflow-boundary-chunk-{suffix}"

        parse = app_module.DocumentParseRecord(
            parse_uid=parse_uid,
            source_filename="formal-workflow-boundary.txt",
            parse_status="success",
            quality_status="native_text_ok",
            block_count=1,
            extracted_text_chars=42,
        )
        app_module.db.session.add(parse)
        app_module.db.session.flush()
        source = app_module.KnowledgeSource(
            source_uid=source_uid,
            title="Formal workflow governed source",
            name="Formal workflow governed source",
            course="Workflow Course",
            chapter="Workflow Chapter",
            language="en",
            visibility="course",
            trust_level="teacher_verified",
            status="active",
            quality_status="native_text_ok",
            parse_uid=parse.parse_uid,
        )
        app_module.db.session.add(source)
        app_module.db.session.flush()
        chunk = app_module.KnowledgeChunk(
            chunk_uid=chunk_uid,
            source_uid=source.source_uid,
            knowledge_source_id=source.id,
            document_id=0,
            parse_uid=parse.parse_uid,
            course=source.course,
            chapter=source.chapter,
            language="en",
            content="Laplace Transform is governed chunk evidence.",
            status="active",
            quality_status="native_text_ok",
            trust_level="teacher_verified",
        )
        app_module.db.session.add(chunk)
        app_module.db.session.commit()

        persisted = app_module.KnowledgeSource.query.filter_by(source_uid=source.source_uid).one()
        chunks = app_module.KnowledgeChunk.query.filter_by(knowledge_source_id=persisted.id).all()

        assert persisted.parse_uid == parse.parse_uid
        assert persisted.status == "active"
        assert chunks and chunks[0].chunk_uid == chunk.chunk_uid
        assert chunks[0].parse_uid == parse.parse_uid


def test_formal_components_are_importable_and_currently_separate_from_legacy_route():
    assert callable(evidence_retrieval.search_evidence)
    assert callable(bilingual_evidence_workflow.retrieve_bilingual_evidence)
    assert callable(chinese_term_candidates.generate_chinese_term_candidates)
    assert callable(concept_card_drafts.create_concept_card_draft_from_evidence)
    assert callable(alignment_verification_execution.execute_alignment_verification)

    route_source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    verification_source = (ROOT / "backend" / "routes" / "alignment_verification.py").read_text(encoding="utf-8")

    assert '@app.route("/api/alignment/run", methods=["POST"])' in route_source
    assert "execute_alignment_verification" in verification_source
    assert '"/api/alignment/run"' not in verification_source


def test_background_job_is_transport_not_formal_workflow_root(app_module):
    missing_business_fields = {
        "run_uid",
        "source_uid",
        "parse_uid",
        "workflow_version",
        "idempotency_key",
        "request_id",
        "stage",
        "total_candidates",
        "successful_items",
        "blocked_items",
        "failed_items",
        "warning_count",
    }

    assert hasattr(app_module, "DocumentAlignmentWorkflowRun")
    assert hasattr(app_module, "DocumentAlignmentWorkflowItem")
    assert all(not hasattr(app_module.BackgroundJob, field) for field in missing_business_fields)


def test_current_formal_services_do_not_write_legacy_alignment_tables():
    service_paths = [
        ROOT / "backend" / "services" / "alignment_verification_execution.py",
        ROOT / "backend" / "services" / "alignment_verification.py",
        ROOT / "backend" / "services" / "concept_card_drafts.py",
        ROOT / "backend" / "services" / "bilingual_evidence_workflow.py",
        ROOT / "backend" / "services" / "evidence_retrieval.py",
        ROOT / "backend" / "services" / "chinese_term_candidates.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in service_paths)

    assert "AlignmentRun(" not in combined
    assert "AICallLog(" not in combined
    assert "UsageRecord(" not in combined
    assert "TerminologyCard(" not in combined


def test_no_auto_approve_and_student_approved_only_boundaries_remain_visible():
    draft_source = (ROOT / "backend" / "services" / "concept_card_drafts.py").read_text(encoding="utf-8")
    verification_source = (ROOT / "backend" / "services" / "alignment_verification_execution.py").read_text(encoding="utf-8")
    student_route_source = (ROOT / "backend" / "routes" / "student_concept_cards.py").read_text(encoding="utf-8")
    student_service_source = (ROOT / "backend" / "services" / "student_concept_cards.py").read_text(encoding="utf-8")

    assert "cannot create approved ConceptAlignmentCard" in draft_source
    assert "needs_review" in draft_source
    assert '"can_auto_approve": bool(output.get("can_auto_approve"))' in verification_source
    assert "get_publishable_approved_card" in student_route_source
    assert "get_approved_card" in student_service_source
    assert 'APPROVED_STATUS = "approved"' in student_service_source
    assert "card_model.status == APPROVED_STATUS" in student_service_source


def test_frontend_uses_formal_routes_while_legacy_route_remains_registered(app_module):
    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    formal_module = (ROOT / "frontend" / "js" / "formal-workflow.js").read_text(encoding="utf-8")
    openapi = (ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8")

    assert "startFormalAlignmentForDocument" in frontend
    assert 'api("/api/alignment/run"' not in frontend
    assert "/api/document-alignment-runs" in formal_module
    assert "/api/alignment/run" not in formal_module
    assert "/api/document-alignment-runs" in openapi

    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert "/api/alignment/run" in rules
    assert "/api/document-alignment-runs" in rules
    assert "/api/document-alignment-runs/<run_uid>" in rules
    assert "/api/document-alignment-runs/<run_uid>/items" in rules


def test_legacy_external_execution_remains_disabled_without_network_dependency():
    classification = classify_legacy_alignment_provider(
        provider_value="deepseek",
        provider_mode_value="live",
    )
    custom_classification = classify_legacy_alignment_provider(
        provider_value="deepseek",
        provider_mode_value="live",
        custom_endpoint_present=True,
    )

    assert classification.external_execution_blocked is True
    assert classification.reason_code == "LEGACY_ALIGNMENT_EXTERNAL_PROVIDER_DISABLED"
    assert classification.blocked_error_code == LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED
    assert custom_classification.external_execution_blocked is True
    assert custom_classification.reason_code == "LEGACY_ALIGNMENT_CUSTOM_ENDPOINT_BLOCKED"
    assert custom_classification.blocked_error_code == LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED


def test_formal_workflow_design_docs_define_contract_and_unique_conclusion():
    adr = (ROOT / "docs" / "adr" / "ADR-formal-document-alignment-workflow.md").read_text(encoding="utf-8")
    boundary = (ROOT / "docs" / "formal_document_alignment_workflow_boundary.md").read_text(encoding="utf-8")
    combined = adr + "\n" + boundary

    required_terms = [
        "PROPOSED_FOR_SMALL_PILOT",
        "FORMAL_DOCUMENT_ALIGNMENT_ORCHESTRATION",
        "GOVERNED_KNOWLEDGE_SOURCE",
        "ASYNC_JOB_ORCHESTRATION",
        "DocumentAlignmentWorkflowRun",
        "DocumentAlignmentWorkflowItem",
        "WORKFLOW_ADMISSION_SERVICE_ESTABLISHED",
        "start_document_alignment_workflow",
        "DocumentAlignmentWorkflowApplicationDependencies",
        "item-key-v1",
        "formal_document_alignment_workflow_v1",
        "document_alignment_requested",
        "NO_LEGACY_AND_FORMAL_DUAL_WRITE",
        "Idempotency-Key",
        "POST /api/document-alignment-runs",
        "GET /api/document-alignment-runs/{run_uid}",
        "GET /api/document-alignment-runs/{run_uid}/items",
        "FORMAL_WORKFLOW_MODELS_REQUIRED_FIRST",
    ]
    for term in required_terms:
        assert term in combined
    assert "TBD" not in combined
    assert "TODO" not in combined
