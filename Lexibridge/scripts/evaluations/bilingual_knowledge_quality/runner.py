"""Explicit Task 11E evaluation runner.

This command is evaluation-only. It imports the backend app only after a
temporary DATABASE_URL and UPLOAD_FOLDER are set, and it never uses
backend/lexibridge.db.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scripts.evaluations.bilingual_knowledge_quality import dataset, metrics, report_builder


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
ACCIDENT_DB = BACKEND / "lexibridge.db"
ACCIDENT_DB_FROZEN_SHA256 = "9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa"
DEFAULT_JSON = ROOT / "docs/evaluations/artifacts/11E-bilingual-knowledge-quality-baseline.json"
DEFAULT_MARKDOWN = ROOT / "docs/evaluations/11E-bilingual-knowledge-quality-baseline.md"
DEFAULT_REVIEW_PACKET = ROOT / "docs/evaluations/artifacts/11E-bilingual-quality-review-packet.jsonl"


@dataclass(frozen=True)
class FormalProviderReadiness:
    concept_id: str
    provider_ready: bool
    preparation_status: str
    rejection_code: str = ""
    rejection_stage: str = ""
    candidate_count: int = 0
    english_evidence_count: int = 0
    chinese_evidence_count: int = 0
    prepared_input: Any = None


@dataclass(frozen=True)
class FormalProviderPreflightSelection:
    concept_id: str
    readiness: FormalProviderReadiness
    selection_reason: str = "first_provider_ready_in_frozen_order"


class FormalProviderReadinessError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class FrozenBenchmarkIdentity:
    """Scoring-envelope identity; binding_term never becomes system input."""

    concept_id: str
    binding_term: str = ""


@dataclass(frozen=True)
class ProductionCandidateBindingInput:
    """Candidate emitted by the production extractor."""

    candidate_id: str
    candidate_term: str
    system_payload: Any


@dataclass(frozen=True)
class FrozenEvaluationBootstrapRow:
    benchmark_concept_id: str
    binding_status: str
    system_candidate_id: str = ""
    system_candidate_term: str = ""
    provider_ready: bool = False
    provider_called: bool = False
    execution_status: str = "upstream_not_ready"
    preparation_status: str = ""
    primary_attribution: str = ""
    included_in_denominator: bool = True
    rejection_code: str = ""
    candidate_count: int = 0
    english_evidence_count: int = 0
    chinese_evidence_count: int = 0
    prepared_input: Any = None


def _evaluation_binding_key(value: Any) -> str:
    """Mirror the R4 exact binding without aliases, stemming, or gold repair."""

    return str(value or "").strip().casefold()


def build_frozen_evaluation_bootstrap(
    benchmark_items,
    production_candidates,
    *,
    prepare_candidate,
) -> tuple[FrozenEvaluationBootstrapRow, ...]:
    """Keep the benchmark denominator while executing only system candidates."""

    candidates_by_key: dict[str, list[ProductionCandidateBindingInput]] = {}
    for candidate in tuple(production_candidates):
        key = _evaluation_binding_key(candidate.candidate_term)
        if key:
            candidates_by_key.setdefault(key, []).append(candidate)

    rows = []
    for benchmark in tuple(benchmark_items):
        matches = candidates_by_key.get(
            _evaluation_binding_key(benchmark.binding_term), []
        )
        if len(matches) != 1:
            rows.append(FrozenEvaluationBootstrapRow(
                benchmark_concept_id=str(benchmark.concept_id),
                binding_status="missing" if not matches else "ambiguous",
                execution_status="upstream_not_ready",
                primary_attribution="CANDIDATE_EXTRACTION_DEFECT",
                rejection_code=(
                    "PRODUCTION_CANDIDATE_MISSING"
                    if not matches
                    else "PRODUCTION_CANDIDATE_AMBIGUOUS"
                ),
            ))
            continue

        candidate = matches[0]
        prepared = prepare_candidate(candidate)
        ready = str(getattr(prepared, "outcome", "")) == "prepared"
        rows.append(FrozenEvaluationBootstrapRow(
            benchmark_concept_id=str(benchmark.concept_id),
            binding_status="matched",
            system_candidate_id=str(candidate.candidate_id),
            system_candidate_term=str(candidate.candidate_term),
            provider_ready=ready,
            execution_status="provider_ready" if ready else "upstream_not_ready",
            preparation_status=str(getattr(prepared, "outcome", "") or ""),
            primary_attribution="" if ready else "ENGLISH_RETRIEVAL_DEFECT",
            rejection_code=str(getattr(prepared, "error_code", "") or ""),
            candidate_count=int(getattr(prepared, "candidate_count", 0) or 0),
            english_evidence_count=len(tuple(
                getattr(prepared, "english_evidence_refs", ()) or ()
            )),
            chinese_evidence_count=len(tuple(
                getattr(prepared, "chinese_evidence_refs", ()) or ()
            )),
            prepared_input=getattr(prepared, "prepared_input", None),
        ))
    return tuple(rows)


def select_frozen_evaluation_preflight(
    bootstrap_rows,
) -> FormalProviderPreflightSelection:
    """Select the first system-ready row in the preserved frozen order."""

    for row in tuple(bootstrap_rows):
        if row.provider_ready:
            readiness = FormalProviderReadiness(
                concept_id=row.benchmark_concept_id,
                provider_ready=True,
                preparation_status=row.preparation_status,
                candidate_count=row.candidate_count,
                english_evidence_count=row.english_evidence_count,
                chinese_evidence_count=row.chinese_evidence_count,
                prepared_input=row.prepared_input,
            )
            return FormalProviderPreflightSelection(
                row.benchmark_concept_id, readiness
            )
    raise FormalProviderReadinessError(
        "FORMAL_PROVIDER_PREFLIGHT_NO_READY_ITEM",
        "No system-derived frozen evaluation item satisfies Formal preparation.",
    )


def continue_frozen_evaluation(
    bootstrap_rows,
    *,
    preflight_result,
    execute_ready_item,
) -> list[dict[str, Any]]:
    """Freeze one result per benchmark row and continue past item failures."""

    frozen_preflight = dict(preflight_result or {})
    results = []
    for row in tuple(bootstrap_rows):
        concept_id = row.benchmark_concept_id
        if not row.provider_ready:
            results.append({
                "benchmark_concept_id": concept_id,
                "concept_id": concept_id,
                "binding_status": row.binding_status,
                "system_candidate_id": row.system_candidate_id,
                "system_candidate_term": row.system_candidate_term,
                "provider_ready": False,
                "provider_called": False,
                "status": "upstream_not_ready",
                "primary_attribution": row.primary_attribution,
                "included_in_denominator": True,
                "error_code": row.rejection_code,
            })
            continue
        if frozen_preflight.get("concept_id") == concept_id:
            result = {**frozen_preflight, "reused_preflight": True}
        else:
            result = dict(execute_ready_item(row))
            result.setdefault("reused_preflight", False)
        result.setdefault("benchmark_concept_id", concept_id)
        result.setdefault("concept_id", concept_id)
        result.setdefault("binding_status", row.binding_status)
        result.setdefault("system_candidate_id", row.system_candidate_id)
        result.setdefault("system_candidate_term", row.system_candidate_term)
        result.setdefault("provider_ready", True)
        result.setdefault("provider_called", True)
        result.setdefault("included_in_denominator", True)
        results.append(result)
        if result.get("status") == "provider_failure" and result.get("systemic"):
            break
    return results


def scan_formal_provider_readiness(
    frozen_concept_order,
    *,
    prepare_item,
) -> tuple[FormalProviderReadiness, ...]:
    """Call the existing Formal preparation boundary without verification."""

    rows = []
    for concept_id in tuple(frozen_concept_order):
        result = prepare_item(concept_id)
        ready = str(getattr(result, "outcome", "")) == "prepared"
        rows.append(FormalProviderReadiness(
            concept_id=str(concept_id),
            provider_ready=ready,
            preparation_status=str(getattr(result, "outcome", "") or ""),
            rejection_code=str(getattr(result, "error_code", "") or ""),
            rejection_stage="" if ready else "formal_item_preparation",
            candidate_count=int(getattr(result, "candidate_count", 0) or 0),
            english_evidence_count=len(tuple(getattr(result, "english_evidence_refs", ()) or ())),
            chinese_evidence_count=len(tuple(getattr(result, "chinese_evidence_refs", ()) or ())),
            prepared_input=getattr(result, "prepared_input", None),
        ))
    return tuple(rows)


def select_formal_provider_preflight(
    readiness_results,
    frozen_concept_order,
) -> FormalProviderPreflightSelection:
    """Select deterministically without accepting gold or quality scores."""

    by_id = {row.concept_id: row for row in tuple(readiness_results)}
    for concept_id in tuple(frozen_concept_order):
        row = by_id.get(str(concept_id))
        if row is not None and row.provider_ready:
            return FormalProviderPreflightSelection(str(concept_id), row)
    raise FormalProviderReadinessError(
        "FORMAL_PROVIDER_PREFLIGHT_NO_READY_ITEM",
        "No frozen concept satisfies Formal provider preparation.",
    )


def continue_real_provider_evaluation(
    frozen_concept_order,
    readiness_results,
    *,
    preflight_result,
    execute_ready_item,
    upstream_attribution,
) -> list[dict[str, Any]]:
    """Continue past item-level upstream failures; stop on systemic failures."""

    by_id = {row.concept_id: row for row in tuple(readiness_results)}
    frozen_preflight = dict(preflight_result or {})
    results: list[dict[str, Any]] = []
    for concept_id in tuple(frozen_concept_order):
        concept_id = str(concept_id)
        readiness = by_id[concept_id]
        if not readiness.provider_ready:
            results.append({
                "concept_id": concept_id,
                "status": "upstream_not_ready",
                "provider_called": False,
                "request_count": 0,
                "preparation_status": readiness.preparation_status,
                "error_code": readiness.rejection_code,
                "primary_attribution": upstream_attribution(concept_id, readiness),
            })
            continue
        if frozen_preflight.get("concept_id") == concept_id:
            result = {**frozen_preflight, "reused_preflight": True}
        else:
            result = dict(execute_ready_item(concept_id))
            result.setdefault("reused_preflight", False)
        result.setdefault("concept_id", concept_id)
        result.setdefault("provider_called", True)
        results.append(result)
        if result.get("status") == "provider_failure" and bool(result.get("systemic")):
            break
    return results


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    before_db = database_state()
    work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="lexibridge-11e-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    temp_db = work_dir / "11e-evaluation.sqlite"
    upload_dir = work_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    provider_status = inspect_provider_policy()
    pipeline_result: dict[str, Any] = {}
    concept_outputs: list[dict[str, Any]] = []
    quality_summary = metrics.compute_quality_metrics(dataset.build_gold(), {})
    status = "BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED"
    blocker = provider_status["blocker"]
    privacy_network = {
        "ai_provider_requests": 0,
        "provider_model": provider_status.get("model_identity", ""),
        "synthetic_text_egress": 0,
        "private_data_egress": 0,
        "external_document_api_requests": 0,
        "private_pdf_usage": 0,
        "secret_exposure": 0,
        "model_downloads": 0,
        "external_network_requests": 0,
    }
    try:
        pipeline_result, concept_outputs, quality_summary = run_retrieval_only_pipeline(
            temp_db=temp_db,
            upload_dir=upload_dir,
            provider_status=provider_status,
        )
    except Exception as exc:
        blocker = f"RETRIEVAL_ONLY_PIPELINE_FAILED:{exc.__class__.__name__}"
        pipeline_result = {
            "pipeline_completed": False,
            "error_type": exc.__class__.__name__,
            "safe_error": safe_error(exc),
        }
    after_db = database_state()
    db_protection = {
        "expected_frozen_sha256": ACCIDENT_DB_FROZEN_SHA256,
        "before_sha256": before_db.get("sha256"),
        "after_sha256": after_db.get("sha256"),
        "before_size": before_db.get("size"),
        "after_size": after_db.get("size"),
        "before_mtime_epoch": before_db.get("mtime_epoch"),
        "after_mtime_epoch": after_db.get("mtime_epoch"),
        "before_wal_exists": before_db.get("wal_exists"),
        "after_wal_exists": after_db.get("wal_exists"),
        "before_shm_exists": before_db.get("shm_exists"),
        "after_shm_exists": after_db.get("shm_exists"),
        "unchanged": before_db == after_db,
        "temporary_database_path": str(temp_db),
        "database_used_for_evaluation": str(temp_db),
        "accident_database_used": False,
    }
    if not db_protection["unchanged"]:
        raise RuntimeError("Accident database changed during Task 11E evaluation.")

    if provider_status["real_provider_available"]:
        # The current repository policy is expected to keep this false. The
        # branch is retained so the artifact has a single status decision point
        # if the policy changes in a later task.
        status = (
            "BILINGUAL_KNOWLEDGE_QUALITY_BASELINE_ESTABLISHED"
            if quality_summary.get("overall_quality_pass")
            else "BILINGUAL_KNOWLEDGE_QUALITY_INSUFFICIENT"
        )
        privacy_network["ai_provider_requests"] = int(provider_status.get("requests", 0) or 0)
        privacy_network["synthetic_text_egress"] = int(provider_status.get("requests", 0) or 0)
        blocker = ""

    runtime = {
        "work_dir": str(work_dir),
        "temporary_database_path": str(temp_db),
        "upload_dir": str(upload_dir),
        "python": sys.version.split()[0],
        "backend_imported_after_temp_db_env": True,
        "corpus_gold_frozen_before_run": True,
    }
    artifact = report_builder.build_artifact(
        status=status,
        branch=current_branch(),
        runtime=runtime,
        provider=provider_status,
        pipeline=pipeline_result,
        quality_metrics=quality_summary,
        concept_outputs=concept_outputs,
        database_protection=db_protection,
        privacy_network=privacy_network,
        blocker=blocker,
    )
    review_packet = report_builder.build_review_packet_lines(concept_outputs, quality_summary)
    json_path = Path(args.json_output or DEFAULT_JSON)
    markdown_path = Path(args.markdown_output or DEFAULT_MARKDOWN)
    review_packet_path = Path(args.review_packet_output or DEFAULT_REVIEW_PACKET)
    report_builder.write_json(json_path, artifact)
    report_builder.write_markdown(markdown_path, report_builder.build_markdown_report(artifact))
    report_builder.write_jsonl(review_packet_path, review_packet)
    print(json.dumps({
        "status": status,
        "blocker": blocker,
        "json_output": str(json_path),
        "markdown_output": str(markdown_path),
        "review_packet_output": str(review_packet_path),
        "concept_count": len(dataset.build_gold()),
        "provider_requests": privacy_network["ai_provider_requests"],
        "accident_db_unchanged": db_protection["unchanged"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Task 11E bilingual quality baseline evaluation.")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--review-packet-output", default=str(DEFAULT_REVIEW_PACKET))
    parser.add_argument("--work-dir", default="")
    return parser


def inspect_provider_policy() -> dict[str, Any]:
    sys.path.insert(0, str(BACKEND))
    from services import alignment_providers, formal_document_alignment_provider_selection

    try:
        selection = formal_document_alignment_provider_selection.resolve_default_formal_document_alignment_provider_selection()
        provider = alignment_providers.get_alignment_provider(selection.provider_name)
        real_available = bool(provider.is_production_provider and getattr(provider, "supports_external_calls", False))
        blocker = "" if real_available else "FORMAL_WORKFLOW_PROVIDER_POLICY_ONLY_ALLOWS_MOCK_RULE_V1"
        return {
            "preflight_status": "REAL_PROVIDER_UNAVAILABLE" if blocker else "REAL_PROVIDER_AVAILABLE",
            "provider_name": selection.provider_name,
            "model_identity": selection.model_identity,
            "prompt_version": selection.prompt_version,
            "provider_type": provider.provider_type,
            "supports_external_calls": bool(getattr(provider, "supports_external_calls", False)),
            "is_production_provider": bool(getattr(provider, "is_production_provider", False)),
            "real_provider_available": real_available,
            "blocker": blocker,
            "requests": 0,
            "success_count": 0,
            "failure_count": 0,
            "retry_count": 0,
            "input_tokens": None,
            "output_tokens": None,
        }
    except Exception as exc:
        return {
            "preflight_status": "REAL_PROVIDER_UNAVAILABLE",
            "provider_name": "",
            "model_identity": "",
            "prompt_version": "",
            "provider_type": "",
            "supports_external_calls": False,
            "is_production_provider": False,
            "real_provider_available": False,
            "blocker": f"FORMAL_PROVIDER_PREFLIGHT_FAILED:{exc.__class__.__name__}",
            "safe_error": safe_error(exc),
            "requests": 0,
            "success_count": 0,
            "failure_count": 0,
            "retry_count": 0,
        }


def run_retrieval_only_pipeline(*, temp_db: Path, upload_dir: Path, provider_status: dict[str, Any]):
    module = load_app_module(temp_db=temp_db, upload_dir=upload_dir)
    client = module.app.test_client()
    teacher_id, teacher_token = create_login_user(module, client, role="teacher", prefix="teacher_11e")
    course = create_course(client, teacher_token, dataset.COURSE_NAME)
    uploads = []
    for source in dataset.build_corpus():
        payload = upload_source(
            client,
            teacher_token,
            course_id=course["id"],
            source=source,
        )
        result = run_ingestion_job(module, payload["job_id"])
        uploads.append({
            "source_id": source.source_id,
            "source_uid": result["source_uid"],
            "chunk_uids": result["chunk_uids"],
            "language": source.language,
            "chapter": source.chapter,
        })

    formal_runs = []
    for upload in uploads:
        if upload["language"] != "en":
            continue
        run_uid = start_formal_run(client, teacher_token, upload["source_uid"])
        formal_runs.append(run_uid)
    worker_outcomes = []
    with module.app.app_context():
        for index in range(20):
            outcome = module.run_formal_worker_once(worker_id=f"11e-formal-{index}")
            worker_outcomes.append(getattr(outcome, "outcome", str(outcome)))
            if getattr(outcome, "outcome", "") == "no_job_available":
                break

    with module.app.app_context():
        chunk_marker_map = build_chunk_evidence_marker_map(module)
        concepts = score_pipeline_outputs(module, chunk_marker_map, provider_status)
        result_map = {
            item["concept_id"]: metrics.SystemConceptResult(
                concept_id=item["concept_id"],
                english_term=item.get("english_term", ""),
                chinese_term=item.get("chinese_term", ""),
                chinese_candidates=tuple(item.get("chinese_candidates", [])),
                english_evidence_ids=tuple(item.get("english_evidence_ids", [])),
                chinese_evidence_ids=tuple(item.get("chinese_evidence_ids", [])),
                explanation_score=item.get("explanation_score"),
                unsupported_claim_count=int(item.get("unsupported_claim_count", 0) or 0),
                contradiction_count=int(item.get("contradiction_count", 0) or 0),
                source_reference_complete=bool(item.get("source_reference_complete")),
                chunk_reference_complete=bool(item.get("chunk_reference_complete")),
                parse_reference_complete_when_available=item.get("parse_reference_complete_when_available"),
                page_bbox_complete_when_available=item.get("page_bbox_complete_when_available"),
                provider_error=item.get("provider_error", ""),
                workflow_error=item.get("workflow_error", ""),
                candidate_error=item.get("candidate_error", ""),
                retrieval_error=item.get("retrieval_error", ""),
                provenance_error=item.get("provenance_error", ""),
                raw=item.get("raw", {}),
            )
            for item in concepts
        }
        summary = metrics.compute_quality_metrics(dataset.build_gold(), result_map)
        pipeline = {
            "pipeline_completed": True,
            "semantic_quality_completed": False,
            "retrieval_only": True,
            "teacher_id": teacher_id,
            "course": dataset.COURSE_NAME,
            "course_id": course["id"],
            "uploads": uploads,
            "formal_runs": formal_runs,
            "formal_worker_outcomes": worker_outcomes,
            "knowledge_source_count": module.KnowledgeSource.query.filter_by(course=dataset.COURSE_NAME).count(),
            "knowledge_chunk_count": module.KnowledgeChunk.query.filter_by(course=dataset.COURSE_NAME).count(),
            "concept_card_count": module.ConceptAlignmentCard.query.filter_by(course=dataset.COURSE_NAME).count(),
            "alignment_provider_policy_blocked_real_quality": True,
        }
        return pipeline, concepts, summary


def load_app_module(*, temp_db: Path, upload_dir: Path):
    os.environ["DATABASE_URL"] = f"sqlite:///{temp_db}"
    os.environ["UPLOAD_FOLDER"] = str(upload_dir)
    os.environ["AUTH_REQUIRED"] = "True"
    os.environ["AI_PROVIDER"] = "none"
    os.environ["ALLOW_MOCK_AI"] = "True"
    os.environ["OCR_PROVIDER"] = "none"
    os.environ["FORMULA_OCR_PROVIDER"] = "none"
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location(f"lexibridge_11e_app_{uuid.uuid4().hex}", BACKEND / "app.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load backend app module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with module.app.app_context():
        module.db.create_all()
        module.ensure_schema_columns()
    module.app.config["TESTING"] = True
    return module


def create_login_user(module, client, *, role: str, prefix: str):
    suffix = uuid.uuid4().hex[:8]
    email = f"{prefix}.{suffix}@lexibridge.local"
    password = f"{role.title()}1234!"
    with module.app.app_context():
        user = module.User(
            username=f"{prefix}_{suffix}",
            email=email,
            password_hash=module.generate_password_hash(password, method="pbkdf2:sha256"),
            role=role,
            is_verified=True,
            created_at=module.current_time_text(),
        )
        module.db.session.add(user)
        module.db.session.commit()
        user_id = user.id
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return user_id, response.get_json()["token"]


def create_course(client, teacher_token: str, name: str) -> dict[str, Any]:
    response = client.post(
        "/api/courses",
        json={
            "name": name,
            "course_code": f"PHY11E-{uuid.uuid4().hex[:6]}",
            "language_mode": "bilingual",
        },
        headers=bearer(teacher_token),
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["course"]


def upload_source(client, token: str, *, course_id: int, source: dataset.SyntheticSource) -> dict[str, Any]:
    response = client.post(
        "/api/documents/upload",
        data={
            "file": (io.BytesIO(source.text.encode("utf-8")), source.filename),
            "scope_type": "course",
            "course_id": str(course_id),
            "language": source.language,
            "source_name": source.title,
            "chapter": source.chapter,
        },
        content_type="multipart/form-data",
        headers={**bearer(token), "X-Request-ID": f"11e-upload-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["data"]


def run_ingestion_job(module, job_id: int) -> dict[str, Any]:
    with module.app.app_context():
        job = module.run_background_job(job_id, worker_id=f"11e-ingestion-{uuid.uuid4().hex[:8]}")
        assert job.status == "completed", job.error_message
        result = json.loads(job.result_json)
        assert result["ingestion_status"] == "ingested"
        return result


def start_formal_run(client, teacher_token: str, source_uid: str) -> str:
    response = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source_uid},
        headers={
            **bearer(teacher_token),
            "Idempotency-Key": f"11e-formal-{uuid.uuid4().hex}",
            "X-Request-ID": f"11e-formal-request-{uuid.uuid4().hex[:8]}",
        },
    )
    assert response.status_code == 202, response.get_data(as_text=True)
    return response.get_json()["data"]["run_uid"]


def score_pipeline_outputs(module, chunk_marker_map: dict[str, list[str]], provider_status: dict[str, Any]) -> list[dict[str, Any]]:
    from services import bilingual_evidence_workflow, chinese_term_candidates

    english_lookup = dataset.english_term_to_concept_id()
    output_by_concept: dict[str, dict[str, Any]] = {}
    for gold in dataset.build_gold():
        try:
            candidates = chinese_term_candidates.generate_chinese_term_candidates(
                module.db.session,
                concept_card_model=module.ConceptAlignmentCard,
                term_model=None,
                terminology_card_model=None,
                chunk_model=module.KnowledgeChunk,
                source_model=module.KnowledgeSource,
                english_term=gold.english_term,
                course=dataset.COURSE_NAME,
                chapter="",
                limit=10,
                filters={"include_low_quality": False, "include_needs_review": False},
            )
            selected = candidates.candidates[0] if candidates.candidates else {}
            chinese_term = str(selected.get("chinese_term") or "")
            evidence = bilingual_evidence_workflow.retrieve_bilingual_evidence(
                module.db.session,
                module.KnowledgeChunk,
                module.KnowledgeSource,
                gold.english_term,
                chinese_term=chinese_term,
                course=dataset.COURSE_NAME,
                chapter="",
                limit=5,
                filters={"include_low_quality": False, "include_needs_review": False},
                auto_generate_chinese_candidates=False,
            )
            english_evidence = [bounded_evidence(candidate, chunk_marker_map) for candidate in evidence.english_evidence_candidates]
            chinese_evidence = [bounded_evidence(candidate, chunk_marker_map) for candidate in evidence.chinese_evidence_candidates]
            output_by_concept[gold.concept_id] = {
                "concept_id": gold.concept_id,
                "english_term": gold.english_term,
                "chinese_term": chinese_term,
                "chinese_candidates": [candidate.get("chinese_term", "") for candidate in candidates.candidates],
                "candidate_scores": [candidate.get("score", 0.0) for candidate in candidates.candidates],
                "english_evidence_ids": flatten_evidence_ids(english_evidence),
                "chinese_evidence_ids": flatten_evidence_ids(chinese_evidence),
                "english_evidence": english_evidence,
                "chinese_evidence": chinese_evidence,
                "explanation": "",
                "explanation_score": 0,
                "unsupported_claim_count": 0 if provider_status["real_provider_available"] else 1,
                "contradiction_count": 0,
                "confidence": None,
                "source_reference_complete": references_complete([*english_evidence, *chinese_evidence], "source_uid"),
                "chunk_reference_complete": references_complete([*english_evidence, *chinese_evidence], "chunk_uid"),
                "parse_reference_complete_when_available": nullable_all([item.get("parse_uid") for item in [*english_evidence, *chinese_evidence]]),
                "page_bbox_complete_when_available": None,
                "provider_error": "" if provider_status["real_provider_available"] else provider_status["blocker"],
                "workflow_error": "",
                "candidate_error": "" if candidates.candidates else "no_chinese_candidate_found",
                "retrieval_error": "" if english_evidence and chinese_evidence else "bilingual_evidence_incomplete",
                "provenance_error": "" if references_complete([*english_evidence, *chinese_evidence], "chunk_uid") else "missing_chunk_ref",
                "provenance": {
                    "english_chunk_uids": [item.get("chunk_uid", "") for item in english_evidence],
                    "chinese_chunk_uids": [item.get("chunk_uid", "") for item in chinese_evidence],
                    "location_available": False,
                },
                "raw": {
                    "candidate_count": len(candidates.candidates),
                    "risk_labels": evidence.risk_labels,
                },
            }
        except Exception as exc:
            output_by_concept[gold.concept_id] = {
                "concept_id": gold.concept_id,
                "english_term": gold.english_term,
                "chinese_term": "",
                "chinese_candidates": [],
                "english_evidence_ids": [],
                "chinese_evidence_ids": [],
                "english_evidence": [],
                "chinese_evidence": [],
                "explanation_score": 0,
                "unsupported_claim_count": 0,
                "contradiction_count": 0,
                "source_reference_complete": False,
                "chunk_reference_complete": False,
                "provider_error": provider_status["blocker"],
                "workflow_error": safe_error(exc),
                "candidate_error": exc.__class__.__name__,
                "retrieval_error": exc.__class__.__name__,
                "provenance_error": "missing_result",
            }

    cards = module.ConceptAlignmentCard.query.filter_by(course=dataset.COURSE_NAME).all()
    for card in cards:
        concept_id = english_lookup.get(str(card.english_term or "").casefold())
        if concept_id and concept_id in output_by_concept:
            output_by_concept[concept_id]["draft_card_uid"] = card.card_uid
            output_by_concept[concept_id]["workflow_status"] = card.status
    return [output_by_concept[gold.concept_id] for gold in dataset.build_gold()]


def build_chunk_evidence_marker_map(module) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    chunks = module.KnowledgeChunk.query.filter_by(course=dataset.COURSE_NAME).order_by(module.KnowledgeChunk.id.asc()).all()
    for chunk in chunks:
        content = str(getattr(chunk, "content", "") or "")
        markers = markers_for_chunk(content, str(getattr(chunk, "language", "") or ""))
        mapping[str(chunk.chunk_uid)] = markers or [str(chunk.chunk_uid)]
    return mapping


def markers_for_chunk(content: str, language: str) -> list[str]:
    lowered = str(content or "").casefold()
    markers: list[str] = []
    for gold in dataset.build_gold():
        if language == "en" and gold.english_term.casefold() in lowered:
            markers.extend(gold.required_english_evidence_ids)
        elif language == "zh" and gold.english_term.casefold() in lowered and any(
            term in content for term in gold.accepted_chinese_terms
        ):
            markers.extend(gold.required_chinese_evidence_ids)
    return sorted(set(markers))


def bounded_evidence(candidate: dict[str, Any], chunk_marker_map: dict[str, list[str]]) -> dict[str, Any]:
    chunk_uid = str(candidate.get("chunk_uid") or "")
    return {
        "source_uid": str(candidate.get("source_uid") or ""),
        "chunk_uid": chunk_uid,
        "language": str(candidate.get("language") or ""),
        "source_title": str(candidate.get("source_title") or "")[:120],
        "snippet": str(candidate.get("snippet") or "")[:300],
        "score": candidate.get("score"),
        "evidence_ids": chunk_marker_map.get(chunk_uid, [chunk_uid] if chunk_uid else []),
        "parse_uid": str(candidate.get("parse_uid") or ""),
        "parse_block_uid": str(candidate.get("parse_block_uid") or ""),
        "page_number": candidate.get("page_number"),
        "bbox": None,
        "quality_status": str(candidate.get("quality_status") or ""),
    }


def flatten_evidence_ids(items: list[dict[str, Any]]) -> list[str]:
    flattened: list[str] = []
    for item in items:
        for evidence_id in item.get("evidence_ids", []):
            if evidence_id and evidence_id not in flattened:
                flattened.append(evidence_id)
    return flattened


def references_complete(items: list[dict[str, Any]], field: str) -> bool:
    return bool(items) and all(str(item.get(field) or "").strip() for item in items)


def nullable_all(values: list[Any]) -> bool | None:
    materialized = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not materialized:
        return None
    return all(materialized)


def database_state() -> dict[str, Any]:
    if not ACCIDENT_DB.exists():
        return {
            "exists": False,
            "sha256": "",
            "size": 0,
            "mtime_epoch": 0,
            "wal_exists": (BACKEND / "lexibridge.db-wal").exists(),
            "shm_exists": (BACKEND / "lexibridge.db-shm").exists(),
        }
    data = ACCIDENT_DB.read_bytes()
    stat = ACCIDENT_DB.stat()
    return {
        "exists": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": stat.st_size,
        "mtime_epoch": int(stat.st_mtime),
        "wal_exists": (BACKEND / "lexibridge.db-wal").exists(),
        "shm_exists": (BACKEND / "lexibridge.db-shm").exists(),
    }


def current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def safe_error(exc: Exception) -> str:
    text = str(exc or exc.__class__.__name__)
    forbidden = ("Authorization:", "Bearer ", "Cookie:", "sk-", "LEXIBRIDGE_SENTINEL_SECRET")
    if any(marker in text for marker in forbidden):
        return "safe error redacted"
    return text[:300]


if __name__ == "__main__":
    raise SystemExit(main())
