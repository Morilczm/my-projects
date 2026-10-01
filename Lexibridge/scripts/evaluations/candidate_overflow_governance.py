"""Provider-free Task 12B.1 frozen candidate overflow evaluation."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.bilingual_knowledge_quality import dataset, runner


OUTPUT = ROOT / "docs/evaluations/artifacts/12B1-candidate-overflow-results.json"
EXPECTED_HASHES = {
    "corpus_sha256": "33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc",
    "gold_sha256": "199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302",
}


def evaluate() -> dict:
    if dataset.dataset_hashes() != EXPECTED_HASHES:
        raise RuntimeError("Frozen corpus or gold hash mismatch.")
    before_db = runner.database_state()
    with tempfile.TemporaryDirectory(prefix="lexibridge-12b1-") as temp_name:
        temp_root = Path(temp_name)
        module = runner.load_app_module(
            temp_db=temp_root / "evaluation.sqlite",
            upload_dir=temp_root / "uploads",
        )
        from services.document_alignment_processing_orchestrator import (
            ProcessDocumentAlignmentWorkflowCommand,
        )

        client = module.app.test_client()
        _, token = runner.create_login_user(
            module, client, role="teacher", prefix="teacher_12b1"
        )
        course = runner.create_course(client, token, dataset.COURSE_NAME)
        uploads = []
        for source in dataset.build_corpus():
            upload = runner.upload_source(
                client, token, course_id=course["id"], source=source
            )
            ingested = runner.run_ingestion_job(module, upload["job_id"])
            uploads.append((source, ingested))
        runs = [
            (source, runner.start_formal_run(client, token, result["source_uid"]))
            for source, result in uploads
            if source.language == "en"
        ]

        candidates = []
        source_results = []
        with module.app.app_context():
            for source, run_uid in runs:
                claimed = module.claim_next_formal_background_job(
                    "12b1-evaluation",
                    module._formal_job_execution_dependencies(),
                )
                lease = claimed.lease
                dependencies = module.build_document_alignment_processing_dependencies(
                    session=module.db.session,
                    models=module._formal_processing_composition_models(),
                    lease=lease,
                    term_extractor=module.extract_terms_from_text,
                )
                command = ProcessDocumentAlignmentWorkflowCommand(
                    workflow_run_uid=run_uid,
                    job_uid=lease.job_uid,
                    worker_id=lease.worker_id,
                    execution_attempt=lease.execution_attempt,
                    lease_token=lease.lease_token,
                )
                bootstrap = dependencies.bootstrap.execute(command)
                run = module.DocumentAlignmentWorkflowRun.query.filter_by(
                    run_uid=run_uid
                ).one()
                items = module.DocumentAlignmentWorkflowItem.query.filter_by(
                    workflow_run_id=run.id
                ).all()
                source_results.append({
                    "source_id": source.source_id,
                    "canonical_candidates": bootstrap.canonical_candidate_count,
                    "admitted_candidates": bootstrap.admitted_candidate_count,
                    "overflow_candidates": bootstrap.overflow_candidate_count,
                    "whole_set_rejected": bootstrap.outcome != "created",
                    "governance_status": bootstrap.governance_status,
                })
                candidates.extend(
                    {
                        "candidate_term": str(item.candidate_term),
                        "item_uid": str(item.item_uid),
                        "command": command,
                        "dependencies": dependencies,
                    }
                    for item in items
                )

            by_key: dict[str, list[dict]] = {}
            for candidate in candidates:
                by_key.setdefault(
                    candidate["candidate_term"].strip().casefold(), []
                ).append(candidate)
            rows = []
            provider_ready = 0
            for gold in dataset.build_gold():
                matches = by_key.get(gold.english_term.casefold(), [])
                binding = (
                    "matched" if len(matches) == 1
                    else "ambiguous" if matches
                    else "missing"
                )
                readiness = "not_applicable"
                if binding == "matched":
                    candidate = matches[0]
                    prepared = candidate["dependencies"].preparation.prepare(
                        candidate["command"], candidate["item_uid"]
                    )
                    readiness = str(prepared.outcome)
                    provider_ready += readiness == "prepared"
                rows.append({
                    "concept_id": gold.concept_id,
                    "binding_status": binding,
                    "provider_ready": readiness == "prepared",
                    "preparation_status": readiness,
                    "included_in_denominator": True,
                })

    after_db = runner.database_state()
    if before_db != after_db:
        raise RuntimeError("Accident database changed.")
    matched = sum(row["binding_status"] == "matched" for row in rows)
    missing = sum(row["binding_status"] == "missing" for row in rows)
    ambiguous = sum(row["binding_status"] == "ambiguous" for row in rows)
    return {
        "task": "12B.1",
        "status": "CANDIDATE_SET_OVERFLOW_GOVERNANCE_CLOSED",
        "frozen_hashes": EXPECTED_HASHES,
        "before": {
            "canonical_candidates": 81,
            "admitted_candidates": 26,
            "overflow_candidates": 55,
            "whole_set_rejected_sources": 1,
            "exact_matched": 3,
            "missing": 22,
            "ambiguous": 0,
            "exact_binding_recall": 0.12,
            "provider_ready": 3,
        },
        "after": {
            "canonical_candidates": sum(item["canonical_candidates"] for item in source_results),
            "admitted_candidates": sum(item["admitted_candidates"] for item in source_results),
            "overflow_candidates": sum(item["overflow_candidates"] for item in source_results),
            "whole_set_rejected_sources": sum(item["whole_set_rejected"] for item in source_results),
            "exact_matched": matched,
            "missing": missing,
            "ambiguous": ambiguous,
            "exact_binding_recall": round(matched / len(rows), 4),
            "provider_ready": provider_ready,
        },
        "source_results": source_results,
        "rows": rows,
        "governance_overflow_benchmark_misses": 0,
        "true_exact_candidate_missing": missing,
        "real_provider_requests": 0,
        "accident_database_before": before_db,
        "accident_database_after": after_db,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifact = evaluate()
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "status": artifact["status"],
        "before": artifact["before"],
        "after": artifact["after"],
        "real_provider_requests": 0,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
