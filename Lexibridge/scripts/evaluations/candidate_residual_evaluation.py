"""Provider-free Task 12B.2 residual candidate extraction evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations import candidate_failure_diagnosis
from scripts.evaluations import candidate_overflow_governance
from scripts.evaluations.bilingual_knowledge_quality import dataset


OUTPUT = ROOT / "docs/evaluations/artifacts/12B2-residual-candidate-results.json"
RESIDUAL_CONCEPT_IDS = (
    "physics-04",
    "physics-05",
    "physics-06",
    "physics-08",
    "physics-09",
    "physics-11",
    "physics-12",
    "physics-19",
    "physics-20",
    "physics-21",
    "physics-22",
)
BEFORE_ATTRIBUTIONS = {
    "physics-04": "EXTRACTION_MISSING",
    "physics-05": "CANDIDATE_BOUNDARY_DEFECT",
    "physics-06": "EXTRACTION_MISSING",
    "physics-08": "EXTRACTION_MISSING",
    "physics-09": "EXTRACTION_MISSING",
    "physics-11": "EXTRACTION_MISSING",
    "physics-12": "EXTRACTION_MISSING",
    "physics-19": "CANDIDATE_BOUNDARY_DEFECT",
    "physics-20": "EXTRACTION_MISSING",
    "physics-21": "EXTRACTION_MISSING",
    "physics-22": "EXTRACTION_MISSING",
}


def _residual_attribution(row: dict) -> str:
    mapping = {
        "CANDIDATE_EXTRACTION_DEFECT": "EXTRACTION_MISSING",
        "CANDIDATE_BOUNDARY_DEFECT": "CANDIDATE_BOUNDARY_DEFECT",
        "CANDIDATE_FRAGMENTATION_DEFECT": "CANDIDATE_FRAGMENTATION_DEFECT",
        "NORMALIZATION_DEFECT": "NORMALIZATION_DEFECT",
        "CANDIDATE_GOVERNANCE_OVERFLOW": "OVERFLOW_NOT_ADMITTED",
        "BINDING_DEFECT": "BINDING_DEFECT",
        "BENCHMARK_FIXTURE_DEFECT": "BENCHMARK_ALIAS_GAP",
        "NO_DEFECT_MATCHED": "MATCHED",
    }
    return mapping.get(row["primary_attribution"], row["primary_attribution"])


def evaluate() -> dict:
    if dataset.dataset_hashes() != candidate_overflow_governance.EXPECTED_HASHES:
        raise RuntimeError("Frozen corpus or gold hash mismatch.")
    pipeline = candidate_overflow_governance.evaluate()
    matrix, _audit, safety = candidate_failure_diagnosis.run_diagnosis()
    by_id = {row["concept_id"]: row for row in matrix}
    residual_rows = []
    for concept_id in RESIDUAL_CONCEPT_IDS:
        row = by_id[concept_id]
        residual_rows.append({
            "concept_id": concept_id,
            "source_id": row["english_source_id"],
            "gold_term": next(
                gold.english_term
                for gold in dataset.build_gold()
                if gold.concept_id == concept_id
            ),
            "source_term_present": row["source_term_present"],
            "parsed_text_term_present": row["parsed_text_term_present"],
            "chunk_term_present": row["chunk_term_present"],
            "chunk_ids": row["chunk_ids"],
            "exact_production_candidate_present": row["exact_candidate_present"],
            "near_production_candidate_present": row["near_candidate_present"],
            "overlong_candidate_present": row["overlong_candidate_present"],
            "fragmented_candidate_present": row["fragmented_candidate_present"],
            "system_candidate_ids": row["system_candidate_ids"],
            "system_candidate_summaries": row["system_candidate_summaries"],
            "candidate_admitted": row["binding_status"] == "matched",
            "candidate_overflowed": row["candidate_overflow_match_present"],
            "normalization_status": row["normalization_status"],
            "binding_status": row["binding_status"],
            "earliest_failure_stage": row["earliest_failure_stage"],
            "before_primary_attribution": BEFORE_ATTRIBUTIONS[concept_id],
            "primary_attribution": _residual_attribution(row),
            "included_in_denominator": True,
        })
    before_counts = Counter(BEFORE_ATTRIBUTIONS.values())
    after_counts = Counter(row["primary_attribution"] for row in residual_rows)
    after = pipeline["after"]
    before = {
        "canonical_candidates": 81,
        "admitted_candidates": 76,
        "overflow_candidates": 5,
        "exact_matched": 14,
        "missing": 11,
        "ambiguous": 0,
        "exact_binding_recall": 0.56,
        "extraction_missing_count": before_counts["EXTRACTION_MISSING"],
        "boundary_defect_count": before_counts["CANDIDATE_BOUNDARY_DEFECT"],
        "overflow_not_admitted_count": 0,
        "candidate_precision_proxy": round(14 / 81, 4),
        "nonbenchmark_candidate_proxy": 81 - 14,
        "definition_fragment_false_positive_count": 2,
        "provider_ready": 3,
    }
    after_summary = {
        **after,
        "extraction_missing_count": after_counts["EXTRACTION_MISSING"],
        "boundary_defect_count": after_counts["CANDIDATE_BOUNDARY_DEFECT"],
        "overflow_not_admitted_count": after_counts["OVERFLOW_NOT_ADMITTED"],
        "candidate_precision_proxy": round(after["exact_matched"] / after["canonical_candidates"], 4),
        "nonbenchmark_candidate_proxy": after["canonical_candidates"] - after["exact_matched"],
        "definition_fragment_false_positive_count": after_counts["CANDIDATE_BOUNDARY_DEFECT"],
    }
    return {
        "task": "12B.2",
        "status": "RESIDUAL_CANDIDATE_EXTRACTION_CONTRACT_PARTIAL",
        "frozen_hashes": candidate_overflow_governance.EXPECTED_HASHES,
        "before": before,
        "after": after_summary,
        "before_attribution_counts": dict(sorted(before_counts.items())),
        "after_attribution_counts": dict(sorted(after_counts.items())),
        "residual_rows": residual_rows,
        "source_results": pipeline["source_results"],
        "benchmark_specific_rules_added": False,
        "real_provider_requests": 0,
        "accident_database_before": safety["before"],
        "accident_database_after": safety["after"],
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
        "after_attribution_counts": artifact["after_attribution_counts"],
        "real_provider_requests": 0,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
