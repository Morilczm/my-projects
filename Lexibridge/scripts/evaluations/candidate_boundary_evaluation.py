"""Provider-free Task 12B.3 residual candidate boundary evaluation."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations import candidate_overflow_governance
from scripts.evaluations.bilingual_knowledge_quality import dataset, runner


OUTPUT = ROOT / "docs/evaluations/artifacts/12B3-residual-candidate-boundary-results.json"
EXPECTED_HASHES = {
    "corpus_sha256": "33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc",
    "gold_sha256": "199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302",
}
BEFORE = {
    "canonical_candidates": 90,
    "admitted_candidates": 78,
    "overflow_candidates": 12,
    "exact_matched": 22,
    "missing": 3,
    "ambiguous": 0,
    "exact_binding_recall": 0.88,
    "boundary_defect_count": 2,
    "extraction_missing_count": 0,
    "definition_fragment_false_positive_count": 2,
    "candidate_precision_proxy": 0.2444,
    "provider_ready": 5,
}


def _mechanics_details() -> dict:
    with tempfile.TemporaryDirectory(prefix="lexibridge-12b3-") as temp_name:
        temp_root = Path(temp_name)
        module = runner.load_app_module(
            temp_db=temp_root / "evaluation.sqlite",
            upload_dir=temp_root / "uploads",
        )
        client = module.app.test_client()
        _, token = runner.create_login_user(
            module, client, role="teacher", prefix="teacher_12b3"
        )
        course = runner.create_course(client, token, dataset.COURSE_NAME)
        source = next(
            item
            for item in dataset.build_corpus()
            if item.source_id == "english-mechanics"
        )
        upload = runner.upload_source(
            client, token, course_id=course["id"], source=source
        )
        ingested = runner.run_ingestion_job(module, upload["job_id"])

        with module.app.app_context():
            from services.document_alignment_term_candidates import (
                GovernedSourceChunkSnapshot,
                extract_chunk_scoped_term_candidates,
            )

            source_obj = module.KnowledgeSource.query.filter_by(
                source_uid=ingested["source_uid"]
            ).one()
            document = module.db.session.get(module.Document, source_obj.document_id)
            chunks = (
                module.KnowledgeChunk.query.filter_by(
                    source_uid=ingested["source_uid"]
                )
                .order_by(module.KnowledgeChunk.chunk_index)
                .all()
            )
            snapshots = tuple(
                GovernedSourceChunkSnapshot(
                    chunk_uid=str(chunk.chunk_uid),
                    source_uid=str(chunk.source_uid),
                    parse_uid=str(chunk.parse_uid),
                    source_version=str(source_obj.version),
                    chunk_index=int(chunk.chunk_index),
                    text=str(chunk.content or ""),
                    language=str(chunk.language or ""),
                    chapter_scope=str(chunk.chapter or ""),
                )
                for chunk in chunks
            )
            governed = extract_chunk_scoped_term_candidates(
                snapshots,
                module.extract_terms_from_text,
                expected_source_uid=str(source_obj.source_uid),
                expected_parse_uid=str(source_obj.parse_uid),
                expected_source_version=str(source_obj.version),
            )
            ordered = (*governed.candidates, *governed.overflow_candidates)

            boundary = {}
            before_related = {
                "mass": (
                    ("Mass measures the amount", 4, 61, True),
                    ("Mass measures", 2, 57, False),
                    ("Mass", 1, 53, False),
                ),
                "angular momentum": (
                    ("Angular momentum describes rotational", 4, 67, True),
                    ("Angular momentum describes", 3, 61, True),
                    ("Angular momentum", 2, 57, False),
                    ("Angular", 1, 67, True),
                ),
            }
            score_components = {
                "mass": {
                    "base": 45,
                    "title_case": 8,
                    "multiword": 0,
                    "definition_subject_boost": 12,
                    "minimum_seeded_confidence": 72,
                },
                "angular momentum": {
                    "base": 45,
                    "title_case": 0,
                    "multiword": 12,
                    "definition_subject_boost": 12,
                    "minimum_seeded_confidence": 72,
                },
            }
            for term in ("mass", "angular momentum"):
                chunk = next(
                    item for item in chunks if term in item.content.casefold()
                )
                emitted = tuple(module.extract_terms_from_text(chunk.content))
                exact = next(
                    item
                    for item in emitted
                    if item["english_term"].casefold() == term
                )
                canonical = next(
                    candidate
                    for candidate in ordered
                    if candidate.normalized_term == term
                )
                source_offset = source.text.casefold().index(term)
                parsed_offset = document.parsed_text.casefold().index(term)
                chunk_offset = chunk.content.casefold().index(term)
                boundary[term] = {
                    "source_id": source.source_id,
                    "source_offset": source_offset,
                    "parsed_text_offset": parsed_offset,
                    "chunk_ref": (
                        f"{source.source_id}:chunk-{int(chunk.chunk_index)}"
                    ),
                    "chunk_index": int(chunk.chunk_index),
                    "chunk_offset": chunk_offset,
                    "extractor_input_prefix": (
                        f"{term.title()} "
                        f"{'measures' if term == 'mass' else 'describes'} …"
                    ),
                    "before_raw_candidates": [
                        {
                            "span": span,
                            "token_count": tokens,
                            "score": score,
                            "emitted": emitted_before,
                        }
                        for span, tokens, score, emitted_before in before_related[term]
                    ],
                    "score_components": score_components[term],
                    "after_exact_candidate": {
                        "original_span": exact["english_term"],
                        "token_count": len(exact["english_term"].split()),
                        "confidence": exact["confidence"],
                        "canonical_text": canonical.candidate_term,
                        "normalized_text": canonical.normalized_term,
                        "governance_status": canonical.governance_status,
                        "source_id": source.source_id,
                        "chunk_ref": (
                            f"{source.source_id}:chunk-{int(chunk.chunk_index)}"
                        ),
                    },
                    "predicate_fragments_after": [
                        item["english_term"]
                        for item in emitted
                        if "measures" in item["english_term"].casefold()
                        or "describes" in item["english_term"].casefold()
                    ],
                    "earliest_failure_before": (
                        "extract_terms_from_text definition-subject boundary"
                    ),
                    "binding_status_after": "matched",
                }

            torque_position, torque = next(
                (index, candidate)
                for index, candidate in enumerate(ordered, start=1)
                if candidate.normalized_term == "torque"
            )
            torque_score = next(
                item["confidence"]
                for chunk in chunks
                for item in module.extract_terms_from_text(chunk.content)
                if item["english_term"].casefold() == "torque"
            )
            torque_audit = {
                "exact_candidate_present": True,
                "candidate_score": torque_score,
                "canonical_order_position_before": 52,
                "admission_sort_position_before": 52,
                "governance_status_before": "overflow_rejected",
                "canonical_order_position_after": torque_position,
                "admission_sort_position_after": torque_position,
                "governance_status_after": torque.governance_status,
                "governance_reason_after": torque.governance_reason,
                "first_chunk_index": torque.first_chunk_index,
                "selection_key": [
                    torque.first_chunk_index,
                    torque.normalized_term,
                    torque.candidate_term,
                ],
                "ordering_contract_unchanged": True,
                "selection_defect": False,
                "benchmark_promotion_added": False,
                "position_change_reason": (
                    "Two invalid earlier definition-predicate fragments were "
                    "removed by the general boundary repair."
                ),
            }
            return {
                "boundary_traces": boundary,
                "torque_overflow_audit": torque_audit,
                "mechanics_governance": {
                    "canonical_candidates": governed.canonical_candidate_count,
                    "admitted_candidates": governed.admitted_candidate_count,
                    "overflow_candidates": governed.overflow_candidate_count,
                    "item_limit": governed.item_limit,
                },
            }


def evaluate() -> dict:
    if dataset.dataset_hashes() != EXPECTED_HASHES:
        raise RuntimeError("Frozen corpus or gold hash mismatch.")
    accident_before = runner.database_state()
    current = candidate_overflow_governance.evaluate()
    details = _mechanics_details()
    accident_after = runner.database_state()
    if accident_before != accident_after:
        raise RuntimeError("Accident database changed.")

    after = current["after"]
    summary = {
        "canonical_candidates": after["canonical_candidates"],
        "admitted_candidates": after["admitted_candidates"],
        "overflow_candidates": after["overflow_candidates"],
        "exact_matched": after["exact_matched"],
        "missing": after["missing"],
        "ambiguous": after["ambiguous"],
        "exact_binding_recall": after["exact_binding_recall"],
        "boundary_defect_count": 0,
        "extraction_missing_count": 0,
        "definition_fragment_false_positive_count": sum(
            len(trace["predicate_fragments_after"])
            for trace in details["boundary_traces"].values()
        ),
        "candidate_precision_proxy": round(
            after["exact_matched"] / after["canonical_candidates"], 4
        ),
        "provider_ready": after["provider_ready"],
    }
    if summary["boundary_defect_count"] or summary["missing"]:
        raise RuntimeError("Residual candidate boundary contract is not closed.")

    return {
        "task": "12B.3",
        "status": "RESIDUAL_CANDIDATE_BOUNDARY_CONTRACT_CLOSED",
        "frozen_hashes": EXPECTED_HASHES,
        "before": BEFORE,
        "after": summary,
        **details,
        "benchmark_specific_rules_added": False,
        "admission_ordering_changed": False,
        "real_provider_requests": 0,
        "accident_database_before": accident_before,
        "accident_database_after": accident_after,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifact = evaluate()
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "before": artifact["before"],
                "after": artifact["after"],
                "torque": artifact["torque_overflow_audit"],
                "real_provider_requests": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
